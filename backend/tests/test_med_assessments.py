"""6a-occupational-health §9 ACs 15-18, 20, 32-33, 35-44, 46-58 (assessments, providers and
examiners at recording, external certificates and verification)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import HookReasonCode
from app.core.clock import set_now
from app.models import (
    AuditEntry,
    FitnessAssessment,
    FitnessLine,
    Notification,
    User,
    Worker,
)
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.med_helpers import (
    API,
    act,
    assessment,
    body,
    check,
    err,
    fit,
    hold,
    ok,
    post,
    project,
    referral,
    riyadh,
)

pytestmark = pytest.mark.usefixtures("med_seed", "clock")


# ---- site clinic --------------------------------------------------------------------------------


def test_AC32_site_clinic_signed_by_linked_examiner(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    old = assessment(db, "MFA-ANIA-EXP-2026-00220")
    a = ok(post(huda, db, body(db, "WKR-000014", [fit()])))
    assert a["status"] == "accepted" and a["verification_status"] == "verified"
    assert a["certificate_no"].startswith("MFC-ANIA-EXP-2026-")
    db.expire_all()
    lines = {
        ln.code: ln.line_state.value
        for ln in db.scalars(select(FitnessLine).where(FitnessLine.assessment_id == old.id))
    }
    assert lines["GEN-FIT"] == "superseded" and lines["NOISE-SURV"] == "governing"


def test_AC33_AC35_awaiting_signoff_then_release(api: Api, db: Session) -> None:
    grace = api.as_("grace.villanueva")
    r = referral(db, "MFR-ANIA-EXP-2026-00031")
    h = hold(db, "MFH-ANIA-EXP-2026-00027")
    res = post(
        grace,
        db,
        body(db, "WKR-000034", [fit()], examiner=3, typ="referral", related_referral_id=str(r.id)),
    )
    assert res.status_code == 422 and err(res) == "EXAMINER_NOT_LINKED", res.text
    a = ok(
        post(
            grace,
            db,
            body(
                db,
                "WKR-000034",
                [fit()],
                typ="referral",
                related_referral_id=str(r.id),
                related_hold_id=str(h.id),
            ),
        )
    )
    assert a["status"] == "awaiting_signoff"
    assert check(db, "WKR-000034", "GEN-FIT").reason == HookReasonCode.MEDICAL_HOLD
    ok(act(api.as_("huda.mansour"), a["id"], "sign"))
    db.expire_all()
    assert hold(db, "MFH-ANIA-EXP-2026-00027").status.value == "released"
    assert referral(db, "MFR-ANIA-EXP-2026-00031").status.value == "assessed"
    assert check(db, "WKR-000034", "GEN-FIT").ok


def test_AC36_AC37_backdate_and_notice(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    res = post(huda, db, body(db, "WKR-000014", [fit()], examined=date(2026, 9, 28)))
    assert err(res) == "BACKDATED_ASSESSMENT", res.text
    ok(post(huda, db, body(db, "WKR-000014", [fit()], examined=date(2026, 9, 29))))
    res = post(huda, db, body(db, "WKR-000015", [fit()], purpose_notice_given=False))
    assert err(res) == "PURPOSE_NOTICE_REQUIRED", res.text


def test_AC38_AC39_AC43_line_rules(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    cases = [
        ([fit(outcome="fit_with_restrictions")], "RESTRICTIONS_REQUIRED"),
        ([fit(restrictions=[{"code": "no_night_work"}])], "RESTRICTIONS_NOT_ALLOWED"),
        (
            [fit(outcome="fit_with_restrictions", restrictions=[{"code": "no_work_at_height"}])],
            "REVIEW_DATE_INVALID",
        ),
        (
            [
                fit(
                    outcome="fit_with_restrictions",
                    restrictions=[{"code": "no_work_at_height"}],
                    restriction_review_date="2027-01-05",
                )
            ],
            "REVIEW_DATE_INVALID",
        ),
        ([fit(), fit()], "DUPLICATE_CODE_LINE"),
    ]
    for lines, code in cases:
        res = post(huda, db, body(db, "WKR-000015", lines))
        assert res.status_code == 422 and err(res) == code, (code, res.text)
    a = ok(
        post(
            huda,
            db,
            body(
                db,
                "WKR-000015",
                [
                    fit(
                        "GEN-FIT",
                        "fit_with_restrictions",
                        restrictions=[{"code": "requires_corrective_lenses"}],
                    )
                ],
            ),
        )
    )
    assert a["lines"][0]["valid_until"] == "2028-10-05"


def test_AC40_temporarily_unfit_hard_stop(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    res = post(huda, db, body(db, "WKR-000015", [fit(outcome="temporarily_unfit")]))
    assert res.status_code == 422, res.text
    ok(
        post(
            huda,
            db,
            body(
                db, "WKR-000015", [fit(outcome="temporarily_unfit", unfit_review_date="2026-11-05")]
            ),
        )
    )
    for when in (None, date(2026, 11, 6)):
        chk = check(
            db,
            "WKR-000015",
            "GEN-FIT",
            None if when is None else riyadh(when.year, when.month, when.day),
        )
        assert chk.reason == HookReasonCode.MEDICAL_UNFIT and chk.hard_stop


def test_AC41_AC42_permanently_unfit_and_second_opinion(api: Api, db: Session) -> None:
    res = post(
        api.as_("huda.mansour"),
        db,
        body(
            db,
            "WKR-000015",
            [fit("WAH-FIT", "permanently_unfit")],
            examiner=2,
            source="external_certificate",
            certificate_no="X-TEST-41",
        ),
    )
    assert err(res) == "EXAMINER_NOT_QUALIFIED", res.text
    huda = api.as_("huda.mansour")
    ok(post(huda, db, body(db, "WKR-000015", [fit("WAH-FIT", "permanently_unfit")])))
    faisal = db.scalar(select(User).where(User.email == "faisal.harbi@example.com"))
    assert faisal is not None
    note = db.scalars(
        select(Notification).where(
            Notification.user_id == faisal.id, Notification.kind == "fitness_permanently_unfit"
        )
    )
    n = note.first()
    assert n is not None and "WAH" not in (n.title_en or "")
    res = post(huda, db, body(db, "WKR-000015", [fit("WAH-FIT")]))
    assert err(res) == "SECOND_OPINION_REQUIRED", res.text
    # a second opinion by Dr. Nadia (EXR-0005, another occupational physician) is accepted
    ext = {"source": "external_certificate", "certificate_no": "X-TEST-42"}
    ok(post(huda, db, body(db, "WKR-000015", [fit("WAH-FIT")], examiner=5, **ext)))


def test_AC44_edit_lock_and_revoke(api: Api, db: Session) -> None:
    a = assessment(db, "MFA-ANIA-EXP-2026-00220")
    res = api.as_("grace.villanueva").patch(
        f"{API}/fitness-assessments/{a.id}", json={"lines": [fit()]}
    )
    assert res.status_code in (403, 409), res.text
    huda = api.as_("huda.mansour")
    res = act(huda, str(a.id), "revoke", reason="short")
    assert res.status_code == 422, res.text
    ok(act(huda, str(a.id), "revoke", reason="Recorded against the wrong worker file"))
    assert check(db, "WKR-000014", "GEN-FIT").reason == HookReasonCode.MEDICAL_REVOKED


# ---- providers and examiners at recording (MP-3, EX-2) ------------------------------------------


def test_AC15_AC16_AC17_AC18_AC20_acceptability(api: Api, db: Session) -> None:
    grace = api.as_("grace.villanueva")
    huda = api.as_("huda.mansour")
    ahmed = api.as_("ahmed.zahrani")
    ext = {"source": "external_certificate", "certificate_no": "X-TEST-1"}
    res = post(
        ahmed,
        db,
        body(db, "WKR-000016", [fit("CSE-ENTRY-FIT")], prov="RAWABI-CC", examiner=4, **ext),
    )
    assert err(res) == "MEDICAL_PROVIDER_NOT_ACCEPTABLE", res.text
    assert res.json()["detail"]["meta"]["reason"] == "PROVIDER_KIND_NOT_ALLOWED"
    res = post(
        api.as_("lina.haddad"),
        db,
        body(db, "WKR-000107", [fit()], prov="RAWABI-CC", examiner=4, **ext),
        "RBT-52",
    )
    assert res.json()["detail"]["meta"]["reason"] == "NOT_OWN_TREE", res.text
    res = post(grace, db, body(db, "WKR-000015", [fit()], prov="SHIFA-RBT"))
    assert res.json()["detail"]["meta"]["reason"] == "NOT_PROJECT_CLINIC", res.text
    qm = {"source": "external_certificate", "prov": "QUICKMED", "examiner": 6}
    res = post(
        ahmed,
        db,
        body(
            db, "WKR-000016", [fit()], examined=date(2026, 9, 25), certificate_no="QM-TEST-A", **qm
        ),
    )
    assert res.json()["detail"]["meta"]["reason"] == "PROVIDER_SUSPENDED", res.text
    res = post(
        ahmed,
        db,
        body(
            db, "WKR-000016", [fit()], examined=date(2026, 9, 24), certificate_no="QM-TEST-B", **qm
        ),
    )
    assert (
        res.status_code == 422 and err(res) == "FITNESS_ALREADY_EXPIRED"
    ) or res.status_code in (200, 201), res.text
    res = post(huda, db, body(db, "WKR-000020", [fit("RAD-WORKER-FIT")], examiner=2, **ext))
    assert err(res) == "EXAMINER_NOT_QUALIFIED", res.text
    set_now(riyadh(2026, 10, 21))
    res = post(
        huda, db, body(db, "WKR-000015", [fit()], examiner=2, examined=date(2026, 10, 21), **ext)
    )
    assert err(res) == "EXAMINER_LICENCE_INVALID", res.text


# ---- external certificates and verification ------------------------------------------------------


def _external(
    api: Api,
    db: Session,
    cert: str = "SAL-TEST-26-1001",
    who: str = "WKR-000016",
    lines: list[dict[str, Any]] | None = None,
) -> tuple[Any, str]:
    ahmed = api.as_("ahmed.zahrani")
    a = ok(
        post(
            ahmed,
            db,
            body(
                db,
                who,
                lines or [fit("DRIVER-FIT"), fit()],
                prov="SALAMA",
                examiner=3,
                source="external_certificate",
                certificate_no=cert,
                examined=date(2026, 10, 4),
            ),
        )
    )
    return ahmed, a["id"]


def test_AC46_AC47_AC48_submit_accept_verify(api: Api, db: Session) -> None:
    ahmed, aid = _external(api, db)
    res = act(ahmed, aid, "submit")
    assert err(res) == "SCAN_REQUIRED", res.text
    upload_pdf(ahmed, "fitness_scan", aid)
    ok(act(ahmed, aid, "submit"))
    assert act(ahmed, aid, "accept").status_code == 403
    huda = api.as_("huda.mansour")
    ok(act(huda, aid, "accept", clinical_data_present=False))
    assert check(db, "WKR-000016", "DRIVER-FIT").reason == HookReasonCode.MEDICAL_UNVERIFIED
    res = huda.post(
        f"{API}/fitness-assessments/{aid}/verifications",
        json={
            "method": "clinic_portal",
            "channel_used": "https://evil.example/verify",
            "outcome": "confirmed",
            "reference": "portal check",
        },
    )
    assert err(res) == "CHANNEL_NOT_REGISTERED", res.text
    ok(
        huda.post(
            f"{API}/fitness-assessments/{aid}/verifications",
            json={
                "method": "clinic_portal",
                "channel_used": "https://verify.salama-test.example/c/1",
                "outcome": "confirmed",
                "reference": "portal check 1",
            },
        )
    )
    assert check(db, "WKR-000016", "DRIVER-FIT").ok


def test_AC50_unverified_window(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    ok(
        api.as_("faisal.harbi").patch(
            f"{API}/projects/{pid}/medical-settings",
            json={"unverified_fitness_acceptance_hours": 24},
        )
    )
    ahmed, aid = _external(api, db, lines=[fit("DRIVER-FIT"), fit("CSE-ENTRY-FIT")])
    upload_pdf(ahmed, "fitness_scan", aid)
    ok(act(ahmed, aid, "submit"))
    ok(act(api.as_("huda.mansour"), aid, "accept", clinical_data_present=False))
    assert check(db, "WKR-000016", "DRIVER-FIT").ok
    assert check(db, "WKR-000016", "CSE-ENTRY-FIT").reason == HookReasonCode.MEDICAL_UNVERIFIED


def test_AC51_unable_to_verify(api: Api, db: Session) -> None:
    from app.core.clock import set_now

    ahmed, aid = _external(api, db)
    upload_pdf(ahmed, "fitness_scan", aid)
    ok(act(ahmed, aid, "submit"))
    huda = api.as_("huda.mansour")
    ok(act(huda, aid, "accept", clinical_data_present=False))
    v = {
        "method": "clinic_email",
        "channel_used": "fitness@salama-test.example",
        "outcome": "no_response",
        "reference": "email sent",
    }
    ok(huda.post(f"{API}/fitness-assessments/{aid}/verifications", json=v))
    set_now(riyadh(2026, 10, 7, 11))
    huda = api.as_("huda.mansour")
    ok(huda.post(f"{API}/fitness-assessments/{aid}/verifications", json=v))
    db.expire_all()
    assert db.get(FitnessAssessment, uuid.UUID(aid)).verification_status.value == (
        "unable_to_verify"
    )


def test_AC52_quickmed_rejected_hard_stop(db: Session) -> None:
    a = db.scalar(
        select(FitnessAssessment).where(FitnessAssessment.certificate_no == "QM-TEST-26-0917")
    )
    assert a is not None and a.status.value == "rejected"
    w = db.get(Worker, a.worker_id)
    assert w is not None
    chk = check(db, w.worker_no, "GEN-FIT")
    assert chk.reason == HookReasonCode.MEDICAL_VERIFICATION_FAILED and chk.hard_stop


def test_AC53_clinical_data_rejects_and_purges(api: Api, db: Session) -> None:
    ahmed, aid = _external(api, db)
    upload_pdf(ahmed, "fitness_scan", aid)
    ok(act(ahmed, aid, "submit"))
    a = ok(
        act(
            api.as_("huda.mansour"),
            aid,
            "reject",
            reason="clinical data",
            clinical_data_present=True,
        )
    )
    assert a["status"] == "rejected"
    purge = db.scalar(
        select(AuditEntry).where(
            AuditEntry.action == "retention_purge", AuditEntry.entity_id == uuid.UUID(aid)
        )
    )
    assert purge is not None


def test_AC54_AC55_cert_reuse_and_id_mismatch(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    res = post(
        ahmed,
        db,
        body(
            db,
            "WKR-000016",
            [fit()],
            prov="SALAMA",
            examiner=3,
            source="external_certificate",
            certificate_no="SAL-TEST-26-0220",
            examined=date(2026, 10, 4),
        ),
    )
    assert res.status_code == 409 and err(res) == "CERT_NO_REUSED", res.text
    res = post(
        ahmed,
        db,
        body(
            db,
            "WKR-000003",
            [fit()],
            prov="SALAMA",
            examiner=3,
            source="external_certificate",
            certificate_no="SAL-TEST-26-9999",
            examined=date(2026, 10, 4),
            id_on_card="2000001071",
        ),
    )
    assert err(res) == "CERT_ID_MISMATCH", res.text
    db.expire_all()
    q = select(AuditEntry).where(AuditEntry.details["cert_id_mismatch"].astext == "2*******71")
    assert db.scalar(q) is not None


def test_AC57_sod_submitter_cannot_accept(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    a = ok(
        post(
            huda,
            db,
            body(
                db,
                "WKR-000016",
                [fit()],
                prov="SALAMA",
                examiner=3,
                source="external_certificate",
                certificate_no="SAL-TEST-26-2002",
                examined=date(2026, 10, 4),
            ),
        )
    )
    upload_pdf(huda, "fitness_scan", a["id"])
    ok(act(huda, a["id"], "submit"))
    res = act(huda, a["id"], "accept", clinical_data_present=False)
    assert res.status_code in (403, 409, 422) and err(res) == "SOD_CONFLICT", res.text


def test_AC58_already_expired_and_historic(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    old = date(2026, 9, 15)
    res = post(
        huda,
        db,
        body(
            db,
            "WKR-000016",
            [fit(printed_next_due="2026-09-30")],
            prov="SALAMA",
            examiner=3,
            source="external_certificate",
            certificate_no="SAL-TEST-26-3003",
            examined=old,
        ),
    )
    assert err(res) == "FITNESS_ALREADY_EXPIRED", res.text
    a = ok(
        post(
            huda,
            db,
            body(
                db,
                "WKR-000016",
                [fit(printed_next_due="2026-09-30")],
                prov="SALAMA",
                examiner=3,
                source="external_certificate",
                certificate_no="SAL-TEST-26-3003",
                examined=old,
                historic=True,
            ),
        )
    )
    assert a["historic"] is True
