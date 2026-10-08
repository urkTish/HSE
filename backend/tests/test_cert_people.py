"""4-third-party-cert §9 ACs 45-49 (scaffolds), 51-55, 60, 62-63 (personnel certificates) and
64-72 (verification)."""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookSubjectType
from app.core.clock import now
from app.models import AuditEntry, PersonnelCertificate, Site, Zone
from app.services.access import common as acommon
from app.services.access import eligibility as elig
from app.services.access.hooks import HookContext
from app.services.cert import policy, validity
from tests.cert_helpers import (
    API,
    eq_payload,
    err_code,
    pcert,
    project,
    riyadh,
    scaffold,
    tpi,
    upload_pdf,
    worker,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")

PC = HookKind.personnel_certificate


# ---- scaffolds (AC45-49) ----------------------------------------------------------------------


def checklist() -> list[dict[str, str]]:
    return [{"item": f"SIC-{i:02d}", "result": "pass"} for i in range(1, 12)]


def inspect(
    api: Api, db: Session, sc_id: Any, inspector: str, kind: str = "periodic", **kw: Any
) -> Any:
    body = {"inspection_type": kind, "inspector_worker_id": str(worker(db, inspector).id),
            "checklist": checklist(), "result": "green", **kw}  # fmt: skip
    return api.as_("noura.qahtani").post(f"{API}/scaffolds/{sc_id}/inspections", json=body)


def new_scaffold(
    api: Api, db: Session, tag: str, supervisor: str, crew: list[str], **kw: Any
) -> dict[str, Any]:
    ref = scaffold(db, "SC-0142")
    body = {"tag": tag, "engagement_id": str(ref.engagement_id), "zone_id": str(ref.zone_id),
            "location_desc": "Test bay", "scaffold_type": "system_modular", "height_m": "10.00",
            "load_class": 3, "erection_supervisor_worker_id": str(worker(db, supervisor).id),
            "erection_crew_worker_ids": [str(worker(db, w).id) for w in crew], **kw}  # fmt: skip
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/scaffolds", json=body
    )
    assert res.status_code in (200, 201), res.text
    out: dict[str, Any] = res.json()
    return out


def test_P4AC45_inspector_must_hold_scaffold_inspector(api: Api, db: Session) -> None:
    sc = scaffold(db, "SC-0142")
    res = inspect(api, db, sc.id, "WKR-000001")  # Imran: SCAFFOLDER only
    assert res.status_code == 422 and err_code(res) == "INSPECTOR_NOT_CERTIFIED", res.text
    res = inspect(api, db, sc.id, "WKR-000023")  # Ferdinand
    assert res.status_code in (200, 201), res.text


def test_P4AC46_erection_supervisor_cannot_hand_over(api: Api, db: Session) -> None:
    sc = new_scaffold(api, db, "SC-0901", "WKR-000023", ["WKR-000001"])
    res = inspect(api, db, sc["id"], "WKR-000023", "handover")
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text


def test_P4AC47_design_required_above_20_m(api: Api, db: Session) -> None:
    sc = new_scaffold(api, db, "SC-0902", "WKR-000001", ["WKR-000001"],
                      scaffold_type="independent_tied", height_m="24.00")  # fmt: skip
    res = inspect(api, db, sc["id"], "WKR-000023", "handover")
    assert res.status_code == 422 and err_code(res) == "SCAFFOLD_DESIGN_REQUIRED", res.text


def test_P4AC48_sandstorm_requires_reinspection(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    land = db.scalar(select(Site).where(Site.code == "S-LAND", Site.project_id == pid))
    assert land is not None
    in_land = [
        s for s in ("SC-0142", "SC-0162", "SC-0165", "SC-0163")
        if db.get(Zone, scaffold(db, s).zone_id).site_id == land.id  # type: ignore[union-attr]
    ]  # fmt: skip
    assert in_land, "no seeded In Use scaffold on S-LAND"
    res = api.as_("khalid.otaibi").post(
        f"{API}/projects/{pid}/ops-events",
        json={"type": "dust_sandstorm", "site_id": str(land.id), "source": "hse",
              "zone_ids": [str(z) for z in db.scalars(select(Zone.id).where(Zone.site_id == land.id))],
              "source_ref": "HSE-TEST-DUST-01"},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    db.expire_all()
    for tag in in_land:
        sc = scaffold(db, tag)
        assert sc.tag_status.value == "inspection_required", tag
    policy.clear_cache(db)
    it = elig.hook_item(db, HookSubjectType.equipment_tag, scaffold(db, in_land[0]).id,
                        HookKind.equipment_certificate, "SCAFFOLD-TAG", now(),
                        acommon.settings(db, pid),
                        HookContext(project_id=pid, equipment_tag=in_land[0]))  # fmt: skip
    assert it.hard_stop


def test_P4AC49_banned_crew_member_hard_stop(api: Api, db: Session) -> None:
    sc = new_scaffold(api, db, "SC-0903", "WKR-000001", ["WKR-000022"])  # Nadeem (banned)
    res = inspect(api, db, sc["id"], "WKR-000023", "handover")
    assert res.status_code == 422 and err_code(res) == "CREW_NOT_CERTIFIED", res.text


# ---- personnel certificates (AC51-55, 60, 62-63) ----------------------------------------------


def pc_body(db: Session, wno: str, cert_type: str, tpi_code: str, cert_no: str, issued: date,
            **kw: Any) -> dict[str, Any]:  # fmt: skip
    w = worker(db, wno)
    return {
        "worker_id": str(w.id),
        "cert_type": cert_type,
        "tpi_id": str(tpi(db, tpi_code).id),
        "cert_no": cert_no,
        "issued_on": issued.isoformat(),
        "name_as_printed": kw.pop("name_as_printed", w.full_name_en),
        "id_on_card": kw.pop("id_on_card", {"shown": False}),
        **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in kw.items()},
    }


def pc_create(api: Api, db: Session, who: str, pcode: str, body: dict[str, Any]) -> Any:
    return api.as_(who).post(
        f"{API}/projects/{project(db, pcode).id}/personnel-certificates", json=body
    )


def pc_submitted(
    api: Api, db: Session, who: str, pcode: str, body: dict[str, Any]
) -> dict[str, Any]:
    c = api.as_(who)
    res = pc_create(api, db, who, pcode, body)
    assert res.status_code in (200, 201), res.text
    cid = res.json()["id"]
    upload_pdf(c, "personnel_cert_scan", cid)
    res = c.post(f"{API}/personnel-certificates/{cid}/transitions", json={"to_status": "submitted"})
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


def pc_preview(api: Api, db: Session, who: str, pcode: str, body: dict[str, Any]) -> Any:
    body = {k: v for k, v in body.items() if k != "id_on_card"}
    res = api.as_(who).post(
        f"{API}/projects/{project(db, pcode).id}/personnel-certificates/preview", json=body
    )
    assert res.status_code == 200, res.text
    return res.json()


def portal_verification(api: Api, who: str, cid: Any, tpi_host: str, **kw: Any) -> Any:
    c = api.as_(who)
    ev = upload_pdf(c, "verification_evidence", cid)
    body = {"method": "tpi_portal", "channel_used": tpi_host, "outcome": "confirmed",
            "reference": "Portal ref TEST-0001", "evidence_attachment_id": ev, **kw}  # fmt: skip
    return c.post(f"{API}/personnel-certificates/{cid}/verifications", json=body)


def test_P4AC51_Z2b_cap_limits_printed_expiry(api: Api, db: Session) -> None:
    body = pc_body(db, "WKR-000019", "FORKLIFT-OPERATOR", "AICC", "AICC-FO-TEST-25-0210",
                   date(2025, 2, 10), printed_expiry=date(2030, 2, 9),
                   scope_categories=["forklift"])  # fmt: skip
    v = pc_preview(api, db, "noura.qahtani", "ANIA-EXP", body)["validity"]
    assert (v["valid_until"], v["limiting_factor"]) == ("2028-02-09", "cap")


def test_P4AC52_Z2d_renewal_supersedes_with_no_gap(api: Api, db: Session) -> None:
    new = pcert(db, "DSPC-SC-TEST-26-1002")
    old = pcert(db, "DSPC-SC-TEST-21-1011")
    assert new.verification_due_on == date(2026, 10, 7)
    assert (
        validity.personnel_in_force(db, old, riyadh(2026, 10, 6))
        if hasattr(validity, "personnel_in_force")
        else old.valid_until == date(2026, 10, 10)
    )
    res = api.as_("faisal.harbi").post(
        f"{API}/personnel-certificates/{new.id}/transitions", json={"to_status": "accepted"}
    )
    assert res.status_code == 200, res.text
    from app.models import User

    noura = db.scalar(select(User.id).where(User.email == "noura.qahtani@example.com"))
    who = "faisal.harbi" if new.submitted_by_user_id == noura else "noura.qahtani"
    res = portal_verification(api, who, new.id, "https://dspc-test.example")
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    old = pcert(db, "DSPC-SC-TEST-21-1011")
    assert old.status.value == "superseded"
    assert old.ended_on == date(2026, 10, 6)


def test_P4AC53_Z9_id_match_never_stores_the_number(api: Api, db: Session) -> None:
    from app.models import Deployment

    z = worker(db, "WKR-000019")
    body = pc_body(db, "WKR-000019", "RIGGER", "AICC", "AICC-RG-TEST-26-1006", date(2026, 10, 1),
                   level="2", id_on_card={"shown": True, "id_type": "iqama",
                                          "id_number": "2000001019"})  # fmt: skip
    res = pc_create(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    assert res.status_code in (200, 201), res.text
    assert res.json()["id_match_result"] == "matched"
    db.expire_all()
    import uuid as _uuid

    rows = db.scalars(
        select(AuditEntry).where(AuditEntry.entity_id == _uuid.UUID(res.json()["id"]))
    ).all()
    assert rows and all("2000001019" not in str(r.__dict__) for r in rows)
    row = db.get(PersonnelCertificate, res.json()["id"])
    assert "2000001019" not in str({k: v for k, v in row.__dict__.items() if not k.startswith("_")})
    bad = {**body, "cert_no": "AICC-RG-TEST-26-1007",
           "id_on_card": {"shown": True, "id_type": "iqama", "id_number": "2000001091"}}  # fmt: skip
    res = pc_create(api, db, "ahmed.zahrani", "ANIA-EXP", bad)
    assert res.status_code == 422 and err_code(res) == "CERT_ID_MISMATCH", res.text
    db.expire_all()
    assert (
        db.scalar(
            select(PersonnelCertificate).where(
                PersonnelCertificate.cert_no == "AICC-RG-TEST-26-1007"
            )
        )
        is None
    )
    audit = [
        str(a.details) for a in db.scalars(select(AuditEntry)) if "2*******91" in str(a.details)
    ]
    assert audit
    assert not [a for a in db.scalars(select(AuditEntry)) if "2000001091" in str(a.details)]
    _ = Deployment, z


def test_P4AC54_name_mismatch_needs_tpi_confirmation(api: Api, db: Session) -> None:
    body = pc_body(db, "WKR-000009", "SIGNALLER", "AICC", "AICC-SG-TEST-26-1001", date(2026, 10, 1),
                   name_as_printed="Mohammed Qasim")  # fmt: skip
    cert = pc_submitted(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    assert cert["name_match"] == "none"
    url = f"{API}/personnel-certificates/{cert['id']}/transitions"
    res = api.as_("noura.qahtani").post(url, json={"to_status": "accepted"})
    assert res.status_code == 422 and err_code(res) == "NAME_MISMATCH_CONFIRMATION", res.text
    res = api.as_("noura.qahtani").post(
        url, json={"to_status": "accepted", "identity_confirmed_by_tpi": True}
    )
    assert res.status_code == 200, res.text


def test_P4AC55_radiographer_level(api: Api, db: Session) -> None:
    body = pc_body(db, "WKR-000009", "RADIOGRAPHER", "FNDT", "FNDT-RT-TEST-26-1001", date(2026, 10, 1),
                   level="I")  # fmt: skip
    res = pc_create(api, db, "noura.qahtani", "ANIA-EXP", body)
    assert res.status_code == 422 and err_code(res) == "LEVEL_NOT_ACCEPTED", res.text
    v = pcert(db, "FNDT-RT-TEST-22-0601")
    assert v.level is not None and v.level.value == "II" and v.valid_until == date(2027, 5, 31)


def test_P4AC60_second_rigger_card_supersedes_the_first(api: Api, db: Session) -> None:
    body = pc_body(
        db, "WKR-000009", "RIGGER", "AICC", "AICC-RG-TEST-26-1002", date(2026, 10, 1), level="2"
    )
    cert = pc_submitted(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    res = api.as_("noura.qahtani").post(
        f"{API}/personnel-certificates/{cert['id']}/transitions", json={"to_status": "accepted"}
    )
    assert res.status_code == 200, res.text
    res = portal_verification(api, "noura.qahtani", cert["id"], "https://verify.aicc-test.example")
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    rows = db.scalars(select(PersonnelCertificate).where(
        PersonnelCertificate.worker_id == worker(db, "WKR-000009").id,
        PersonnelCertificate.cert_type == "RIGGER")).all()  # fmt: skip
    st = {r.cert_no: r.status.value for r in rows}
    assert st == {"AICC-RG-TEST-24-0601": "superseded", "AICC-RG-TEST-26-1002": "accepted"}


def test_P4AC62_trade_cert_missing_is_not_blocking(api: Api, db: Session) -> None:
    w = worker(db, "WKR-000104")
    res = api.as_("faisal.harbi").get(f"{API}/workers/{w.id}/certificates")
    assert res.status_code == 200, res.text
    assert res.json()["trade_requirement"] == "RIGGER"
    assert res.json()["trade_requirement_met"] is False


def test_P4AC63_medical_flag_hidden_and_restriction_review(api: Api, db: Session) -> None:
    body = pc_body(db, "WKR-000019", "SIGNALLER", "AICC", "AICC-SG-TEST-26-1002", date(2026, 10, 1),
                   medical_restriction_on_card=True)  # fmt: skip
    cert = pc_submitted(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    cid = cert["id"]
    assert (
        api.as_("noura.qahtani")
        .post(f"{API}/personnel-certificates/{cid}/transitions", json={"to_status": "accepted"})
        .status_code
        == 200
    )
    assert portal_verification(
        api, "noura.qahtani", cid, "https://verify.aicc-test.example"
    ).status_code in (200, 201)
    fahad = api.as_("fahad.mutairi").get(f"{API}/personnel-certificates/{cid}")
    if fahad.status_code == 200:
        assert "medical_restriction_on_card" not in fahad.json()
    assert (
        api.as_("noura.qahtani")
        .get(f"{API}/personnel-certificates/{cid}")
        .json()["medical_restriction_on_card"]
        is True
    )
    pid = project(db, "ANIA-EXP").id
    db.expire_all()
    policy.clear_cache(db)
    it = elig.hook_item(db, HookSubjectType.worker, worker(db, "WKR-000019").id, PC, "SIGNALLER", now(),
                        acommon.settings(db, pid), HookContext(project_id=pid))  # fmt: skip
    j = it.to_schema().model_dump(mode="json")
    assert j["status"] == "met" and "CARD_RESTRICTION_REVIEW" in str(j)
    res = api.as_("noura.qahtani").post(
        f"{API}/personnel-certificates/{cid}/restriction-review", json={}
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    policy.clear_cache(db)
    it = elig.hook_item(db, HookSubjectType.worker, worker(db, "WKR-000019").id, PC, "SIGNALLER", now(),
                        acommon.settings(db, pid), HookContext(project_id=pid))  # fmt: skip
    assert "CARD_RESTRICTION_REVIEW" not in str(it.to_schema().model_dump(mode="json"))


# ---- verification (AC64-72) -------------------------------------------------------------------


def _accepted_unverified(api: Api, db: Session, wno: str, ctype: str, no: str, **kw: Any) -> str:
    body = pc_body(db, wno, ctype, kw.pop("tpi_code", "AICC"), no, date(2026, 10, 1), **kw)
    cert = pc_submitted(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    res = api.as_("noura.qahtani").post(
        f"{API}/personnel-certificates/{cert['id']}/transitions", json={"to_status": "accepted"}
    )
    assert res.status_code == 200, res.text
    return str(cert["id"])


def test_P4AC64_unverified_acceptance_window(api: Api, db: Session) -> None:
    sig = _accepted_unverified(
        api, db, "WKR-000009", "GAS-TESTER", "DSPC-GT-TEST-26-1003", tpi_code="DSPC"
    )
    op = _accepted_unverified(api, db, "WKR-000009", "CRANE-OPERATOR", "AICC-OP-TEST-26-1004",
                              scope_categories=["mobile_crane"])  # fmt: skip

    def in_force(cid: str) -> tuple[bool, str | None]:
        r = api.as_("noura.qahtani").get(f"{API}/personnel-certificates/{cid}").json()["validity"]
        return r["in_force"], r["not_in_force_reason"]

    assert in_force(sig) == (False, "CERT_UNVERIFIED")
    pid = project(db, "ANIA-EXP").id
    res = api.as_("faisal.harbi").patch(
        f"{API}/projects/{pid}/cert-settings", json={"unverified_acceptance_hours": 24}
    )
    assert res.status_code == 200, res.text
    assert in_force(sig)[0] is True
    assert in_force(op) == (False, "CERT_UNVERIFIED")


def test_P4AC65_verifier_sod(api: Api, db: Session) -> None:
    body = pc_body(db, "WKR-000009", "SIGNALLER", "AICC", "AICC-SG-TEST-26-1005", date(2026, 10, 1))
    cert = pc_submitted(api, db, "noura.qahtani", "ANIA-EXP", body)
    res = portal_verification(api, "noura.qahtani", cert["id"], "https://verify.aicc-test.example")
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text
    res = api.as_("ahmed.zahrani").post(
        f"{API}/personnel-certificates/{cert['id']}/verifications",
        json={"method": "tpi_phone", "channel_used": "+966500000000", "outcome": "confirmed",
              "reference": "AICC verification desk supervisor"},
    )  # fmt: skip
    assert res.status_code == 403, res.text


def test_P4AC66_email_channel_must_be_registered(api: Api, db: Session) -> None:
    cid = _accepted_unverified(api, db, "WKR-000009", "SIGNALLER", "AICC-SG-TEST-26-1006")
    c = api.as_("noura.qahtani")
    ev = upload_pdf(c, "verification_evidence", cid)
    res = c.post(f"{API}/personnel-certificates/{cid}/verifications",
                 json={"method": "tpi_email", "channel_used": "certs@aicc-verify-mail.example",
                       "outcome": "confirmed", "reference": "Mail TEST-1", "evidence_attachment_id": ev})  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "CHANNEL_NOT_REGISTERED", res.text


def test_P4AC67_foreign_qr_url_warns_and_is_not_a_channel(api: Api, db: Session) -> None:
    url = "https://aicc-verify-test.example.net/c/AICC-SG-TEST-26-1007"
    body = pc_body(db, "WKR-000009", "SIGNALLER", "AICC", "AICC-SG-TEST-26-1007", date(2026, 10, 1),
                   tpi_verification_url=url)  # fmt: skip
    pv = pc_preview(api, db, "ahmed.zahrani", "ANIA-EXP", body)
    assert "VERIFICATION_URL_FOREIGN_DOMAIN" in [w["code"] for w in pv["warnings"]]
    cid = _accepted_unverified(api, db, "WKR-000009", "SIGNALLER", "AICC-SG-TEST-26-1007",
                               tpi_verification_url=url)  # fmt: skip
    c = api.as_("noura.qahtani")
    ev = upload_pdf(c, "verification_evidence", cid)
    res = c.post(f"{API}/personnel-certificates/{cid}/verifications",
                 json={"method": "tpi_qr_url", "channel_used": url, "outcome": "confirmed",
                       "reference": "QR TEST-1", "evidence_attachment_id": ev})  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "CHANNEL_NOT_REGISTERED", res.text


def test_P4AC68_two_no_responses_26h_apart(api: Api, db: Session) -> None:
    cid = _accepted_unverified(api, db, "WKR-000009", "SIGNALLER", "AICC-SG-TEST-26-1008")
    c = api.as_("noura.qahtani")
    for at in (now() - timedelta(hours=26), now()):
        ev = upload_pdf(c, "verification_evidence", cid)
        res = c.post(f"{API}/personnel-certificates/{cid}/verifications",
                     json={"method": "tpi_portal", "channel_used": "https://verify.aicc-test.example",
                           "outcome": "no_response", "reference": "Portal TEST-NR",
                           "evidence_attachment_id": ev,
                           "performed_at": at.isoformat()})  # fmt: skip
        assert res.status_code in (200, 201), res.text
    r = c.get(f"{API}/personnel-certificates/{cid}").json()
    assert r["verification_status"] == "unable_to_verify"
    assert r["validity"]["in_force"] is False
    from app.models import Notification, User

    db.expire_all()
    fid = db.scalar(select(User.id).where(User.email == "faisal.harbi@example.com"))
    assert db.scalar(select(Notification.id).where(
        Notification.user_id == fid, Notification.title_en.like("Unable to verify%"))) is not None  # fmt: skip


def test_P4AC69_failed_verification_rejects_and_raises_e11(api: Api, db: Session) -> None:
    c = pcert(db, "QC-SC-TEST-26-0777")
    assert c.status.value == "rejected"
    assert c.status_reason is not None and c.status_reason.value == "verification_failed"
    from app.models import CertificationBan

    ban = db.scalar(
        select(CertificationBan).where(CertificationBan.worker_id == worker(db, "WKR-000022").id)
    )
    assert ban is not None and ban.from_date == date(2026, 9, 17)


def test_P4AC70_original_sighted_does_not_verify(api: Api, db: Session) -> None:
    cid = _accepted_unverified(api, db, "WKR-000009", "SIGNALLER", "AICC-SG-TEST-26-1009")
    c = api.as_("noura.qahtani")
    ev = upload_pdf(c, "verification_evidence", cid)
    res = c.post(f"{API}/personnel-certificates/{cid}/verifications",
                 json={"method": "original_sighted", "channel_used": "site office",
                       "outcome": "confirmed", "reference": "Card sighted TEST",
                       "evidence_attachment_id": ev})  # fmt: skip
    assert res.status_code in (200, 201), res.text
    assert (
        c.get(f"{API}/personnel-certificates/{cid}").json()["verification_status"] == "not_verified"
    )


def test_P4AC71_equipment_sticker_card_has_no_personal_data(api: Api, db: Session) -> None:
    res = api.as_("noura.qahtani").post(
        f"{API}/certification-checks",
        json={"payload": eq_payload(db, "RW-MC-03"), "project_id": str(project(db, "ANIA-EXP").id)},
    )
    assert res.status_code == 200, res.text
    card = res.json()["equipment"]
    assert card["category"] == "mobile_crane" and card["tag"] == "RW-MC-03"
    assert card["owner_short_code"] == "RAWABI" and card["service_status"] == "in_service"
    assert card["cert_no"] == "AICC-EQ-TEST-25-1106" and card["tpi_code"] == "AICC"
    assert card["valid_until"] == "2026-11-05" and card["swl_t"] == "50.000"
    assert "limitations" in card
    for k in ("operator", "inspector_name", "full_name_en"):
        assert k not in res.text


def test_P4AC72_ac_card_in_certificates_mode(api: Api, db: Session) -> None:
    from app.models import Deployment, QrToken

    w = worker(db, "WKR-000108")
    d = db.scalar(select(Deployment).where(Deployment.worker_id == w.id,
                                           Deployment.project_id == project(db, "RBT-52").id))  # fmt: skip
    assert d is not None
    t = db.scalar(
        select(QrToken).where(QrToken.subject_id == d.id).order_by(QrToken.created_at.desc())
    )
    assert t is not None
    res = api.as_("lina.haddad").post(
        f"{API}/certification-checks",
        json={"payload": acommon.payload(t), "project_id": str(project(db, "RBT-52").id)},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    certs = {c["cert_type"]: c for c in body["person"]["certificates"]}
    assert (
        certs["RIGGER"]["valid_until"] == "2026-10-20"
        and certs["SIGNALLER"]["valid_until"] == "2028-03-02"
    )
    assert all(c["in_force"] for c in certs.values())
    txt = res.text
    for k in ("id_number", "scan", "medical", "verification"):
        assert k not in txt, k
    db.expire_all()
    from app.core.enums import AuditAction

    assert (
        db.scalar(select(AuditEntry.id).where(AuditEntry.action == AuditAction.cert_check_view))
        is not None
    )
