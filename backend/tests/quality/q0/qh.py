"""Helpers of the Q0 tests: raise an NCR and walk it through its states through the API."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import Ids

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def ok(res: Any, code: int = 200) -> Any:
    assert res.status_code == code, res.text
    return res.json()


def err(res: Any, status: int, code: str) -> dict[str, Any]:
    assert res.status_code == status, res.text
    d = res.json()["detail"]
    assert d["code"] == code, d
    return d


def ncr_body(ids: Ids, project: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    if project == "ANIA-EXP":
        base: dict[str, Any] = {
            "site_id": ids.site("S-LAND"),
            "responsible_engagement_id": ids.engagement("RAWABI"),
            "owner_id": ids.user("bilal.qureshi"),
        }
    else:
        base = {
            "site_id": ids.site("S-DC1"),
            "responsible_engagement_id": ids.engagement("WAHAT"),
            "owner_id": ids.user("imran.siddiq"),
        }
    base.update(
        {
            "title": "Spacers missing under the bottom mat",
            "requirement_en": "Cover 40 mm per drawing S-301.",
            "finding_en": "Cover 25 mm measured at grid C14.",
            "category": "workmanship",
            "detection_stage": "in_process",
            "classification": "minor",
        }
    )
    base.update(kw)
    return base


def raise_ncr(c: TestClient, ids: Ids, project: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    body = ncr_body(ids, project, **kw)
    body.setdefault("open", True)
    return ok(c.post(f"{API}/projects/{ids.project(project)}/quality/ncrs", json=body), 201)


def attach(c: TestClient, owner_type: str, owner_id: str, name: str = "evidence.pdf") -> str:
    res = c.post(
        f"{API}/attachments",
        data={"owner_type": owner_type, "owner_id": owner_id},
        files={"file": (name, PDF, "application/pdf")},
    )
    return str(ok(res, 201)["id"])


def ca_body(ids: Ids, **kw: Any) -> dict[str, Any]:
    b = {
        "title": "Brief the steel fixers on cover blocks",
        "description": "Toolbox briefing and a cover-block check in the pre-pour checklist.",
        "control_level": "administrative",
        "owner_id": ids.user("joseph.mathew.qc"),
        "verifier_id": ids.user("hatem.shehri"),
    }
    b.update(kw)
    return b


def to_proposed(
    c: TestClient,
    ids: Ids,
    ncr: dict[str, Any],
    *,
    lines: list[dict[str, Any]] | None = None,
    justification: str | None = None,
) -> dict[str, Any]:
    """Containment, RCA, CA (major+), disposition lines, propose — as the owner `c`."""
    nid = ncr["id"]
    if ncr["classification"] != "minor":
        ok(
            c.put(
                f"{API}/quality/ncrs/{nid}/containment",
                json={"containment_en": "Area barricaded and tagged; work stopped.", "done": True},
            )
        )
        ok(
            c.put(
                f"{API}/quality/ncrs/{nid}/rca",
                json={
                    "method": "five_why",
                    "cause_category": "method",
                    "data": {
                        "whys": [
                            "Spacers were not placed by the crew.",
                            "The crew had no spacer briefing pack.",
                            "The method statement was not issued to site.",
                        ],
                        "root_cause": "Document distribution did not reach the work front.",
                    },
                },
            )
        )
        ok(c.post(f"{API}/quality/ncrs/{nid}/actions", json=ca_body(ids)), 201)
    else:
        ok(
            c.put(
                f"{API}/quality/ncrs/{nid}/rca",
                json={
                    "method": "simple",
                    "cause_category": "people",
                    "data": {
                        "cause": "Spacers skipped under time pressure at the end of the shift."
                    },
                },
            )
        )
    body: dict[str, Any] = {"lines": lines or [{"disposition": "rework", "note": "Re-fix bars."}]}
    if justification:
        body["disposition_justification_en"] = justification
    ok(c.put(f"{API}/quality/ncrs/{nid}/disposition", json=body))
    return ok(c.post(f"{API}/quality/ncrs/{nid}/propose"))


def sign(c: TestClient, nid: str, step: str, decision: str = "approved", **kw: Any) -> Any:
    return c.post(f"{API}/quality/ncrs/{nid}/sign", json={"step": step, "decision": decision, **kw})
