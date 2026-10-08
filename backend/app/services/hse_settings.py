"""Phase 1 project settings (spec 1-dashboard §3.10), KPI targets, AI transfer approval (AI-14)
and reference lists (§3.11)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, not_found, not_implemented, validation_error
from app.core.hse_enums import CaPriority, ReferenceList, TreatmentClass
from app.data.reference import OFF_POINTS, REFERENCE
from app.models import HseSettings, ReferenceItem, User
from app.schemas.hse_common import UserRef
from app.schemas.hse_settings import (
    AiTransferApprovalCreate,
    AiTransferApprovalRead,
    HeatSeason,
    HseSettingsRead,
    HseSettingsUpdate,
    ReferenceItemRead,
    ReferenceItemUpdate,
    ReferenceListRead,
    ReferenceListsRead,
)
from app.services import audit, projects
from app.services.permissions import Principal

DEFAULT_CA_DUE_DAYS = {
    CaPriority.critical.value: 1,
    CaPriority.high.value: 7,
    CaPriority.medium.value: 14,
    CaPriority.low.value: 30,
}


def get(db: Session, project_id: uuid.UUID) -> HseSettings:
    """The project's Phase 1 settings; a row with the §3.10 defaults is created on first use."""
    s = db.get(HseSettings, project_id)
    if s is None:
        s = HseSettings(project_id=project_id, ca_due_days=dict(DEFAULT_CA_DUE_DAYS))
        for col in HseSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                if not callable(arg):
                    setattr(s, col.key, arg)
        if not s.kpi_targets:
            s.kpi_targets = {}
        db.add(s)
        db.flush()
    return s


def ca_due_days(s: HseSettings, priority: CaPriority) -> int:
    return int((s.ca_due_days or DEFAULT_CA_DUE_DAYS).get(priority.value, 14))


def _user_ref(db: Session, user_id: uuid.UUID | None) -> UserRef | None:
    if user_id is None:
        return None
    u = db.get(User, user_id)
    if u is None:
        return None
    return UserRef(id=u.id, full_name_en=u.full_name_en, full_name_ar=u.full_name_ar)


def to_read(db: Session, s: HseSettings) -> HseSettingsRead:
    approval = None
    if s.ai_approved_on is not None:
        recorder = _user_ref(db, s.ai_approval_recorded_by)
        approval = AiTransferApprovalRead(
            approved_on=s.ai_approved_on,
            approver_name=s.ai_approver_name or "",
            approver_organisation=s.ai_approver_organisation or "",
            reference=s.ai_approval_reference,
            notes=s.ai_approval_notes,
            recorded_by=recorder or UserRef(id=uuid.UUID(int=0), full_name_en="—"),
            recorded_at=s.ai_approval_recorded_at or now(),
        )
    return HseSettingsRead(
        project_id=s.project_id,
        lost_days_cap=s.lost_days_cap,
        fatality_lost_days_charge=s.fatality_lost_days_charge,
        include_commuting_in_rates=s.include_commuting_in_rates,
        include_non_contractor_cases_in_rates=s.include_non_contractor_cases_in_rates,
        max_hours_per_person_day=s.max_hours_per_person_day,
        warn_hours_per_person_day=s.warn_hours_per_person_day,
        daily_return_deadline=s.daily_return_deadline,
        completeness_threshold_pct=s.completeness_threshold_pct,
        inspection_grace_days=s.inspection_grace_days,
        ca_due_days={CaPriority(k): v for k, v in (s.ca_due_days or DEFAULT_CA_DUE_DAYS).items()},
        ca_max_extensions=s.ca_max_extensions,
        new_starter_days=s.new_starter_days,
        heat_season=HeatSeason(start=s.heat_season_start, end=s.heat_season_end),
        low_exposure_hours=s.low_exposure_hours,
        leading_warning_drop_pct=s.leading_warning_drop_pct,
        leading_warning_rise_pct=s.leading_warning_rise_pct,
        kpi_targets=dict(s.kpi_targets or {}),
        month_lock_day=s.month_lock_day,
        injury_identity_retention_years=s.injury_identity_retention_years,
        induction_register_from=s.induction_register_from,
        ai_enabled=s.ai_enabled,
        ai_requested=s.ai_requested,
        ai_transfer_approval=approval,
        updated_at=s.updated_at,
        updated_by=_user_ref(db, s.updated_by_user_id),
    )


def _snapshot(s: HseSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in HseSettings.__table__.columns:
        v = getattr(s, col.key)
        out[col.key] = v if isinstance(v, int | bool | str | dict | list) or v is None else str(v)
    return out


def read(db: Session, p: Principal, project_id: uuid.UUID) -> HseSettingsRead:
    project = projects.get_visible(db, p, project_id)
    return to_read(db, get(db, project.id))


def update(
    db: Session, p: Principal, project_id: uuid.UUID, body: HseSettingsUpdate
) -> HseSettingsRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, Capability.hse_settings_edit)
    s = get(db, project.id)
    before = _snapshot(s)
    data = body.model_dump(exclude_unset=True)
    if "lost_days_cap" in data and data["lost_days_cap"] not in (0, 180):
        raise validation_error("lost_days_cap", "lost_days_cap must be 180 or 0.")
    if "fatality_lost_days_charge" in data and data["fatality_lost_days_charge"] not in (0, 6000):
        raise validation_error("fatality_lost_days_charge", "Must be 0 or 6000.")
    if "ca_due_days" in data:
        cdd = {CaPriority(k).value: int(v) for k, v in data.pop("ca_due_days").items()}
        if set(cdd) != {c.value for c in CaPriority} or not all(1 <= v <= 90 for v in cdd.values()):
            raise validation_error("ca_due_days", "Give all four priorities, each 1-90 days.")
        s.ca_due_days = cdd
    if "heat_season" in data:
        hs = data.pop("heat_season")
        s.heat_season_start, s.heat_season_end = hs["start"], hs["end"]
    if "kpi_targets" in data:
        s.kpi_targets = {str(k): str(v) for k, v in data.pop("kpi_targets").items()}
    if "ai_enabled" in data:
        want = bool(data.pop("ai_enabled"))
        if want and s.ai_approved_on is None:
            raise ApiError(
                409,
                ErrorCode.AI_TRANSFER_APPROVAL_REQUIRED,
                "Record the client's approval of the AI data transfer before enabling AI.",
                "يجب تسجيل موافقة العميل على نقل البيانات قبل تفعيل المساعد الذكي.",
            )
        s.ai_requested = want
    if data.pop("training_register_from", None) is not None:
        # 5-training TH-6: stored from Phase 5 stage 2 (contract v0.6.0 stage 1: null is a no-op).
        raise not_implemented()
    reg = data.get("induction_register_from")
    if reg is not None and project.start_date is not None and reg < project.start_date:
        raise validation_error(
            "induction_register_from", "The date must be on or after the project start date."
        )
    for k, v in data.items():
        setattr(s, k, v)
    if s.warn_hours_per_person_day > s.max_hours_per_person_day:
        raise validation_error(
            "warn_hours_per_person_day", "Warning threshold cannot exceed the maximum."
        )
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.hse_settings,
        entity_id=project.id,
        project_id=project.id,
        before=before,
        after=_snapshot(s),
    )
    return to_read(db, s)


def record_approval(
    db: Session, p: Principal, project_id: uuid.UUID, body: AiTransferApprovalCreate
) -> HseSettingsRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, Capability.hse_settings_edit)
    s = get(db, project.id)
    before = _snapshot(s)
    s.ai_approved_on = body.approved_on
    s.ai_approver_name = body.approver_name
    s.ai_approver_organisation = body.approver_organisation
    s.ai_approval_reference = body.reference
    s.ai_approval_notes = body.notes
    s.ai_approval_recorded_by = p.user.id
    s.ai_approval_recorded_at = now()
    s.ai_requested = True
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.hse_settings,
        entity_id=project.id,
        project_id=project.id,
        before=before,
        after=_snapshot(s),
        details={"ai_transfer_approval": "recorded"},
    )
    return to_read(db, s)


def withdraw_approval(db: Session, p: Principal, project_id: uuid.UUID) -> HseSettingsRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, Capability.hse_settings_edit)
    s = get(db, project.id)
    before = _snapshot(s)
    s.ai_approved_on = None
    s.ai_approver_name = s.ai_approver_organisation = None
    s.ai_approval_reference = s.ai_approval_notes = None
    s.ai_approval_recorded_by = None
    s.ai_approval_recorded_at = None
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.hse_settings,
        entity_id=project.id,
        project_id=project.id,
        before=before,
        after=_snapshot(s),
        details={"ai_transfer_approval": "withdrawn"},
    )
    return to_read(db, s)


# ---- reference lists -----------------------------------------------------------------------------


def seed_reference(db: Session) -> None:
    existing = {(r.list_name, r.code) for r in db.scalars(select(ReferenceItem)).all()}
    for lst, items in REFERENCE.items():
        for i, (code, en, ar, group, den, dar) in enumerate(items):
            if (lst.value, code) in existing:
                continue
            db.add(
                ReferenceItem(
                    list_name=lst.value,
                    code=code,
                    label_en=en,
                    label_ar=ar,
                    group=group,
                    description_en=den,
                    description_ar=dar,
                    sort_order=i,
                    points=OFF_POINTS[code][0] if lst == ReferenceList.airside_offence else None,
                    immediate_suspension=(
                        OFF_POINTS[code][1] if lst == ReferenceList.airside_offence else False
                    ),
                )
            )
    db.flush()


def labels(db: Session, lst: ReferenceList) -> dict[str, tuple[str, str]]:
    """Current labels (edited ones win over the seeded defaults)."""
    out = {code: (en, ar) for code, en, ar, *_ in REFERENCE.get(lst, [])}
    for r in db.scalars(select(ReferenceItem).where(ReferenceItem.list_name == lst.value)):
        out[r.code] = (r.label_en, r.label_ar)
    return out


def _item_read(r: ReferenceItem) -> ReferenceItemRead:
    tc = None
    if r.list_name == ReferenceList.treatment.value and r.group:
        tc = TreatmentClass(r.group)
    return ReferenceItemRead(
        code=r.code,
        label_en=r.label_en,
        label_ar=r.label_ar,
        group=r.group,
        treatment_class=tc,
        points=r.points if r.list_name == ReferenceList.airside_offence.value else None,
        immediate_suspension=(
            r.immediate_suspension if r.list_name == ReferenceList.airside_offence.value else None
        ),
        description_en=r.description_en,
        description_ar=r.description_ar,
        sort_order=r.sort_order,
    )


def list_reference(db: Session) -> ReferenceListsRead:
    rows = db.scalars(select(ReferenceItem)).all()
    if {r.list_name for r in rows} != {lst.value for lst in REFERENCE}:
        seed_reference(db)
        rows = db.scalars(select(ReferenceItem)).all()
    by: dict[str, list[ReferenceItem]] = {}
    for r in rows:
        by.setdefault(r.list_name, []).append(r)
    return ReferenceListsRead(
        lists=[
            ReferenceListRead(
                name=lst,
                items=[_item_read(r) for r in sorted(by.get(lst.value, []), key=_order)],
            )
            for lst in ReferenceList
        ]
    )


def _order(r: ReferenceItem) -> tuple[int, str]:
    return r.sort_order, r.code


def update_reference(
    db: Session, p: Principal, lst: ReferenceList, code: str, body: ReferenceItemUpdate
) -> ReferenceItemRead:
    if not p.is_manager:
        p.require(None, Capability.hse_settings_edit)
    if db.get(ReferenceItem, (lst.value, code)) is None:
        seed_reference(db)
    r = db.get(ReferenceItem, (lst.value, code))
    if r is None:
        raise not_found("Reference item")
    changes = body.model_dump(exclude_unset=True)
    if "points" in changes and lst != ReferenceList.airside_offence:
        raise validation_error("points", "Points apply to the airside offence list only.")
    if "points" in changes and changes["points"] is None:
        changes.pop("points")
    before = {"label_en": r.label_en, "label_ar": r.label_ar, "points": r.points}
    for k, v in changes.items():
        setattr(r, k, v)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(None),
        entity_type=EntityType.reference_list_item,
        entity_id=None,
        before=before,
        after={"label_en": r.label_en, "label_ar": r.label_ar, "points": r.points},
        details={"list": lst.value, "code": code},
    )
    return _item_read(r)
