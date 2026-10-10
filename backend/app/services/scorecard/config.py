"""6g reference lists, project settings (§3.9) and scorecard profiles (§3.1, SP-1…SP-5)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, ProjectStatus
from app.core.errors import ErrorCode, not_found
from app.core.scorecard_enums import (
    RpLanguages,
    ScCardStatus,
    ScModule,
    ScProfileStatus,
)
from app.models import Project, ScCard, ScProfile
from app.schemas.common import Page
from app.schemas.scorecard import (
    ScBand,
    ScCapConfig,
    ScMetricConfig,
    ScPillarWeight,
    ScProfileCreate,
    ScProfilePage,
    ScProfileRead,
    ScProfileUpdate,
    ScReference,
    ScRefItem,
    ScSettingsRead,
    ScSettingsUpdate,
)
from app.services.permissions import Principal, forbidden_error
from app.services.scorecard import common as cm
from app.services.scorecard.labels import LISTS

D = Decimal
ORG = "ORG"
ORG_FROM = date(2020, 1, 1)


def reference() -> ScReference:
    return ScReference(
        lists={
            k: [ScRefItem(code=c, label_en=en, label_ar=ar, detail=det) for c, en, ar, det in v]
            for k, v in LISTS.items()
        }
    )


# ---- settings ------------------------------------------------------------------------------------

RANGES: dict[str, tuple[Any, Any]] = {
    "scorecard_min_exposure_hours": (50_000, 1_000_000),
    "scorecard_min_coverage_pct": (D("50.0"), D("90.0")),
    "scorecard_comment_days": (2, 10),
    "dispute_resolution_days": (1, 10),
    "scorecard_trend_points": (D("2.0"), D("15.0")),
    "scorecard_drop_points": (D("5.0"), D("25.0")),
    "pip_submit_days": (3, 14),
}


def _out_of_range(field: str) -> Exception:
    return cm.code_err(
        ErrorCode.SETTING_OUT_OF_RANGE,
        f"{field} is outside the allowed range (§3.9).",
        "القيمة خارج النطاق المسموح.",
        field,
    )


def _read(db: Session, project_id: uuid.UUID) -> ScSettingsRead:
    s = cm.settings_row(db, project_id)
    c = cm.cfg(db, project_id)
    live = {m: (date.fromisoformat(v) if (v := c.live_from.get(m.value)) else None)
            for m in ScModule if m != ScModule.phase1}  # fmt: skip
    return ScSettingsRead(
        project_id=project_id,
        scorecard_from_month=cm.mkey(s.scorecard_from_month) if s.scorecard_from_month else None,
        source_live_from=live,
        sources_confirmed_at=s.sources_confirmed_at,
        scorecard_min_exposure_hours=int(c["scorecard_min_exposure_hours"]),
        scorecard_min_coverage_pct=str(c["scorecard_min_coverage_pct"]),
        scorecard_comment_days=int(c["scorecard_comment_days"]),
        dispute_resolution_days=int(c["dispute_resolution_days"]),
        scorecard_trend_points=str(c["scorecard_trend_points"]),
        scorecard_drop_points=str(c["scorecard_drop_points"]),
        pip_submit_days=int(c["pip_submit_days"]),
        client_report_due_day=int(c["client_report_due_day"]),
        external_distribution_enabled=bool(c["external_distribution_enabled"]),
        external_domains=list(c["external_domains"]),
        report_languages=RpLanguages(c["report_languages"]),
        updated_at=s.updated_at,
    )


def get_settings(db: Session, p: Principal, project_id: uuid.UUID) -> ScSettingsRead:
    cm.project(db, p, project_id)
    if not p.is_manager:
        cm.need(p, project_id, cm.C.scorecard_view, write=False)
    return _read(db, project_id)


def _first_final(db: Session, project_id: uuid.UUID) -> date | None:
    return db.scalar(
        select(func.min(ScCard.month)).where(
            ScCard.project_id == project_id,
            ScCard.status.in_([ScCardStatus.final, ScCardStatus.superseded]),
        )
    )


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: ScSettingsUpdate
) -> ScSettingsRead:
    pr = cm.project(db, p, project_id)
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager edits 6g settings (225).")
    p.require(project_id, cm.C.scorecard_settings)
    s = cm.settings_row(db, project_id)
    before = {"values": dict(s.values or {}), "source_live_from": dict(s.source_live_from or {}),
              "scorecard_from_month": str(s.scorecard_from_month)}  # fmt: skip
    data = body.model_dump(exclude_unset=True)
    vals = dict(s.values or {})
    for k, (lo, hi) in RANGES.items():
        if k in data and data[k] is not None:
            try:
                v = D(str(data[k])) if isinstance(lo, Decimal) else int(data[k])
            except (InvalidOperation, ValueError) as exc:
                raise _out_of_range(k) from exc
            if not lo <= v <= hi:
                raise _out_of_range(k)
            vals[k] = str(v) if isinstance(lo, Decimal) else v
    if data.get("client_report_due_day") is not None:
        from app.services import hse_settings  # noqa: PLC0415

        lock = hse_settings.get(db, project_id).month_lock_day
        v = int(data["client_report_due_day"])
        if not lock + 1 <= v <= 28:
            raise _out_of_range("client_report_due_day")
        vals["client_report_due_day"] = v
    if "external_domains" in data and data["external_domains"] is not None:
        doms = [d.strip().lower() for d in data["external_domains"]]
        if any("@" in d or "." not in d or " " in d for d in doms):
            raise _out_of_range("external_domains")
        vals["external_domains"] = doms
    if data.get("external_distribution_enabled") is not None:
        vals["external_distribution_enabled"] = bool(data["external_distribution_enabled"])
    if vals.get("external_distribution_enabled") and not vals.get("external_domains"):
        raise _out_of_range("external_domains")
    if data.get("report_languages") is not None:
        vals["report_languages"] = RpLanguages(data["report_languages"]).value
    if data.get("scorecard_from_month") is not None:
        m = cm.parse_month(data["scorecard_from_month"], "scorecard_from_month")
        if m < pr.start_date.replace(day=1):
            raise _out_of_range("scorecard_from_month")
        first = _first_final(db, project_id)
        if (
            first is not None
            and s.scorecard_from_month is not None
            and (m > s.scorecard_from_month)
        ):
            raise _out_of_range("scorecard_from_month")
        s.scorecard_from_month = m
    if data.get("source_live_from") is not None:
        live = dict(s.source_live_from or {})
        for k, v in data["source_live_from"].items():
            live[ScModule(k).value] = v.isoformat() if v else None
        s.source_live_from = live
        s.sources_confirmed_at = None
    s.values = vals
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    from app.services import audit  # noqa: PLC0415

    audit.record(
        db, AuditAction.settings_changed, p.actor(project_id),
        entity_type=EntityType.scorecard_settings, project_id=project_id, before=before,
        after={"values": vals, "source_live_from": dict(s.source_live_from or {}),
               "scorecard_from_month": str(s.scorecard_from_month)},
    )  # fmt: skip
    db.flush()
    return _read(db, project_id)


def confirm_sources(db: Session, p: Principal, project_id: uuid.UUID) -> ScSettingsRead:
    cm.project(db, p, project_id)
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager confirms the sources (225).")
    s = cm.settings_row(db, project_id)
    s.sources_confirmed_at = now()
    s.sources_confirmed_by_user_id = p.user.id
    cm.record(db, p, AuditAction.update, EntityType.scorecard_settings, s, project_id,
              details={"sources_confirmed": True})  # fmt: skip
    db.flush()
    return _read(db, project_id)


def prefill_sources(db: Session, project_id: uuid.UUID) -> dict[str, str | None]:
    """SN-5 prefill: the module's own switch where one exists, else the first day of the month
    after the module's first record on the project (null when there is none)."""
    from app.models import (  # noqa: PLC0415
        BanPatrol,
        ChecklistResponse,
        Deployment,
        Drill,
        EquipmentDeployment,
        FieldSettings,
        FitnessAssessment,
        FuSettings,
        HseSettings,
        Permit,
        TrainingRecord,
        WasteConsignment,
    )

    hse = db.get(HseSettings, project_id)
    fus = db.get(FuSettings, project_id)

    def after_first(model: Any, col: Any) -> str | None:
        first = db.scalar(select(func.min(col)).where(model.project_id == project_id))
        if first is None:
            return None
        d = first.date() if hasattr(first, "date") and callable(first.date) else first
        return cm.add_months(d.replace(day=1), 1).isoformat()

    fs = db.get(FieldSettings, project_id)
    tb_from = fs.toolbox_register_from if fs is not None else None
    return {
        ScModule.access.value: (hse.induction_register_from.isoformat()
                                if hse and hse.induction_register_from
                                else after_first(Deployment, Deployment.created_at)),
        ScModule.ptw.value: after_first(Permit, Permit.created_at),
        ScModule.cert.value: after_first(EquipmentDeployment, EquipmentDeployment.created_at),
        ScModule.training.value: after_first(TrainingRecord, TrainingRecord.created_at),
        ScModule.medical.value: after_first(FitnessAssessment, FitnessAssessment.created_at),
        ScModule.heat.value: after_first(BanPatrol, BanPatrol.created_at),
        ScModule.emergency.value: after_first(Drill, Drill.created_at),
        ScModule.field.value: after_first(ChecklistResponse, ChecklistResponse.created_at),
        ScModule.toolbox.value: tb_from.isoformat() if isinstance(tb_from, date) else None,
        ScModule.env.value: after_first(WasteConsignment, WasteConsignment.created_at),
        ScModule.followup.value: (fus.followup_rules_from.isoformat()
                                  if fus and fus.followup_rules_from else None),
    }  # fmt: skip


# ---- profiles ------------------------------------------------------------------------------------


def ensure_org(db: Session) -> ScProfile:
    pr = db.scalar(
        select(ScProfile)
        .where(ScProfile.profile_code == ORG, ScProfile.activated_at.is_not(None))
        .order_by(ScProfile.version.desc())
    )
    if pr is None:
        js = cm.default_profile_json()
        pr = ScProfile(
            project_id=None, profile_code=ORG, version=1, effective_from_month=ORG_FROM,
            status=ScProfileStatus.active, activated_at=now(), **js,
        )  # fmt: skip
        db.add(pr)
        db.flush()
    return pr


def profile_for(db: Session, project: Project, month: date) -> ScProfile:
    """The profile in force for the month: the project's own activated versions first, else ORG
    (latest activated version with effective_from_month ≤ month)."""
    ensure_org(db)
    for code in (project.code, ORG):
        pr = db.scalar(
            select(ScProfile)
            .where(
                ScProfile.profile_code == code,
                ScProfile.activated_at.is_not(None),
                ScProfile.effective_from_month <= month,
            )
            .order_by(ScProfile.version.desc())
        )
        if pr is not None:
            return pr
    return ensure_org(db)


def to_read(x: ScProfile) -> ScProfileRead:
    return ScProfileRead(
        id=x.id, project_id=x.project_id, profile_code=x.profile_code, version=x.version,
        effective_from_month=cm.mkey(x.effective_from_month),
        pillars=[ScPillarWeight(**p) for p in x.pillars],
        metrics=[ScMetricConfig(**m) for m in x.metrics],
        caps=[ScCapConfig(**c) for c in x.caps], bands=[ScBand(**b) for b in x.bands],
        status=x.status, activated_at=x.activated_at,
    )  # fmt: skip


def _visible(db: Session, p: Principal, x: ScProfile) -> None:
    if p.is_manager:
        return
    if x.project_id is not None:
        if p.grant(x.project_id, cm.C.scorecard_view) is None:
            raise not_found("Profile")
        return
    if not any(p.grant(pid, cm.C.scorecard_view) for pid in p.projects):
        raise not_found("Profile")


def list_profiles(
    db: Session, p: Principal, project_id: uuid.UUID | None, page: int, size: int
) -> ScProfilePage:
    ensure_org(db)
    stmt = select(ScProfile).order_by(ScProfile.profile_code, ScProfile.version)
    if project_id is not None:
        stmt = stmt.where((ScProfile.project_id == project_id) | ScProfile.project_id.is_(None))
    rows = []
    for x in db.scalars(stmt):
        try:
            _visible(db, p, x)
        except Exception:  # noqa: S112
            continue
        rows.append(x)
    items = rows[(page - 1) * size : page * size]
    return ScProfilePage(items=[to_read(x) for x in items], total=len(rows), page=page,
                         page_size=size)  # fmt: skip


def get_profile(db: Session, p: Principal, profile_id: uuid.UUID) -> ScProfileRead:
    x = db.get(ScProfile, profile_id)
    if x is None:
        raise not_found("Profile")
    _visible(db, p, x)
    return to_read(x)


def _manager(p: Principal) -> None:
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager edits scorecard profiles (225).")


def create_profile(db: Session, p: Principal, body: ScProfileCreate) -> ScProfileRead:
    _manager(p)
    org = ensure_org(db)
    code = ORG
    if body.project_id is not None:
        pr = db.get(Project, body.project_id)
        if pr is None:
            raise not_found("Project")
        code = pr.code
    if db.scalar(
        select(ScProfile.id).where(
            ScProfile.profile_code == code, ScProfile.status == ScProfileStatus.draft
        )
    ):
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "A Draft version already exists.",
                     "توجد مسودة بالفعل.")  # fmt: skip
    src = (
        db.scalar(
            select(ScProfile)
            .where(ScProfile.profile_code == code, ScProfile.activated_at.is_not(None))
            .order_by(ScProfile.version.desc())
        )
        or org
    )
    last = db.scalar(select(func.max(ScProfile.version)).where(ScProfile.profile_code == code))
    x = ScProfile(
        project_id=body.project_id, profile_code=code, version=(last or 0) + 1,
        effective_from_month=cm.add_months(cm.local_day().replace(day=1), 1),
        pillars=[dict(v) for v in src.pillars], metrics=[dict(v) for v in src.metrics],
        caps=[dict(v) for v in src.caps], bands=[dict(v) for v in src.bands],
        status=ScProfileStatus.draft, created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(x)
    db.flush()
    cm.record(db, p, AuditAction.create, EntityType.scorecard_profile, x, body.project_id)
    return to_read(x)


def _draft(db: Session, p: Principal, profile_id: uuid.UUID) -> ScProfile:
    _manager(p)
    x = db.get(ScProfile, profile_id)
    if x is None:
        raise not_found("Profile")
    if x.status != ScProfileStatus.draft:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION,
                     "Profile versions are immutable once active (SP-1).",
                     "إصدارات الملف لا تُعدّل بعد التفعيل.")  # fmt: skip
    return x


def update_profile(
    db: Session, p: Principal, profile_id: uuid.UUID, body: ScProfileUpdate
) -> ScProfileRead:
    x = _draft(db, p, profile_id)
    before = {"pillars": x.pillars, "metrics": x.metrics, "caps": x.caps, "bands": x.bands}
    if body.effective_from_month is not None:
        x.effective_from_month = cm.parse_month(body.effective_from_month, "effective_from_month")
    if body.pillars is not None:
        x.pillars = [{"pillar_code": pw.pillar_code.value, "weight": pw.weight}
                     for pw in body.pillars]  # fmt: skip
    if body.metrics is not None:
        by = {m["metric_code"]: dict(m) for m in x.metrics}
        for mp in body.metrics:
            if mp.metric_code not in by:
                raise cm.code_err(ErrorCode.VALIDATION_ERROR, "Only list SM metrics (SP-2).",
                                  "مقاييس القائمة فقط.", "metrics")  # fmt: skip
            for k in ("weight", "good", "bad", "min_volume", "enabled"):
                v = getattr(mp, k)
                if v is not None:
                    by[mp.metric_code][k] = v
        x.metrics = list(by.values())
    if body.caps is not None:
        x.caps = [{"cap_code": c.cap_code.value, "max_grade": c.max_grade.value,
                   "enabled": c.enabled} for c in body.caps]  # fmt: skip
    if body.bands is not None:
        x.bands = [{"grade": b.grade.value, "min_score": b.min_score} for b in body.bands]
    x.updated_by_user_id = p.user.id
    cm.record(db, p, AuditAction.update, EntityType.scorecard_profile, x, x.project_id,
              before=before)  # fmt: skip
    db.flush()
    return to_read(x)


def validate(x: ScProfile) -> None:
    """SP-1 / SP-3 checks at activation."""
    pw = {p["pillar_code"]: D(str(p["weight"])) for p in x.pillars}
    if sum(pw.values(), D(0)) != D(100):
        raise cm.code_err(ErrorCode.WEIGHTS_NOT_100, "Pillar weights must sum to 100.0.",
                          "يجب أن يكون مجموع أوزان المحاور 100.", "pillars")  # fmt: skip
    for pc, w in pw.items():
        mw = sum((D(str(m["weight"])) for m in x.metrics if m["pillar_code"] == pc), D(0))
        if mw != w:
            raise cm.code_err(
                ErrorCode.WEIGHTS_NOT_100,
                f"Metric weights of {pc} must sum to the pillar weight.",
                "يجب أن يساوي مجموع أوزان المقاييس وزن المحور.",
                "metrics",
            )
    for m in x.metrics:
        if not D("0.5") <= D(str(m["weight"])) <= D("30.0") or D(str(m["good"])) == D(
            str(m["bad"])
        ):
            raise cm.code_err(ErrorCode.VALIDATION_ERROR,
                              f"{m['metric_code']}: weight 0.5-30.0 and good ≠ bad.",
                              "الوزن بين 0.5 و30 والمرساتان مختلفتان.", "metrics")  # fmt: skip
    lag = pw.get("LAG", D(0))
    trir = next((m for m in x.metrics if m["metric_code"] == "SM-TRIR"), None)
    if not D(20) <= lag <= D(50) or trir is None or not trir.get("enabled", True):
        raise cm.code_err(ErrorCode.LAGGING_WEIGHT_OUT_OF_RANGE,
                          "The LAG pillar weight must be 20.0-50.0 and SM-TRIR enabled (SP-3).",
                          "وزن المؤشرات المتأخرة بين 20 و50.", "pillars")  # fmt: skip
    cp1 = next((c for c in x.caps if c["cap_code"] == "CP-1"), None)
    if cp1 is None or not cp1.get("enabled") or cp1.get("max_grade") != "D":
        raise cm.code_err(ErrorCode.CAP_REQUIRED, "CP-1 must stay enabled with max grade D.",
                          "يجب أن يبقى الحد CP-1 مفعلاً.", "caps")  # fmt: skip


def activate_profile(db: Session, p: Principal, profile_id: uuid.UUID) -> ScProfileRead:
    x = _draft(db, p, profile_id)
    validate(x)
    projects = (
        [x.project_id]
        if x.project_id is not None
        else list(db.scalars(select(Project.id).where(Project.status != ProjectStatus.closed)))
    )
    for pid in projects:
        last_final = db.scalar(
            select(func.max(ScCard.month)).where(
                ScCard.project_id == pid, ScCard.status == ScCardStatus.final
            )
        )
        if last_final is not None and x.effective_from_month <= last_final:
            raise cm.code_err(
                ErrorCode.PROFILE_BACKDATED,
                f"{cm.mkey(last_final)} is already Final: the version must start later.",
                "الشهر معتمد بالفعل: يجب أن يبدأ الإصدار لاحقاً.", "effective_from_month",
            )  # fmt: skip
    for old in db.scalars(
        select(ScProfile).where(
            ScProfile.profile_code == x.profile_code, ScProfile.status == ScProfileStatus.active
        )
    ):
        old.status = ScProfileStatus.retired
    x.status = ScProfileStatus.active
    x.activated_at = now()
    cm.record(db, p, AuditAction.status_change, EntityType.scorecard_profile, x, x.project_id)
    db.flush()
    return to_read(x)


def page_of(cls: Any, rows: list[Any], page: int, size: int) -> Any:
    return cls(items=rows[(page - 1) * size : page * size], total=len(rows), page=page,
               page_size=size)  # fmt: skip


__all__ = ["Page"]
