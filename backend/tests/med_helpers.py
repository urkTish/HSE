"""Helpers for Phase 6a tests (6a-occupational-health Appendix A world, clock 2026-10-06 10:00
Riyadh). Tests use the ``med_seed`` fixture (Phase 0-5 template + the 6a seed, cloned per test)
and ``clock``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FitnessAssessment,
    FitnessHold,
    FitnessReferral,
    MedicalExaminer,
    MedicalProvider,
)
from app.services.med import engine
from tests.cert_helpers import API, CLOCK, P, at, expect, project, riyadh, worker
from tests.train_helpers import kpi

__all__ = [
    "API",
    "CLOCK",
    "P",
    "act",
    "assessment",
    "at",
    "body",
    "check",
    "err",
    "expect",
    "exr",
    "fit",
    "hold",
    "hook",
    "kpi",
    "ok",
    "post",
    "project",
    "provider",
    "reason",
    "referral",
    "riyadh",
    "worker",
]


def provider(db: Session, code: str) -> MedicalProvider:
    pv = db.scalar(select(MedicalProvider).where(MedicalProvider.provider_code == code))
    assert pv is not None, code
    return pv


def assessment(db: Session, no: str) -> FitnessAssessment:
    a = db.scalar(select(FitnessAssessment).where(FitnessAssessment.assessment_no == no))
    assert a is not None, no
    return a


def hold(db: Session, no: str) -> FitnessHold:
    h = db.scalar(select(FitnessHold).where(FitnessHold.hold_no == no))
    assert h is not None, no
    return h


def referral(db: Session, no: str) -> FitnessReferral:
    r = db.scalar(select(FitnessReferral).where(FitnessReferral.referral_no == no))
    assert r is not None, no
    return r


def check(
    db: Session, worker_no: str, code: str, when: datetime | None = None, pcode: str = "ANIA-EXP"
) -> engine.Check:
    from app.services.med import common

    db.expire_all()
    common.clear_cache(db)
    ctx = engine.ctx_for(db, project(db, pcode).id)
    wf = engine.load_one(db, worker(db, worker_no).id)
    return engine.check(ctx, wf, code, when or CLOCK)


def err(res: Any) -> str:
    body = res.json()
    d = body.get("detail", body)
    return str(d.get("code") if isinstance(d, dict) else d)


def exr(db: Session, n: int) -> MedicalExaminer:
    x = db.scalar(select(MedicalExaminer).where(MedicalExaminer.examiner_no == f"EXR-{n:04d}"))
    assert x is not None
    return x


def body(
    db: Session,
    worker_no: str,
    lines: list[dict[str, Any]],
    *,
    prov: str = "SHIFA-ANIA",
    examiner: int = 1,
    examined: date = date(2026, 10, 6),
    source: str = "site_clinic",
    typ: str = "periodic",
    **kw: Any,
) -> dict[str, Any]:
    return {
        "worker_id": str(worker(db, worker_no).id),
        "assessment_type": typ,
        "source": source,
        "provider_id": str(provider(db, prov).id),
        "examiner_id": str(exr(db, examiner).id),
        "examined_on": examined.isoformat(),
        "lines": lines,
        "purpose_notice_given": True,
        **kw,
    }


def fit(code: str = "GEN-FIT", outcome: str = "fit", **kw: Any) -> dict[str, Any]:
    return {"code": code, "outcome": outcome, **kw}


def post(c: Any, db: Session, b: dict[str, Any], pcode: str = "ANIA-EXP") -> Any:
    return c.post(f"{API}/projects/{project(db, pcode).id}/fitness-assessments", json=b)


def ok(res: Any) -> dict[str, Any]:
    assert res.status_code in (200, 201), res.text
    return res.json()  # type: ignore[no-any-return]


def act(c: Any, aid: str, action: str, **kw: Any) -> Any:
    return c.post(f"{API}/fitness-assessments/{aid}/transitions", json={"action": action, **kw})


def hook(
    db: Session, worker_no: str, code: str, when: datetime | None = None, pcode: str = "ANIA-EXP"
) -> Any:
    """The Phase 2 hook item for kind medical_fitness (stage logic applied)."""
    from app.core.access_enums import HookKind, HookSubjectType
    from app.services.access import common as acommon
    from app.services.access import eligibility as elig
    from app.services.access.hooks import HookContext
    from app.services.cert import policy
    from app.services.med import common

    db.expire_all()
    pid = project(db, pcode).id
    policy.clear_cache(db)
    common.clear_cache(db)
    db.info.pop("med_wf", None)
    s = acommon.settings(db, pid)
    return elig.hook_item(
        db, HookSubjectType.worker, worker(db, worker_no).id, HookKind.medical_fitness, code,
        when or CLOCK, s, HookContext(project_id=pid),
    )  # fmt: skip


def reason(it: Any) -> str | None:
    return it.to_schema().model_dump(mode="json").get("hook_reason_code")  # type: ignore[no-any-return]
