"""AI assistant, insights and monthly report (spec 1-dashboard §5.9, AC65-AC77).

The Anthropic client is replaced by `FakeLlm`; the tool loop, the tools, the grounding check
and all post-processing run for real against the test database.
"""

import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.ai import tools as ai_tools
from app.core.config import get_settings
from app.core.hse_enums import GroundingResult
from app.models import AiLog, HseSettings, MonthlyReport, Project, WorkforceReturn
from tests.conftest import Api, Ids
from tests.fake_llm import FakeLlm, all_results, last_results, say, timeout, use

API = "/api/v1"
JSON = {"Accept": "application/json"}
SEP = {"preset": "month", "anchor": "2026-09-01"}


@pytest.fixture
def fake() -> Iterator[FakeLlm]:
    f = FakeLlm()
    llm.set_client_factory(lambda: f)
    yield f
    llm.set_client_factory(None)


def ask(c: TestClient, project_id: str, question: str, **extra: Any) -> Any:
    return c.post(
        f"{API}/ai/ask",
        json={"project_id": project_id, "question": question, "language": "en", **extra},
        headers=JSON,
    )


def kpi_of(messages: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    for r in last_results(messages):
        for k in r.get("kpis") or []:
            if k["metric"] == metric:
                return dict(k)
    raise AssertionError(f"{metric} not in tool results")


def logs(db: Session) -> list[AiLog]:
    db.expire_all()
    return list(db.scalars(select(AiLog).order_by(AiLog.created_at)))


# ---- AC65 grounded answer with citation ----------------------------------------------------


@pytest.mark.usefixtures("hse_seed")
def test_AC65_trir_answer_cited_and_grounded(
    api: Api, ids: Ids, fake: FakeLlm, db: Session
) -> None:
    def answer(messages: list[dict[str, Any]]) -> Any:
        k = kpi_of(messages, "K-21")
        return say(f"TRIR in September 2026 was {k['value']} {k['base_label']} [{k['cite']}].")

    fake.script(use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-21"], period=SEP), answer)
    res = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "What was our TRIR in Sep 2026?")
    assert res.status_code == 200, res.text
    a = res.json()
    assert "0.92 per 200,000 h" in a["text"]
    assert a["grounding"] == GroundingResult.passed.value
    c = a["citations"][0]
    assert c["tool"] == "get_kpis"
    assert c["metric"] == "K-21"
    assert c["value_display"] == "0.92"
    assert c["period_label_en"] == "Sep 2026"
    assert c["scope_label_en"].startswith("ANIA-EXP")
    assert "**Sources**" in a["text"]
    assert fake.calls[0]["model"] == get_settings().ai_model_default
    log = logs(db)[-1]
    assert log.grounding == GroundingResult.passed
    assert [t["name"] for t in log.tool_calls] == ["get_kpis"]
    # the same question again is served from the snapshot cache (no model call)
    fake.script()
    again = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "What was our TRIR in Sep 2026?")
    assert again.status_code == 200
    assert again.json()["text"] == a["text"]
    assert logs(db)[-1].cached is True


# ---- AC66 grounding failure → one regeneration → fallback -----------------------------------


def test_AC66_ungrounded_number_regenerates_then_falls_back(
    api: Api, ids: Ids, fake: FakeLlm, db: Session
) -> None:
    fake.script(
        use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-21"], period=SEP),
        say("TRIR was 0.97 per 200,000 h [S1]."),
        say("TRIR was 0.97 per 200,000 h [S1]."),
    )
    res = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "TRIR this month?")
    assert res.status_code == 200, res.text
    a = res.json()
    assert len(fake.calls) == 3
    regen = fake.calls[2]["messages"][-1]["content"]
    assert "0.97" in regen
    assert a["grounding"] == GroundingResult.failed.value
    assert "0.97" not in a["text"]
    assert a["fallback_table"] is not None
    assert a["fallback_table"]["rows"]
    log = logs(db)[-1]
    assert log.grounding == GroundingResult.failed
    assert "0.97" in log.grounding_failures


def test_grounding_passes_after_retry(api: Api, ids: Ids, fake: FakeLlm) -> None:
    def good(messages: list[dict[str, Any]]) -> Any:
        k = kpi_of(messages, "K-01")
        return say(f"Man-hours: {k['value']} [S1].")

    fake.script(
        use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-01"], period=SEP),
        say("Man-hours were 123,456 [S1]."),
        good,
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "Man-hours?").json()
    assert a["grounding"] == GroundingResult.passed_after_retry.value
    assert a["fallback_table"] is None


# ---- AC67 no names --------------------------------------------------------------------------


@pytest.mark.usefixtures("hse_seed")
def test_AC67_who_was_injured_gives_refs_not_names(
    api: Api, ids: Ids, fake: FakeLlm, db: Session
) -> None:
    def answer(messages: list[dict[str, Any]]) -> Any:
        rows = next(r for r in all_results(messages) if "incidents" in r)["incidents"]
        refs = ", ".join(r["ref"] for r in rows if r["cases"])
        return say(
            f"Injury cases on 8 September 2026: {refs}. Identities are available in the "
            "incident register to authorised roles."
        )

    period = {"preset": "custom", "start": "2026-09-08", "end": "2026-09-08"}
    fake.script(
        use("search_incidents", project_codes=["ANIA-EXP"], period=period),
        use("get_incident", ref="INC-ANIA-EXP-2026-0147"),
        answer,
    )
    res = ask(api.as_("faisal.harbi"), ids.project("ANIA-EXP"), "Who was injured on 8 September?")
    assert res.status_code == 200, res.text
    a = res.json()
    assert "INC-ANIA-EXP-2026-0147" in a["text"]
    assert "register" in a["text"]
    sent = fake.sent()
    for banned in ("Imran", "Hussain", "عمران", "2000000017", "person_name", "id_number"):
        assert banned not in sent, banned
        assert banned not in a["text"]
    log = json.dumps([x.tool_calls for x in logs(db)], ensure_ascii=False)
    assert "Imran" not in log and "2000000017" not in log


# ---- AC68 out-of-scope project --------------------------------------------------------------


def test_AC68_yousef_has_no_access_to_ania(api: Api, ids: Ids, fake: FakeLlm, db: Session) -> None:
    def answer(messages: list[dict[str, Any]]) -> Any:
        r = last_results(messages)[0]
        assert r.get("no_access") is True
        return say("I have no access to that data.")

    fake.script(use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-21"]), answer)
    c = api.as_("yousef.ghamdi")
    res = ask(c, ids.project("RBT-52"), "What is the TRIR of ANIA-EXP?")
    assert res.status_code == 200, res.text
    a = res.json()
    assert "no access" in a["text"]
    results = fake.calls[1]["messages"][-1]["content"]
    payload = json.loads(results[0]["content"])
    assert "kpis" not in payload and "context" not in payload
    assert "ANIA" not in json.dumps(payload)
    assert logs(db)[-1].tool_calls[0]["narrowed"] is True
    # asking on the ANIA-EXP project itself: 404, no hint
    assert ask(c, ids.project("ANIA-EXP"), "TRIR?").status_code == 404


def test_yousef_own_scope_is_not_reported_as_narrowed(api: Api, ids: Ids, fake: FakeLlm) -> None:
    seen: dict[str, Any] = {}

    def answer(messages: list[dict[str, Any]]) -> Any:
        seen.update(last_results(messages)[0])
        return say("Done.")

    fake.script(use("get_kpis", metrics=["K-01"], period=SEP), answer)
    res = ask(api.as_("yousef.ghamdi"), ids.project("RBT-52"), "Man-hours?")
    assert res.status_code == 200, res.text
    assert seen["context"]["scope_narrowed"] is False
    assert "scope_narrowed" not in seen
    assert "QIMMA" in seen["context"]["scope"]


# ---- AC69 trend needs ≥ 6 points ------------------------------------------------------------


@pytest.mark.usefixtures("hse_seed")
def test_AC69_two_months_no_trend(api: Api, ids: Ids, fake: FakeLlm) -> None:
    def honest(messages: list[dict[str, Any]]) -> Any:
        r = last_results(messages)[0]
        assert r["trend_established"] is False
        a, b = (p["value"] for p in r["points"])
        return say(
            f"TRIR was {a} in Aug 2026 and {b} in Sep 2026 [S1]. A trend cannot be "
            "established from fewer than 6 monthly points."
        )

    series = {"metric": "K-21", "granularity": "month", "start": "2026-08-01", "end": "2026-09-30"}
    fake.script(
        use("get_kpi_timeseries", project_codes=["ANIA-EXP"], **series),
        say("TRIR is trending up [S1]."),
        honest,
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "Is TRIR trending up?").json()
    assert "rule:trend_not_established" in fake.calls[2]["messages"][-1]["content"] or (
        "trend_not_established" in fake.calls[2]["messages"][-1]["content"]
    )
    assert a["grounding"] == GroundingResult.passed_after_retry.value
    assert "cannot be established" in a["text"]
    assert "trending up" not in a["text"]


# ---- AC70 / AC71 association wording --------------------------------------------------------


def _compare_stub(sufficient: bool, p: str, n: int) -> Any:
    def handler(ctx: ai_tools.ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        cid = ctx.cite(ai_tools.AiTool.compare_groups, "injury_cases by group — compare_groups")
        return {
            "dimension": params["dimension"],
            "exposure_basis": "man_hours",
            "groups": [{"group": "in", "count": n - 3}, {"group": "out", "count": 3}],
            "p_value": p,
            "n": n,
            "sample_sufficient": sufficient,
            "supports_association": sufficient and p == "0.01",
            "cite": cid,
        }, False

    return handler


def test_AC70_insufficient_sample_no_supported_difference(
    api: Api, ids: Ids, fake: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ai_tools.HANDLERS, "compare_groups", _compare_stub(False, "0.21", 8))
    fake.script(
        use("compare_groups", dimension="heat_season"),
        say("Injuries are associated with the heat season [S1]."),
        say("No statistically supported difference (n = 8) [S1]."),
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "Heat season vs rest?").json()
    assert "association_not_supported" in fake.calls[2]["messages"][-1]["content"]
    assert a["grounding"] == GroundingResult.passed_after_retry.value
    assert "No statistically supported difference (n = 8)" in a["text"]
    assert "associated with" not in a["text"]


def test_AC71_supported_association_wording(
    api: Api, ids: Ids, fake: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ai_tools.HANDLERS, "compare_groups", _compare_stub(True, "0.01", 40))
    fake.script(
        use("compare_groups", dimension="new_starter"),
        say("Being a new starter causes more injuries [S1]."),
        say(
            "Being a new starter is associated with a higher injury rate (p = 0.01, n = 40), "
            "measured against man-hours exposure [S1]."
        ),
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "New starters?").json()
    assert "causal_language" in fake.calls[2]["messages"][-1]["content"]
    assert a["grounding"] == GroundingResult.passed_after_retry.value
    assert "associated with" in a["text"]
    assert "caused" not in a["text"]
    assert "man-hours" in a["text"]


# ---- AC72 recommendations -------------------------------------------------------------------


def test_AC72_recommendations_hierarchy_label_sources(api: Api, ids: Ids, fake: FakeLlm) -> None:
    recs = [
        {"control_level": "ppe", "title": "Harness checks", "text": "...", "citation_ids": ["S1"]},
        {
            "control_level": "administrative",
            "title": "Scaffold tagging re-briefing",
            "text": "...",
            "citation_ids": ["S1"],
        },
        {
            "control_level": "engineering",
            "title": "Double guardrails and toe-boards",
            "text": "...",
            "citation_ids": ["S1"],
        },
    ]
    text = "Falls from scaffolds need stronger controls [S1].\n```recommendations\n"
    fake.script(
        use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-10"], period=SEP),
        say(text + json.dumps(recs) + "\n```"),
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "Recommendations for falls?").json()
    levels = [r["control_level"] for r in a["recommendations"]]
    assert levels == ["engineering", "administrative", "ppe"]
    assert all(r["citation_ids"] == ["S1"] for r in a["recommendations"])
    assert "AI-generated" in a["text"]
    assert "```recommendations" not in a["text"]
    assert a["ai_label_en"]


def test_AC72_ppe_only_recommendations_are_rejected(api: Api, ids: Ids, fake: FakeLlm) -> None:
    bad = [{"control_level": "ppe", "title": "Wear harness", "text": "", "citation_ids": ["S1"]}]
    good = [
        {"control_level": "engineering", "title": "Guardrails", "text": "", "citation_ids": ["S1"]}
    ]
    fake.script(
        use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-10"], period=SEP),
        say("Advice [S1].\n```recommendations\n" + json.dumps(bad) + "\n```"),
        say("Advice [S1].\n```recommendations\n" + json.dumps(good) + "\n```"),
    )
    a = ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "What should we do?").json()
    assert "no_control_above_administrative" in fake.calls[2]["messages"][-1]["content"]
    assert [r["control_level"] for r in a["recommendations"]] == ["engineering"]


# ---- AC73 disabled --------------------------------------------------------------------------


def test_AC73_ai_disabled_without_approval(api: Api, ids: Ids, fake: FakeLlm, db: Session) -> None:
    pid = ids.project("ANIA-EXP")
    db.execute(
        update(HseSettings)
        .where(HseSettings.project_id == pid)
        .values(ai_requested=False, ai_approved_on=None)
    )
    db.commit()
    c = api.as_("noura.qahtani")
    st = c.get(f"{API}/ai/status", params={"project_id": pid}).json()
    assert st["enabled"] is False
    assert st["reason_code"] == "AI_DISABLED"
    res = ask(c, pid, "TRIR?")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "AI_DISABLED"
    body = {"project_id": pid, "month": "2026-09"}
    assert c.post(f"{API}/ai/monthly-report", json=body).status_code in (403, 404)
    assert fake.calls == []
    # enabling AI without a recorded approval is refused
    mgr = api.as_("faisal.harbi")
    r = mgr.patch(f"{API}/projects/{pid}/hse-settings", json={"ai_enabled": True})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "AI_TRANSFER_APPROVAL_REQUIRED"


def test_ai_unavailable_without_key(api: Api, ids: Ids) -> None:
    pid = ids.project("ANIA-EXP")
    c = api.as_("noura.qahtani")
    st = c.get(f"{API}/ai/status", params={"project_id": pid}).json()
    assert st["enabled"] is True
    assert st["available"] is False
    assert st["reason_code"] == "AI_UNAVAILABLE"
    assert st["default_model"] == "claude-sonnet-5-5"
    assert st["deep_model"] == "claude-opus-5-5"
    res = ask(c, pid, "TRIR?")
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "AI_UNAVAILABLE"


# ---- AC74 masking ---------------------------------------------------------------------------


def test_AC74_phone_number_masked_and_warned(api: Api, ids: Ids, fake: FakeLlm) -> None:
    fake.script(say("I cannot look up contact details."))
    a = ask(
        api.as_("noura.qahtani"),
        ids.project("ANIA-EXP"),
        "Call +966500000123 about the scaffold, or mail a.b@example.com",
    ).json()
    assert "500000123" not in a["question_masked"]
    assert "a.b@example.com" not in a["question_masked"]
    assert set(a["prompt_warnings"]) == {"MOBILE_MASKED", "EMAIL_MASKED"}
    sent = fake.sent()
    assert "500000123" not in sent and "a.b@example.com" not in sent


# ---- AC75 provider timeout ------------------------------------------------------------------


def test_AC75_timeout_ai_unavailable_dashboard_ok(
    api: Api, ids: Ids, fake: FakeLlm, db: Session
) -> None:
    pid = ids.project("ANIA-EXP")
    c = api.as_("noura.qahtani")
    fake.script(timeout())
    res = ask(c, pid, "TRIR?")
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "AI_UNAVAILABLE"
    assert logs(db)[-1].error_code == "AI_UNAVAILABLE"
    # streamed: meta then an error event
    fake.script(timeout())
    sse = c.post(f"{API}/ai/ask", json={"project_id": pid, "question": "LTIFR?"})
    assert sse.status_code == 200
    assert sse.headers["content-type"].startswith("text/event-stream")
    events = [b.split("\n")[0] for b in sse.text.strip().split("\n\n")]
    assert events == ["event: meta", "event: error"]
    assert "AI_UNAVAILABLE" in sse.text
    assert c.get(f"{API}/kpi/dashboard", params={"project_id": pid}).status_code == 200


def test_sse_stream_events(api: Api, ids: Ids, fake: FakeLlm) -> None:
    fake.script(
        use("get_kpis", project_codes=["ANIA-EXP"], metrics=["K-01"], period=SEP),
        lambda m: say(f"Man-hours: {kpi_of(m, 'K-01')['value']} [S1]."),
    )
    res = api.as_("noura.qahtani").post(
        f"{API}/ai/ask", json={"project_id": ids.project("ANIA-EXP"), "question": "MH?"}
    )
    events = [b.split("\n")[0][7:] for b in res.text.strip().split("\n\n")]
    assert events[0] == "meta"
    assert "status" in events and "delta" in events and "citations" in events
    assert events[-1] == "done"


def test_rate_limit_questions_per_day(
    api: Api, ids: Ids, fake: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_questions_per_user_day", 1)
    c = api.as_("noura.qahtani")
    fake.script(say("Hello."))
    assert ask(c, ids.project("ANIA-EXP"), "Hi?").status_code == 200
    res = ask(c, ids.project("ANIA-EXP"), "Again?")
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) > 0


# ---- insights, logs -------------------------------------------------------------------------


@pytest.mark.usefixtures("hse_seed")
def test_insights_rule_based_without_key(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    q = {"project_id": ids.project("ANIA-EXP"), "anchor": "2026-07-01", "as_of": "2026-10-05"}
    res = c.get(f"{API}/ai/insights", params=q)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ai_available"] is False
    assert body["items"]
    assert all(i["source"] == "rules" for i in body["items"])
    assert any("E1" in i["title_en"] for i in body["items"])
    assert c.get(f"{API}/ai/insights", params=q).json()["cached"] is True


def test_ai_logs_manager_only(api: Api, ids: Ids, fake: FakeLlm) -> None:
    fake.script(say("Hello."))
    ask(api.as_("noura.qahtani"), ids.project("ANIA-EXP"), "Hi, my id is 2123456789")
    assert api.as_("noura.qahtani").get(f"{API}/ai/logs").status_code == 403
    res = api.as_("faisal.harbi").get(f"{API}/ai/logs")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items and items[0]["kind"] == "ask"
    assert "2123456789" not in json.dumps(items)


# ---- AC76 / AC77 monthly report -------------------------------------------------------------


def _report_narrative(messages: list[dict[str, Any]]) -> Any:
    digest = json.loads(messages[0]["content"])
    assert "Imran" not in json.dumps(digest, ensure_ascii=False)
    text = "Performance summary; see the tables for the figures."
    ar = "ملخص الأداء؛ راجع الجداول للأرقام."
    return say(
        json.dumps(
            {
                "executive_summary": {"en": text, "ar": ar},
                "trends_insights": {"en": "Values only; see tables.", "ar": ar},
                "recommendations": {"en": "Engineering controls first.", "ar": ar},
            },
            ensure_ascii=False,
        )
    )


@pytest.mark.usefixtures("hse_seed")
def test_AC76_AC77_monthly_report_draft_publish_revised(
    api: Api, ids: Ids, fake: FakeLlm, db: Session
) -> None:
    pid = ids.project("ANIA-EXP")
    fake.script(_report_narrative)
    noura = api.as_("noura.qahtani")
    res = noura.post(f"{API}/ai/monthly-report", json={"project_id": pid, "month": "2026-09"})
    assert res.status_code == 202, res.text
    rid = res.json()["id"]
    assert fake.calls[0]["model"] == get_settings().ai_model_deep
    assert fake.calls[0]["tools"] == []
    r = noura.get(f"{API}/monthly-reports/{rid}").json()
    assert r["status"] == "draft", r
    assert [s["order"] for s in r["sections"]] == list(range(1, 14))
    assert all(s["title_en"] and s["title_ar"] for s in r["sections"])
    summary = next(s for s in r["sections"] if s["section"] == "executive_summary")
    assert summary["narrative_en"] and summary["narrative_ar"]
    kpi = next(s for s in r["sections"] if s["section"] == "kpi_table")
    cells = json.dumps(kpi["tables"])
    assert "870,000" in cells and "0.92" in cells  # W3 Sep 2026 MH and TRIR
    # draft → reviewed (officer) → published (manager)
    t = noura.post(f"{API}/monthly-reports/{rid}/transitions", json={"to_status": "reviewed"})
    assert t.status_code == 200, t.text
    no = noura.post(f"{API}/monthly-reports/{rid}/transitions", json={"to_status": "published"})
    assert no.status_code == 403
    mgr = api.as_("faisal.harbi")
    pub = mgr.post(f"{API}/monthly-reports/{rid}/transitions", json={"to_status": "published"})
    assert pub.status_code == 200, pub.text
    assert pub.json()["revised_since_publication"] is False
    # restatement of Sep 2026 after publication
    row = db.scalar(
        select(WorkforceReturn)
        .join(Project, Project.id == WorkforceReturn.project_id)
        .where(Project.code == "ANIA-EXP", WorkforceReturn.work_date == date(2026, 9, 15))
        .limit(1)
    )
    assert row is not None
    row.man_hours = row.man_hours + 1000
    db.commit()
    after = mgr.get(f"{API}/monthly-reports/{rid}").json()
    assert after["revised_since_publication"] is True
    frozen = next(s for s in after["sections"] if s["section"] == "kpi_table")
    assert "870,000" in json.dumps(frozen["tables"])
    rep = db.get(MonthlyReport, rid)
    assert rep is not None


def test_monthly_report_needs_complete_month(api: Api, ids: Ids, fake: FakeLlm) -> None:
    res = api.as_("noura.qahtani").post(
        f"{API}/ai/monthly-report",
        json={"project_id": ids.project("ANIA-EXP"), "month": "2030-01"},
    )
    assert res.status_code == 422
