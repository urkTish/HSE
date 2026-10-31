"""Q0 roles, profile, settings, responsible-person matrix and sign-offs (spec 8-quality §A.16,
AC-Q0-01…16)."""

import uuid

from sqlalchemy import select

from app.core.quality.common import QRecordType
from app.db.session import get_sessionmaker
from app.main import app
from app.models import AuditEntry, Project, ProjectEngagement
from app.models.quality import QRpRule
from app.services.quality import registry as reg
from app.services.quality import rpm
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, err, ok, raise_ncr, sign, to_proposed

# ---- roles and scope -----------------------------------------------------------------------------


def test_AC01_contractor_quality_role_is_narrowed_to_its_tree(
    qsetup: None, api: Api, ids: Ids
) -> None:
    hatem = api.as_("hatem.shehri")
    mine = [
        raise_ncr(hatem, ids, responsible_engagement_id=ids.engagement(e))["id"]
        for e in ("RAWABI", "NAJD", "GULFPAVE", "SAHARA")
    ]
    faisal = api.as_("faisal.harbi")
    rbt = ids.project("RBT-52")
    ok(faisal.put(f"{API}/projects/{rbt}/quality/profile", json={"sector_profile": "construction"}))
    other = raise_ncr(faisal, ids, "ANIA-EXP", responsible_engagement_id=ids.engagement("RAWABI"))
    body = {
        "site_id": ids.site("S-TWR"),
        "responsible_engagement_id": ids.engagement("QIMMA"),
        "owner_id": ids.user("faisal.harbi"),
        "title": "Tower NCR",
        "requirement_en": "x",
        "finding_en": "y",
        "category": "workmanship",
        "detection_stage": "in_process",
        "classification": "minor",
        "open": True,
    }
    qimma = ok(faisal.post(f"{API}/projects/{rbt}/quality/ncrs", json=body), 201)
    bilal = api.as_("bilal.qureshi")
    listed = {
        n["id"]
        for n in ok(bilal.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/ncrs"))["items"]
    }
    assert set(mine) | {other["id"]} <= listed
    assert bilal.get(f"{API}/quality/ncrs/{qimma['id']}").status_code == 404
    with get_sessionmaker()() as db:
        denied = db.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "access_denied", AuditEntry.entity_id == uuid.UUID(qimma["id"])
            )
        )
        assert denied is not None


def test_AC02_contractor_assigned_never_edits_settings_or_voids(
    qsetup: None, api: Api, ids: Ids
) -> None:
    pid = ids.project("ANIA-EXP")
    bilal = api.as_("bilal.qureshi")
    assert (
        bilal.patch(
            f"{API}/projects/{pid}/quality/settings", json={"values": {"ncr_repeat_days": 120}}
        ).status_code
        == 403
    )
    n = raise_ncr(api.as_("hatem.shehri"), ids)
    assert (
        bilal.post(
            f"{API}/quality/ncrs/{n['id']}/void",
            json={"reason": "Raised twice by mistake on the same day"},
        ).status_code
        == 403
    )
    caps = {
        c["capability"]
        for p in ok(bilal.get(f"{API}/auth/me"))["projects"]
        for c in p["capabilities"]
    }
    assert "quality.settings" not in caps and "quality.void" not in caps and "ncr.manage" in caps


def test_AC03_responsible_person_sees_only_records_where_they_resolve(
    qsetup: None, api: Api, ids: Ids
) -> None:
    joseph = api.as_("joseph.mathew.qc")
    bilal = api.as_("bilal.qureshi")
    pid = ids.project("ANIA-EXP")
    plain = raise_ncr(joseph, ids)
    conc = raise_ncr(joseph, ids, quantity="10", unit="m3")
    attach(bilal, "q_ncr_evidence", conc["id"])
    to_proposed(
        bilal,
        ids,
        conc,
        lines=[{"disposition": "use_as_is", "quantity": "10"}],
        justification="Cover 25 mm accepted: durability check by the designer, exposure "
        "class XC1 interior slab, calculation attached.",
    )
    abd = api.as_("abdullah.dossary")
    listed = {n["id"] for n in ok(abd.get(f"{API}/projects/{pid}/quality/ncrs"))["items"]}
    assert conc["id"] in listed and plain["id"] not in listed
    assert abd.get(f"{API}/quality/ncrs/{plain['id']}").status_code == 404
    res = abd.post(f"{API}/exports", json={"dataset": "quality_ncrs", "project_id": pid})
    assert res.status_code == 403


# ---- profile and settings ---------------------------------------------------------------------


def test_AC04_profile_required_before_raising(qsetup: None, api: Api, ids: Ids) -> None:
    faisal = api.as_("faisal.harbi")
    rbt = ids.project("RBT-52")
    body = {"site_id": ids.site("S-TWR"), "title": "x", "open": False}
    err(faisal.post(f"{API}/projects/{rbt}/quality/ncrs", json=body), 422, "PROFILE_REQUIRED")
    home = ok(faisal.get(f"{API}/projects/{rbt}/quality/home"))
    assert home["needs_profile"] is True and home["can_configure"] is True
    ok(faisal.put(f"{API}/projects/{rbt}/quality/profile", json={"sector_profile": "construction"}))
    ok(faisal.post(f"{API}/projects/{rbt}/quality/ncrs", json=body), 201)


def test_AC05_profile_switch(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    old = raise_ncr(hatem, ids)
    err(
        hatem.put(
            f"{API}/projects/{pid}/quality/profile",
            json={"sector_profile": "logistics", "reason": "short"},
        ),
        422,
        "VALIDATION_ERROR",
    )
    ok(
        hatem.put(
            f"{API}/projects/{pid}/quality/profile",
            json={
                "sector_profile": "logistics",
                "reason": "Airport logistics centre handed over to 3PL ops",
            },
        )
    )
    with get_sessionmaker()() as db:
        e = db.scalar(
            select(AuditEntry)
            .where(AuditEntry.action == "settings_changed", AuditEntry.project_id == uuid.UUID(pid))
            .order_by(AuditEntry.occurred_at.desc())
        )
        assert e is not None and e.before == {"sector_profile": "construction"}
        assert e.after == {"sector_profile": "logistics"}
    sys_body = {
        "code": "SYS-NEW",
        "name_en": "New system",
        "name_ar": "نظام جديد",
        "discipline": "HVC",
    }
    err(hatem.post(f"{API}/projects/{pid}/quality/systems", json=sys_body), 409, "PROFILE_INACTIVE")
    raise_ncr(hatem, ids)
    listed = ok(hatem.get(f"{API}/projects/{pid}/quality/ncrs", params={"profile": "construction"}))
    assert old["id"] in {n["id"] for n in listed["items"]}


def test_AC06_profile_defaults_from_project_type(qsetup: None, api: Api, ids: Ids) -> None:
    faisal = api.as_("faisal.harbi")
    ruh = ok(faisal.get(f"{API}/projects/{ids.project('RUH-CCH')}/quality/settings"))
    rbt = ok(faisal.get(f"{API}/projects/{ids.project('RBT-52')}/quality/settings"))
    assert ruh["suggested_profile"] == "logistics" and ruh["sector_profile"] == "logistics"
    assert rbt["suggested_profile"] == "construction" and rbt["sector_profile"] is None


def test_AC07_settings_schema_and_ranges(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    keys = {d["key"]: d for d in ok(hatem.get(f"{API}/quality/settings/schema"))}
    for k in (
        "ncr_containment_hours",
        "ir_notice_hours",
        "dossier_blockers",
        "test_auto_ncr",
        "wpq_continuity_months",
        "excursion_auto_hold",
        "mapping_validity_months",
        "doc_review_months",
        "supplier_score_weights",
        "tor_warning_pct",
    ):
        assert k in keys, k
    assert {keys[k]["part"] for k in keys} == {"Q0", "Q1", "Q2", "Q3", "Q4"}
    pid = ids.project("ANIA-EXP")
    err(
        hatem.patch(
            f"{API}/projects/{pid}/quality/settings", json={"values": {"ncr_repeat_days": 20}}
        ),
        422,
        "SETTING_OUT_OF_RANGE",
    )
    s = ok(
        hatem.patch(
            f"{API}/projects/{pid}/quality/settings", json={"values": {"ncr_repeat_days": 120}}
        )
    )
    assert s["values"]["ncr_repeat_days"] == 120
    with get_sessionmaker()() as db:
        e = db.scalar(
            select(AuditEntry)
            .where(AuditEntry.action == "settings_changed", AuditEntry.entity_type == "q_settings")
            .order_by(AuditEntry.occurred_at.desc())
        )
        assert e is not None and e.after == {"ncr_repeat_days": 120}


def test_ROL01_quality_roles_assigned_by_qa_qc_manager_not_hse_officer(
    qsetup: None, api: Api, ids: Ids
) -> None:
    body = {"role": "qc_inspector", "project_id": ids.project("ANIA-EXP")}
    uid = ids.user("omar.siddiqui")
    noura = api.as_("noura.qahtani")
    assert noura.post(f"{API}/users/{uid}/role-assignments", json=body).status_code == 403
    hatem = api.as_("hatem.shehri")
    ok(hatem.post(f"{API}/users/{uid}/role-assignments", json=body), 201)


# ---- responsible-person matrix (AC-Q0-08…16) -----------------------------------------------------


def _project(db: object, code: str) -> Project:
    p = db.scalar(select(Project).where(Project.code == code))  # type: ignore[attr-defined]
    assert p is not None
    return p


def test_AC08_position_resolves_for_hold_point(qsetup: None, ids: Ids) -> None:
    with get_sessionmaker()() as db:
        p = _project(db, "ANIA-EXP")
        ctx = rpm.Ctx(site_id=uuid.UUID(ids.site("S-LAND")))
        res = rpm.resolve(db, p, QRecordType.ir, "inspect", ctx, qualifier="H")
        assert uuid.UUID(ids.user("abdullah.dossary")) in res.users
        assert uuid.UUID(ids.user("hatem.shehri")) not in res.users
        s = rpm.resolve(db, p, QRecordType.ir, "inspect", ctx, qualifier="S")
        assert uuid.UUID(ids.user("mazen.harbi")) in s.users


def _close_ready(api: Api, ids: Ids) -> dict[str, object]:
    """A minor NCR (raised by Joseph, owner Bilal) up to Pending Verification."""
    joseph, bilal, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("bilal.qureshi"),
        api.as_("hatem.shehri"),
    )
    n = raise_ncr(joseph, ids)
    to_proposed(bilal, ids, n)
    ok(sign(hatem, n["id"], "disposition"))
    ok(
        bilal.post(
            f"{API}/quality/ncrs/{n['id']}/costs",
            json={"cost_type": "rework_labour", "quantity": "4"},
        ),
        201,
    )
    return ok(
        bilal.post(
            f"{API}/quality/ncrs/{n['id']}/implement",
            json={"implementation_note": "Bars re-fixed on spacers, photos taken."},
        )
    )


def test_AC09_no_active_row(qsetup: None, api: Api, ids: Ids) -> None:
    n = _close_ready(api, ids)
    with get_sessionmaker()() as db:
        for r in db.scalars(
            select(QRpRule).where(QRpRule.record_type == "ncr", QRpRule.step == "close")
        ):
            r.active = False
        db.commit()
    err(sign(api.as_("hatem.shehri"), str(n["id"]), "close"), 422, "RESPONSIBLE_PERSON_NOT_SET")
    home = ok(api.as_("hatem.shehri").get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/home"))
    assert any(s["record_id"] == n["id"] and s["step"] == "close" for s in home["steps_without_rp"])


def test_AC10_segregation_and_self_approval(qsetup: None, api: Api, ids: Ids) -> None:
    hatem, bilal = api.as_("hatem.shehri"), api.as_("bilal.qureshi")
    n = raise_ncr(hatem, ids)
    to_proposed(bilal, ids, n)
    err(sign(hatem, n["id"], "disposition"), 422, "SOD_CONFLICT")
    with get_sessionmaker()() as db:
        r = rpm.effective_rule(db, _project(db, "ANIA-EXP").id, QRecordType.ncr, "disposition")
        assert r is not None
        r.self_approval_allowed = True
        db.commit()
    assert ok(sign(hatem, n["id"], "disposition"))["status"] == "disposition_approved"


def test_AC11_contractor_own_tree(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    rule = next(
        r
        for r in ok(hatem.get(f"{API}/projects/{pid}/quality/rp-rules"))
        if r["record_type"] == "ncr" and r["step"] == "close"
    )
    ok(
        hatem.patch(
            f"{API}/quality/rp-rules/{rule['id']}",
            json={"assignee_kind": "role", "assignee": "quality_engineer"},
        )
    )
    n = _close_ready(api, ids)
    bilal = api.as_("bilal.qureshi")
    # the owner is a requester anyway; use a GULFPAVE NCR owned by Rania for the tree check
    err(sign(bilal, str(n["id"]), "close"), 422, "SOD_CONFLICT")
    with get_sessionmaker()() as db:
        dlift = db.scalar(
            select(ProjectEngagement).where(
                ProjectEngagement.project_id == uuid.UUID(pid),
                ProjectEngagement.id.notin_(
                    [uuid.UUID(ids.engagement(c)) for c in ("RAWABI", "NAJD", "GULFPAVE", "SAHARA")]
                ),
            )
        )
    if dlift is not None:
        out = raise_ncr(
            hatem, ids, responsible_engagement_id=str(dlift.id), owner_id=ids.user("rania.zahrani")
        )
        assert bilal.get(f"{API}/quality/ncrs/{out['id']}").status_code == 404


def test_AC11_gulfpave_in_tree_refused(qsetup: None, api: Api, ids: Ids) -> None:
    hatem, rania = api.as_("hatem.shehri"), api.as_("rania.zahrani")
    pid = ids.project("ANIA-EXP")
    rule = next(
        r
        for r in ok(hatem.get(f"{API}/projects/{pid}/quality/rp-rules"))
        if r["record_type"] == "ncr" and r["step"] == "disposition"
    )
    ok(
        hatem.patch(
            f"{API}/quality/rp-rules/{rule['id']}",
            json={"assignee_kind": "role", "assignee": "quality_engineer"},
        )
    )
    n = raise_ncr(
        hatem,
        ids,
        responsible_engagement_id=ids.engagement("GULFPAVE"),
        owner_id=ids.user("rania.zahrani"),
    )
    to_proposed(rania, ids, n)
    err(sign(api.as_("bilal.qureshi"), n["id"], "disposition"), 422, "SOD_CONFLICT")


def test_AC12_matrix_change_takes_effect_without_code(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/rp-rules",
            json={
                "record_type": "ncr",
                "step": "disposition",
                "assignee_kind": "user",
                "assignee": ids.user("sultan.mutlaq"),
            },
        ),
        201,
    )
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids)
    to_proposed(api.as_("bilal.qureshi"), ids, n)
    assert (
        hatem.post(
            f"{API}/quality/ncrs/{n['id']}/sign",
            json={"step": "disposition", "decision": "approved"},
        ).status_code
        == 403
    )
    assert (
        ok(sign(api.as_("sultan.mutlaq"), n["id"], "disposition"))["status"]
        == "disposition_approved"
    )


def test_AC13_paper_signoff(qsetup: None, api: Api, ids: Ids) -> None:
    import base64

    from tests.quality.q0.qh import PDF

    hatem = api.as_("hatem.shehri")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, quantity="5", unit="m3")
    bilal = api.as_("bilal.qureshi")
    attach(bilal, "q_ncr_evidence", n["id"])
    to_proposed(
        bilal,
        ids,
        n,
        lines=[{"disposition": "use_as_is", "quantity": "5"}],
        justification="Accepted by the consultant on the basis of the designer's check "
        "of the reduced cover for an interior slab.",
    )
    paper = {
        "name": "Eng. Khalid Saleh",
        "organisation": "Al-Noor PMC Consultants",
        "position": "Resident Engineer",
        "signed_on": "2026-10-05",
    }
    err(sign(hatem, n["id"], "concession", paper=paper), 422, "VALIDATION_ERROR")
    scan = {"file_name": "signed.pdf", "content_base64": base64.b64encode(PDF).decode()}
    r = ok(sign(hatem, n["id"], "concession", paper={**paper, "scans": [scan]}))
    s = next(x for x in r["signoffs"] if x["step"] == "concession")
    assert s["channel"] == "paper" and s["evidence_attachment_ids"]
    assert s["text_en"] == (
        "Signed on paper by Eng. Khalid Saleh (Al-Noor PMC Consultants), "
        "recorded by Hatem Al-Shehri"
    )
    with get_sessionmaker()() as db:
        r2 = rpm.effective_rule(db, _project(db, "ANIA-EXP").id, QRecordType.ncr, "disposition")
        assert r2 is not None
        r2.paper_allowed = False
        db.commit()
    err(
        sign(hatem, n["id"], "disposition", paper={**paper, "scans": [scan]}),
        422,
        "VALIDATION_ERROR",
    )


def test_AC14_manager_reassigns_but_never_signs(qsetup: None, api: Api, ids: Ids) -> None:
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids)
    to_proposed(api.as_("bilal.qureshi"), ids, n)
    faisal = api.as_("faisal.harbi")
    assert sign(faisal, n["id"], "disposition").status_code == 403
    pid = ids.project("ANIA-EXP")
    ok(
        faisal.post(
            f"{API}/projects/{pid}/quality/reassign",
            json={
                "record_type": "ncr",
                "record_id": n["id"],
                "step": "disposition",
                "assignee_kind": "user",
                "assignee": ids.user("sultan.mutlaq"),
                "reason": "Hatem on leave until the 20th October",
            },
        )
    )
    other = raise_ncr(api.as_("joseph.mathew.qc"), ids)
    to_proposed(api.as_("bilal.qureshi"), ids, other)
    sultan = api.as_("sultan.mutlaq")
    assert sign(sultan, other["id"], "disposition").status_code in (403, 404)
    assert ok(sign(sultan, n["id"], "disposition"))["status"] == "disposition_approved"
    with get_sessionmaker()() as db:
        e = db.scalar(
            select(AuditEntry).where(
                AuditEntry.entity_id == uuid.UUID(n["id"]), AuditEntry.action == "update"
            )
        )
        assert e is not None


def test_AC15_signoffs_have_no_update_or_delete_route() -> None:
    for route in app.routes:
        path = getattr(route, "path", "")
        if "signoff" in path:
            assert getattr(route, "methods", set()) <= {"GET", "HEAD"}, path


def test_AC16_awaiting_my_signoff(qsetup: None, api: Api, ids: Ids) -> None:
    from datetime import UTC, datetime

    joseph, bilal, faisal = (
        api.as_("joseph.mathew.qc"),
        api.as_("bilal.qureshi"),
        api.as_("faisal.harbi"),
    )
    conc = []
    for _ in range(2):
        n = raise_ncr(joseph, ids, quantity="3", unit="m3")
        attach(bilal, "q_ncr_evidence", n["id"])
        to_proposed(
            bilal,
            ids,
            n,
            lines=[{"disposition": "use_as_is", "quantity": "3"}],
            justification="Minor cover deficiency accepted; designer check and core "
            "readings attached to the NCR evidence.",
        )
        conc.append(n["id"])
    d = raise_ncr(joseph, ids)
    to_proposed(bilal, ids, d)
    pid = ids.project("ANIA-EXP")
    ok(
        faisal.post(
            f"{API}/projects/{pid}/quality/reassign",
            json={
                "record_type": "ncr",
                "record_id": d["id"],
                "step": "disposition",
                "assignee_kind": "user",
                "assignee": ids.user("abdullah.dossary"),
                "reason": "Consultant to approve this disposition directly",
            },
        )
    )
    abd = api.as_("abdullah.dossary")
    got = ok(abd.get(f"{API}/projects/{pid}/quality/awaiting"))
    assert got["count"] == 3
    assert [i["record_id"] for i in got["items"]] == [*conc, d["id"]]
    assert {i["step"] for i in got["items"]} == {"concession", "disposition"}
    abd_id = uuid.UUID(ids.user("abdullah.dossary"))

    def extra(_db: object, p: object, project_id: uuid.UUID) -> list[reg.PendingStep]:
        if getattr(p, "user").id != abd_id:  # noqa: B009
            return []
        return [
            reg.PendingStep(
                QRecordType.ir,
                uuid.uuid4(),
                project_id,
                "IR-TEST-0001",
                "Test IR",
                "inspect",
                datetime(2026, 9, 1, tzinfo=UTC),
                "/quality/inspection-requests/x",
                "Q1",
            )
        ]

    reg.PENDING_STEPS["test"] = extra
    try:
        got = ok(abd.get(f"{API}/projects/{pid}/quality/awaiting"))
        assert got["count"] == 4 and got["items"][0]["ref"] == "IR-TEST-0001"
    finally:
        reg.PENDING_STEPS.pop("test", None)
