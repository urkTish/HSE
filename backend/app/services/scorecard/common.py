"""Helpers shared by the Phase 6g services (spec 6g-scorecard-reports): settings (§3.9 defaults
merged over the stored values), the default profile ORG v1 (§3.10), month helpers, formatting
(K-R8 half-up at output only), scope checks and the helpers re-exported from earlier modules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability, Role
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.scorecard_enums import ScCap, ScGrade, ScMetric, ScModule, ScPillar, ScWindow
from app.models import Project, ProjectEngagement, ScSettings
from app.services.env.common import (
    at_local,
    err,
    local_day,
    make_ca,
    managers,
    need,
    next_seq,
    officers,
    once,
    pcode,
    project,
    reason,
    record,
    reps,
    roles_on,
    send,
    site_engineers,
    to_local,
    tree_of,
    user_ref,
)
from app.services.permissions import Grant, Principal, forbidden_error

__all__ = [
    "at_local",
    "err",
    "local_day",
    "make_ca",
    "managers",
    "need",
    "next_seq",
    "officers",
    "once",
    "pcode",
    "project",
    "reason",
    "record",
    "reps",
    "roles_on",
    "send",
    "site_engineers",
    "to_local",
    "tree_of",
    "user_ref",
]

C = Capability
D = Decimal
ZERO = D(0)
HUNDRED = D(100)

DEFAULTS: dict[str, Any] = {
    "scorecard_min_exposure_hours": 100_000,
    "scorecard_min_coverage_pct": "60.0",
    "scorecard_comment_days": 3,
    "dispute_resolution_days": 3,
    "scorecard_trend_points": "5.0",
    "scorecard_drop_points": "10.0",
    "pip_submit_days": 7,
    "client_report_due_day": 15,
    "external_distribution_enabled": False,
    "external_domains": [],
    "report_languages": "en_ar_separate",
}

# ---- default profile ORG v1 (§3.10) -----------------------------------------------------------

PILLARS: dict[ScPillar, int] = {
    ScPillar.LAG: 30, ScPillar.OBS: 7, ScPillar.CA: 10, ScPillar.PTW: 10, ScPillar.CERT: 8,
    ScPillar.TRN: 7, ScPillar.FIT: 4, ScPillar.HEAT: 4, ScPillar.EMG: 4, ScPillar.INS: 7,
    ScPillar.TBT: 3, ScPillar.ENV: 3, ScPillar.NOT: 3,
}  # fmt: skip

W = ScWindow
P = ScPillar


@dataclass(frozen=True)
class MetricDef:
    code: ScMetric
    pillar: ScPillar
    kpi: str
    window: ScWindow
    good: str
    bad: str
    min_volume: int
    weight: str
    module: ScModule
    canonical_base: int | None = None  # rate metrics: anchors per this base (SP-4)


M_ = MetricDef
SM = ScMetric
METRICS: list[MetricDef] = [
    M_(SM.TRIR, P.LAG, "K-21", W.r12_rate, "0.00", "1.00", 0, "12", ScModule.phase1, 200_000),
    M_(SM.LTIFR, P.LAG, "K-20", W.r12_rate, "0.00", "2.00", 0, "8", ScModule.phase1, 1_000_000),
    M_(SM.LTISR, P.LAG, "K-23", W.r12_rate, "0.00", "20.00", 0, "5", ScModule.phase1, 200_000),
    M_(SM.HIPO, P.LAG, "K-44", W.r12_rate, "0.00", "1.00", 0, "5", ScModule.phase1, 200_000),
    M_(SM.OBS, P.OBS, "K-32", W.month, "100", "20", 0, "4", ScModule.phase1, 200_000),
    M_(SM.UNSAFE_CLOSE, P.OBS, "K-33", W.month, "95.0", "50.0", 5, "3", ScModule.phase1),
    M_(SM.CA_ONTIME, P.CA, "K-41", W.month, "95.0", "60.0", 5, "6", ScModule.phase1),
    M_(SM.CA_OVERDUE, P.CA, "K-42", W.month, "0.0", "2.0", 0, "4", ScModule.phase1),
    M_(SM.PTW_AUDIT, P.PTW, "K-61", W.month, "100.0", "80.0", 3, "5", ScModule.ptw),
    M_(SM.PTW_CRIT, P.PTW, "K-64", W.month, "0.0", "10.0", 3, "3", ScModule.ptw),
    M_(SM.PTW_CLOSE, P.PTW, "K-69", W.month, "100.0", "80.0", 5, "2", ScModule.ptw),
    M_(SM.EQ_CERT, P.CERT, "K-72", W.month_end, "100.0", "80.0", 3, "3", ScModule.cert),
    M_(SM.PERS_CERT, P.CERT, "K-76", W.month_end, "100.0", "80.0", 5, "3", ScModule.cert),
    M_(SM.SCAF_TAG, P.CERT, "K-81", W.month_end, "100.0", "80.0", 3, "2", ScModule.cert),
    M_(SM.TRAIN, P.TRN, "K-82", W.month_end, "100.0", "80.0", 10, "5", ScModule.training),
    M_(SM.INDUCT, P.TRN, "K-49", W.month_end, "100.0", "80.0", 5, "2", ScModule.access),
    M_(SM.FIT, P.FIT, "K-89", W.month_end, "100.0", "80.0", 10, "4", ScModule.medical),
    M_(SM.HEAT_WELF, P.HEAT, "K-101", W.month, "100.0", "80.0", 10, "2", ScModule.heat),
    M_(SM.HEAT_BAN, P.HEAT, "K-100", W.month, "0.0", "5.0", 5, "2", ScModule.heat),
    M_(SM.EMG_COVER, P.EMG, "K-106", W.month, "100.0", "80.0", 1, "2", ScModule.emergency),
    M_(SM.EMG_EQUIP, P.EMG, "K-107", W.month_end, "100.0", "80.0", 3, "2", ScModule.emergency),
    M_(SM.CHECKLIST, P.INS, "K-110", W.month, "95.0", "75.0", 3, "3", ScModule.field),
    M_(SM.INSP_COVER, P.INS, "K-113", W.month, "100.0", "70.0", 1, "2", ScModule.field),
    M_(SM.AUDIT, P.INS, "K-115", W.latest_3m, "90.0", "60.0", 1, "2", ScModule.field),
    M_(SM.TBT, P.TBT, "K-116", W.month, "95.0", "60.0", 1, "3", ScModule.toolbox),
    M_(SM.WASTE_COC, P.ENV, "K-121", W.month, "100.0", "80.0", 3, "1", ScModule.env),
    M_(SM.SPILL, P.ENV, "K-124", W.r12_rate, "0.00", "1.00", 0, "2", ScModule.env, 200_000),
    M_(SM.NOTIF, P.NOT, "K-127", W.month, "100.0", "80.0", 3, "2", ScModule.followup),
    M_(SM.LESSON_ACK, P.NOT, "K-130", W.month, "100.0", "50.0", 3, "1", ScModule.followup),
]
METRIC_BY_CODE: dict[str, MetricDef] = {m.code.value: m for m in METRICS}
CAPS: list[tuple[ScCap, ScGrade]] = [
    (ScCap.CP1, ScGrade.D), (ScCap.CP2, ScGrade.C), (ScCap.CP3, ScGrade.B),
]  # fmt: skip
BANDS: list[tuple[ScGrade, str]] = [(ScGrade.A, "90.0"), (ScGrade.B, "75.0"), (ScGrade.C, "60.0")]
GRADE_ORDER = {ScGrade.A: 4, ScGrade.B: 3, ScGrade.C: 2, ScGrade.D: 1}


def default_profile_json() -> dict[str, Any]:
    return {
        "pillars": [{"pillar_code": p.value, "weight": str(w)} for p, w in PILLARS.items()],
        "metrics": [
            {
                "metric_code": m.code.value,
                "pillar_code": m.pillar.value,
                "kpi_ref": m.kpi,
                "window": m.window.value,
                "weight": m.weight,
                "good": m.good,
                "bad": m.bad,
                "min_volume": m.min_volume,
                "enabled": True,
            }
            for m in METRICS
        ],
        "caps": [{"cap_code": c.value, "max_grade": g.value, "enabled": True} for c, g in CAPS],
        "bands": [{"grade": g.value, "min_score": s} for g, s in BANDS],
    }


# ---- settings ----------------------------------------------------------------------------------


@dataclass
class Cfg:
    project_id: uuid.UUID
    from_month: date | None
    live_from: dict[str, str | None]
    confirmed: bool
    v: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    def live(self, module: ScModule, month: date) -> bool:
        """SN-5: the module's date is set and on or before the first day of the month."""
        if module == ScModule.phase1:
            return True
        raw = self.live_from.get(module.value)
        return raw is not None and date.fromisoformat(raw) <= month


def settings_row(db: Session, project_id: uuid.UUID) -> ScSettings:
    s = db.get(ScSettings, project_id)
    if s is None:
        s = ScSettings(project_id=project_id, values={}, source_live_from={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    s = db.get(ScSettings, project_id)
    return Cfg(
        project_id,
        s.scorecard_from_month if s else None,
        dict(s.source_live_from or {}) if s else {},
        bool(s and s.sources_confirmed_at),
        {**DEFAULTS, **((s.values or {}) if s else {})},
    )


# ---- months and numbers --------------------------------------------------------------------------


def parse_month(value: str, field: str = "month") -> date:
    try:
        y, m = value.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError) as exc:
        raise validation_error(field, "Give a month as yyyy-mm.") from exc


def mkey(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_end(d: date) -> date:
    return add_months(d, 1) - timedelta(days=1)


def end_of_day(d: date) -> datetime:
    """23:59:59 local of the day, as an aware datetime."""
    return at_local(d, "23:59") + timedelta(seconds=59)


def local_dt(d: date, t: time) -> datetime:
    return at_local(d, t.strftime("%H:%M"))


def q(v: Decimal | None, places: str) -> Decimal | None:
    return None if v is None else D(v).quantize(D(places), rounding=ROUND_HALF_UP)


def s(v: Decimal | int | None) -> str | None:
    """Unrounded decimal string (normalised, no exponent)."""
    if v is None:
        return None
    x = D(v)
    return format(x.normalize(), "f") if x == x.to_integral() else format(x, "f")


def d1(v: Decimal | None) -> str:
    r = q(v, "0.1")
    return "—" if r is None else str(r)


def d2(v: Decimal | None) -> str:
    r = q(v, "0.01")
    return "—" if r is None else str(r)


def d4(v: Decimal | None) -> str:
    r = q(v, "0.0001")
    return "—" if r is None else str(r)


def ref_no(prefix: str, code: str, year: int, seq: int, width: int) -> str:
    return f"{prefix}-{code}-{year}-{seq:0{width}d}"


def code_err(code: ErrorCode, en: str, ar: str, field: str | None = None, **meta: Any) -> ApiError:
    return err(422, code, en, ar, field, **meta)


# ---- engagements and scope -------------------------------------------------------------------


def eng(db: Session, eng_id: uuid.UUID) -> ProjectEngagement:
    e = db.get(ProjectEngagement, eng_id)
    if e is None:
        raise validation_error("engagement_id", "Unknown engagement.")
    return e


def eng_code(db: Session, eng_id: uuid.UUID | None) -> str:
    e = db.get(ProjectEngagement, eng_id) if eng_id else None
    return e.contractor.short_code if e is not None and e.contractor is not None else "—"


def descendants(db: Session, eng_id: uuid.UUID) -> set[uuid.UUID]:
    from app.services.permissions import engagement_descendants  # noqa: PLC0415

    return engagement_descendants(db, eng_id)


def has_children(db: Session, eng_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(ProjectEngagement.id).where(ProjectEngagement.parent_engagement_id == eng_id)
        )
        is not None
    )


def view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Grant:
    project(db, p, project_id)
    return need(p, project_id, C.scorecard_view, write=False)


def is_viewer(p: Principal, project_id: uuid.UUID) -> bool:
    if p.is_manager:
        return False
    sc = p.projects.get(project_id)
    return sc is not None and sc.read_only


def is_site_engineer(db: Session, p: Principal, project_id: uuid.UUID) -> bool:
    if p.is_manager:
        return False
    roles = roles_on(db, p.user.id, project_id)
    return Role.site_engineer in roles and not roles & {Role.hse_officer}


def staff(db: Session, p: Principal, project_id: uuid.UUID) -> bool:
    return p.is_manager or Role.hse_officer in roles_on(db, p.user.id, project_id)


def require_manager(p: Principal) -> None:
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager may do this.")


def project_by_id(db: Session, project_id: uuid.UUID) -> Project:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return pr
