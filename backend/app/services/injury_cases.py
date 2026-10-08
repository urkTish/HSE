"""Injury cases (spec 1-dashboard §3.4, rules I-4…I-12, P1-1…P1-2): category derivation,
day counts, PDPL field groups per capability 29/30 with `sensitive_field_read` audit."""

import re
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import (
    CaseCategory,
    ClassificationStatus,
    IdType,
    IncidentStatus,
    IncidentType,
    PersonType,
    RateExclusionReason,
    ReferenceList,
)
from app.kpi.cases import CaseDates, day_counts, derive_category, lost_days_charged
from app.models import Deployment, Incident, InjuryCase, Worker
from app.schemas.hse_common import ApiWarning
from app.schemas.incidents import (
    CaseDayCounts,
    ClassificationConfirm,
    IdNumberRead,
    InjuryCaseCreate,
    InjuryCaseRead,
    InjuryCaseUpdate,
)
from app.services import audit, hse_settings
from app.services.common import ensure_open, invalid_transition
from app.services.hse_common import Refs, check_engagement, covers, id_warnings, project_today
from app.services.incidents import (
    EDITABLE,
    Bundle,
    bundle,
    can_view,
    exclusion_reasons,
    get_incident,
    load_cases,
    open_lti,
    person_label,
    restate_if_locked,
)
from app.services.permissions import Principal, deny, forbidden_error

PRIVACY_EN = "Privacy case"
PRIVACY_AR = "حالة خصوصية"
ID_PATTERNS = {
    IdType.iqama: re.compile(r"^2\d{9}$"),
    IdType.national_id: re.compile(r"^1\d{9}$"),
    IdType.gcc_id: re.compile(r"^[A-Z0-9]{6,15}$"),
    IdType.passport: re.compile(r"^[A-Z0-9]{6,9}$"),
}
IDENTITY = (
    "person_name",
    "id_type",
    "id_number_masked",
    "employee_no",
    "nationality",
    "age_band",
    "site_start_date",
    "days_on_site",
    "hours_into_shift",
    "gosi_case_ref",
)
MEDICAL = (
    "illness",
    "body_part",
    "body_side",
    "nature",
    "treatments",
    "loss_of_consciousness",
    "treated_at",
    "fatal",
    "date_of_death",
    "away_start_date",
    "rtw_date",
    "restricted_start",
    "restricted_end",
    "transfer_start",
    "transfer_end",
    "permanent_disability",
    "privacy_case",
    "privacy_reason",
    "day_counts",
    "medical_notes",
)
IDENTITY_KEEP = (
    "person_name",
    "employee_no",
    "trade",
    "nationality",
    "employer_engagement_id",
    "site_start_date",
)
PLAIN = (
    "person_type",
    "employer_engagement_id",
    "person_name",
    "employee_no",
    "nationality",
    "trade",
    "age_band",
    "site_start_date",
    "hours_into_shift",
    "illness",
    "body_part",
    "body_side",
    "nature",
    "mechanism",
    "agency",
    "loss_of_consciousness",
    "treated_at",
    "fatal",
    "date_of_death",
    "away_start_date",
    "rtw_date",
    "restricted_start",
    "restricted_end",
    "transfer_start",
    "transfer_end",
    "permanent_disability",
    "commuting",
    "privacy_case",
    "privacy_reason",
    "medical_notes",
    "gosi_case_ref",
)


# ---- rules ---------------------------------------------------------------------------------------


def case_dates(c: InjuryCase, injury_date: date) -> CaseDates:
    return CaseDates(
        injury_date=injury_date,
        away_start_date=c.away_start_date,
        rtw_date=c.rtw_date,
        restricted_start=c.restricted_start,
        restricted_end=c.restricted_end,
        transfer_start=c.transfer_start,
        transfer_end=c.transfer_end,
    )


def derive(c: InjuryCase, inc: Incident, as_of: date) -> CaseCategory:
    return derive_category(
        dates=case_dates(c, inc.occurred_date),
        fatal=c.fatal,
        permanent=c.permanent_disability,
        treatments=c.treatments or [],
        loss_of_consciousness=c.loss_of_consciousness,
        nature=c.nature,
        treated_at=c.treated_at,
        as_of=as_of,
    )


def _validate(db: Session, b: Bundle, c: InjuryCase) -> None:
    d0 = b.inc.occurred_date
    if c.person_type == PersonType.contractor_worker:
        if c.employer_engagement_id is None:
            raise validation_error(
                "employer_engagement_id", "The employer is required for contractor workers."
            )
        check_engagement(db, b.project, c.employer_engagement_id, "employer_engagement_id")
    elif c.employer_engagement_id is not None:
        raise validation_error(
            "employer_engagement_id", "Only contractor workers have an employer engagement."
        )
    if c.site_start_date and c.site_start_date > d0:
        raise validation_error("site_start_date", "The site start date must be ≤ incident date.")
    if c.fatal and c.date_of_death is None:
        raise validation_error("date_of_death", "The date of death is required for a fatality.")
    if c.date_of_death is not None and (not c.fatal or c.date_of_death < d0):
        raise validation_error("date_of_death", "Date of death needs fatal = true, ≥ incident.")
    if c.away_start_date is not None and c.away_start_date <= d0:
        raise validation_error(
            "away_start_date", "Absence starts after the day of injury (I-7, OSHA 1904.7(b)(3))."
        )
    away_start = c.away_start_date or d0 + timedelta(days=1)
    if c.rtw_date is not None and c.rtw_date <= away_start:
        raise validation_error(
            "rtw_date", "The return-to-work date must be after the absence start."
        )
    absent = c.away_start_date is not None or c.rtw_date is not None
    for kind in ("restricted", "transfer"):
        start, end = getattr(c, f"{kind}_start"), getattr(c, f"{kind}_end")
        if end is not None and start is None:
            raise validation_error(f"{kind}_start", f"{kind}_start is required with {kind}_end.")
        if start is None:
            continue
        if start <= d0:
            raise validation_error(f"{kind}_start", "Must be after the day of injury.")
        if end is not None and end < start:
            raise validation_error(f"{kind}_end", "The end must be on or after the start.")
        if (
            absent
            and (c.rtw_date is None or start < c.rtw_date)
            and (end is None or end >= away_start)
        ):
            raise validation_error(f"{kind}_start", "Must not overlap the absence period.")
    if c.privacy_case and c.privacy_reason is None:
        raise validation_error("privacy_reason", "Choose the OSHA 1904.29(b)(7) reason.")
    if not c.privacy_case:
        c.privacy_reason = None


def _set_id(c: InjuryCase, id_type: IdType | None, number: str | None) -> None:
    if number:
        number = number.strip().upper()
        if id_type is None:
            raise validation_error("id_type", "The ID type is required with an ID number.")
        if not ID_PATTERNS[id_type].match(number):
            raise validation_error("id_number", f"Not a valid {id_type.value} number.")
        c.id_number_enc = crypto.encrypt(number)
        c.id_number_masked = crypto.mask_id(number)
    else:
        c.id_number_enc = None
        c.id_number_masked = None
    c.id_type = id_type


# ---- visibility ----------------------------------------------------------------------------------


def _apply_worker(
    db: Session, b: Bundle, c: InjuryCase, worker_id: uuid.UUID | None, given: set[str]
) -> str | None:
    """v1.1: link a Phase 2 worker (deployment on the incident's project) and pre-fill the
    identity fields that were not sent. Returns the full ID number to store, when pre-filled."""
    c.worker_id = worker_id
    if worker_id is None:
        return None
    w = db.get(Worker, worker_id)
    dep = (
        db.scalar(
            select(Deployment)
            .where(Deployment.worker_id == worker_id, Deployment.project_id == b.inc.project_id)
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        if w is not None
        else None
    )
    if w is None or dep is None:
        raise validation_error("worker_id", "The worker has no deployment on this project.")
    if "person_name" not in given or not c.person_name:
        c.person_name = w.full_name_en
    if "employee_no" not in given and dep.employee_no:
        c.employee_no = dep.employee_no
    if "trade" not in given and dep.trade:
        c.trade = dep.trade
    if "site_start_date" not in given or c.site_start_date is None:
        c.site_start_date = dep.inducted_on or dep.mobilised_on
    if ("employer_engagement_id" not in given or c.employer_engagement_id is None) and (
        dep.engagement_id
    ):
        c.employer_engagement_id = dep.engagement_id
    if "nationality" not in given and w.nationality:
        c.nationality = w.nationality
    if "id_number" not in given and w.id_number_enc and w.id_type:
        c.id_type = IdType(w.id_type.value)
        return crypto.decrypt(w.id_number_enc)
    return None


def _load(db: Session, p: Principal, case_id: uuid.UUID) -> tuple[InjuryCase, Bundle]:
    c = db.get(InjuryCase, case_id)
    if c is None:
        raise deny(db, p, EntityType.injury_case, case_id, None, "Injury case")
    inc = db.get(Incident, c.incident_id)
    assert inc is not None  # noqa: S101
    b = bundle(db, inc)
    if not can_view(p, inc, b.cases, b.inv):
        raise deny(db, p, EntityType.injury_case, case_id, inc.project_id, "Injury case")
    return c, b


def _can_identity(p: Principal, c: InjuryCase, b: Bundle) -> bool:
    g = p.grant(b.inc.project_id, Capability.injury_identity_view)
    return covers(g, b.inc.site_id, c.employer_engagement_id or b.inc.responsible_engagement_id)


def _can_medical(p: Principal, c: InjuryCase, b: Bundle) -> bool:
    g = p.grant(b.inc.project_id, Capability.injury_medical_view)
    return covers(g, b.inc.site_id, c.employer_engagement_id or b.inc.responsible_engagement_id)


def _can_write(p: Principal, b: Bundle) -> bool:
    g = p.grant(b.inc.project_id, Capability.incident_classify)
    if covers(g, b.inc.site_id, None):
        return True
    return b.inc.status == IncidentStatus.draft and b.inc.created_by_user_id == p.user.id


# ---- read ----------------------------------------------------------------------------------------


def to_read(
    db: Session,
    p: Principal,
    c: InjuryCase,
    b: Bundle,
    as_of: date | None = None,
    warnings: list[ApiWarning] | None = None,
) -> InjuryCaseRead:
    inc = b.inc
    s = hse_settings.get(db, inc.project_id)
    refs = Refs(db)
    trades = hse_settings.labels(db, ReferenceList.trade)
    en, ar = person_label(c, refs, trades)
    reasons = exclusion_reasons(inc, c, s)
    fields: dict[str, Any] = {
        "id": c.id,
        "incident_id": inc.id,
        "case_no": f"{inc.ref}-P{c.person_no}",
        "display_label": en,
        "display_label_ar": ar,
        "person_type": c.person_type,
        "employer": refs.eng(c.employer_engagement_id),
        "trade": c.trade,
        "mechanism": c.mechanism,
        "agency": c.agency,
        "commuting": c.commuting,
        "derived_category": c.derived_category,
        "case_category": c.category,
        "classification_status": c.classification_status,
        "category_override_justification": c.override_justification,
        "excluded_from_rates": bool(reasons),
        "exclusion_reasons": [RateExclusionReason(r) for r in reasons],
        "open_lti": open_lti(c),
        "warnings": warnings or [],
    }
    redacted = []
    read_fields: list[str] = []
    if _can_identity(p, c, b):
        hidden = c.privacy_case and not p.is_manager
        days_on_site = (inc.occurred_date - c.site_start_date).days if c.site_start_date else None
        ident = {
            "worker_id": c.worker_id,
            "worker_no": _worker_no(db, c.worker_id),
            "person_name": f"{PRIVACY_EN} / {PRIVACY_AR}" if hidden else c.person_name,
            "id_type": None if hidden else c.id_type,
            "id_number_masked": None if hidden else c.id_number_masked,
            "employee_no": c.employee_no,
            "nationality": c.nationality,
            "age_band": c.age_band,
            "site_start_date": c.site_start_date,
            "days_on_site": days_on_site,
            "hours_into_shift": c.hours_into_shift,
            "gosi_case_ref": c.gosi_case_ref,
        }
        if hidden:
            ident.pop("id_type")
            ident.pop("id_number_masked")
        fields.update(ident)
        read_fields += [k for k in ident if k != "person_name" or not hidden]
    else:
        redacted.append("identity")
    if _can_medical(p, c, b):
        day = as_of or project_today(b.project)
        counts = day_counts(case_dates(c, inc.occurred_date), day, s.lost_days_cap)
        med = {k: getattr(c, k) for k in MEDICAL if k != "day_counts"}
        med["day_counts"] = CaseDayCounts(
            as_of=day,
            days_away=counts.days_away,
            restricted_days=counts.restricted_days,
            transfer_days=counts.transfer_days,
            capped=counts.capped,
            lost_days_charged=lost_days_charged(
                c.category, counts, c.fatal, c.permanent_disability, s.fatality_lost_days_charge
            ),
        )
        fields.update(med)
        read_fields += list(med)
    else:
        redacted.append("medical")
    fields["redacted_groups"] = redacted
    if read_fields:
        audit.record(
            db,
            AuditAction.sensitive_field_read,
            p.actor(inc.project_id),
            entity_type=EntityType.injury_case,
            entity_id=c.id,
            project_id=inc.project_id,
            fields_read=read_fields,
        )
    return InjuryCaseRead(**fields)


def get(db: Session, p: Principal, case_id: uuid.UUID, as_of: date | None) -> InjuryCaseRead:
    c, b = _load(db, p, case_id)
    return to_read(db, p, c, b, as_of)


def reveal_id(db: Session, p: Principal, case_id: uuid.UUID) -> IdNumberRead:
    c, b = _load(db, p, case_id)
    if not _can_identity(p, c, b) or (c.privacy_case and not p.is_manager):
        raise forbidden_error("You may not view this ID number.")
    number = crypto.decrypt(c.id_number_enc) if c.id_number_enc else None
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(b.inc.project_id),
        entity_type=EntityType.injury_case,
        entity_id=c.id,
        project_id=b.inc.project_id,
        fields_read=["id_type", "id_number"],
    )
    return IdNumberRead(id_type=c.id_type, id_number=number)


# ---- writes --------------------------------------------------------------------------------------


def _snapshot(c: InjuryCase) -> dict[str, Any]:
    snap = {k: getattr(c, k) for k in PLAIN}
    snap.update(
        treatments=list(c.treatments or []),
        id_type=c.id_type,
        id_number_masked=c.id_number_masked,
        derived_category=c.derived_category,
        confirmed_category=c.confirmed_category,
        classification_status=c.classification_status,
    )
    return snap


def _key(c: InjuryCase) -> tuple[Any, ...]:
    """What, if changed on a counted case, restates its month (I-9)."""
    return (c.category, c.person_type, c.commuting, c.employer_engagement_id)


def _rederive(c: InjuryCase, b: Bundle) -> None:
    old = c.derived_category
    c.derived_category = derive(c, b.inc, project_today(b.project))
    if (
        c.classification_status == ClassificationStatus.confirmed
        and c.override_justification is None
        and c.derived_category != old
    ):
        # A confirmed category that followed the derivation is re-opened for confirmation.
        c.confirmed_category = None
        c.classification_status = ClassificationStatus.provisional


def create(
    db: Session, p: Principal, incident_id: uuid.UUID, body: InjuryCaseCreate
) -> InjuryCaseRead:
    b = bundle(db, get_incident(db, p, incident_id))
    ensure_open(b.project)
    p.ensure_writer()
    if not _can_write(p, b):
        raise forbidden_error()
    if b.inc.status not in EDITABLE:
        raise invalid_transition("Incident", b.inc.status, "case added")
    if IncidentType.injury_illness.value not in b.inc.incident_types:
        raise validation_error("incident_types", "Cases belong to injury/illness incidents only.")
    n = (
        db.scalar(select(func.max(InjuryCase.person_no)).where(InjuryCase.incident_id == b.inc.id))
        or 0
    ) + 1
    data = body.model_dump()
    c = InjuryCase(incident_id=b.inc.id, project_id=b.inc.project_id, person_no=n)
    for k in PLAIN:
        setattr(c, k, data[k])
    c.treatments = [t.value for t in body.treatments]
    _set_id(c, body.id_type, body.id_number)
    given = {k for k in body.model_fields_set if data.get(k) is not None}
    pre = _apply_worker(db, b, c, body.worker_id, given)
    if pre is not None:
        _set_id(c, c.id_type, pre)
    _validate(db, b, c)
    c.derived_category = derive(c, b.inc, project_today(b.project))
    c.classification_status = ClassificationStatus.provisional
    c.seed_fake = False
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(b.inc.project_id),
        entity_type=EntityType.injury_case,
        entity_id=c.id,
        project_id=b.inc.project_id,
        after=_snapshot(c),
    )
    if b.inc.status != IncidentStatus.draft:
        restate_if_locked(
            db, p, b, [b.inc.occurred_date], f"{b.inc.ref} case added", f"إضافة حالة {b.inc.ref}"
        )
    warnings = id_warnings(medical_notes=c.medical_notes) + _med(db, c, p)
    return to_read(db, p, c, bundle(db, b.inc), warnings=warnings)


def update(db: Session, p: Principal, case_id: uuid.UUID, body: InjuryCaseUpdate) -> InjuryCaseRead:
    c, b = _load(db, p, case_id)
    ensure_open(b.project)
    p.ensure_writer()
    if b.inc.status == IncidentStatus.voided:
        raise invalid_transition("Incident", b.inc.status, "case edited")
    if not _can_write(p, b):
        raise forbidden_error()
    before = _snapshot(c)
    key_before = _key(c)
    ch = body.changes()
    for k in PLAIN:
        if k in ch:
            setattr(c, k, ch[k])
    if "treatments" in ch:
        c.treatments = [str(t) for t in ch["treatments"]]
    if "id_number" in ch or "id_type" in ch:
        number = ch.get("id_number") if "id_number" in ch else _current_id(c)
        _set_id(c, ch.get("id_type", c.id_type), number)
    if "worker_id" in ch and ch["worker_id"] != c.worker_id:
        keep = {k for k in IDENTITY_KEEP if getattr(c, k) is not None}
        if c.id_number_enc is not None:
            keep.add("id_number")
        pre = _apply_worker(db, b, c, ch["worker_id"], set(ch) | keep)
        if pre is not None:
            _set_id(c, c.id_type, pre)
    _validate(db, b, c)
    _rederive(c, b)
    c.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snapshot(c))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(b.inc.project_id),
            entity_type=EntityType.injury_case,
            entity_id=c.id,
            project_id=b.inc.project_id,
            before=bf,
            after=af,
        )
    if b.inc.status != IncidentStatus.draft and _key(c) != key_before:
        restate_if_locked(
            db,
            p,
            b,
            [b.inc.occurred_date],
            f"{b.inc.ref}-P{c.person_no} reclassified {key_before[0].value} → {c.category.value}",
            f"إعادة تصنيف {b.inc.ref}-P{c.person_no}",
        )
    warnings = id_warnings(medical_notes=c.medical_notes) + _med(db, c, p)
    return to_read(db, p, c, b, warnings=warnings)


def _med(db: Session, c: InjuryCase, p: Principal) -> list[ApiWarning]:
    """6a §11.2: fitness holds from injury cases (FH-1a, FH-4) and RW-2 warnings."""
    from app.services.med import holds as med_holds  # noqa: PLC0415

    return med_holds.on_case(db, c, p)


def _worker_no(db: Session, worker_id: uuid.UUID | None) -> str | None:
    return db.scalar(select(Worker.worker_no).where(Worker.id == worker_id)) if worker_id else None


def _current_id(c: InjuryCase) -> str | None:
    return crypto.decrypt(c.id_number_enc) if c.id_number_enc else None


def delete(db: Session, p: Principal, case_id: uuid.UUID) -> None:
    c, b = _load(db, p, case_id)
    p.ensure_writer()
    if b.inc.status != IncidentStatus.draft:
        raise invalid_transition("Incident", b.inc.status, "case removed")
    if not _can_write(p, b):
        raise forbidden_error()
    audit.record(
        db,
        AuditAction.archive,
        p.actor(b.inc.project_id),
        entity_type=EntityType.injury_case,
        entity_id=c.id,
        project_id=b.inc.project_id,
        details={"deleted_from_draft": True, "case_no": f"{b.inc.ref}-P{c.person_no}"},
    )
    db.delete(c)
    db.flush()


def confirm(
    db: Session, p: Principal, case_id: uuid.UUID, body: ClassificationConfirm
) -> InjuryCaseRead:
    c, b = _load(db, p, case_id)
    ensure_open(b.project)
    g = p.require(b.inc.project_id, Capability.incident_classify)
    if not covers(g, b.inc.site_id, None):
        raise forbidden_error()
    if b.inc.status in (IncidentStatus.draft, IncidentStatus.voided):
        raise invalid_transition("Incident", b.inc.status, "classified")
    key_before = _key(c)
    before = _snapshot(c)
    c.derived_category = derive(c, b.inc, project_today(b.project))
    if body.case_category != c.derived_category:
        if not p.is_manager:
            raise forbidden_error("Only the HSE Manager may override the derived category (I-6).")
        if not body.justification or len(body.justification.strip()) < 20:
            raise ApiError(
                422,
                ErrorCode.JUSTIFICATION_REQUIRED,
                "A justification of at least 20 characters is required to override (I-6).",
                "يلزم تبرير لا يقل عن 20 حرفاً لتغيير التصنيف.",
            )
        c.override_justification = body.justification.strip()
    else:
        c.override_justification = None
    c.confirmed_category = body.case_category
    c.classification_status = ClassificationStatus.confirmed
    c.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snapshot(c))
    audit.record(
        db,
        AuditAction.update,
        p.actor(b.inc.project_id),
        entity_type=EntityType.injury_case,
        entity_id=c.id,
        project_id=b.inc.project_id,
        before=bf,
        after=af,
        details={
            "classification": "confirmed",
            "override": c.override_justification is not None,
        },
    )
    if _key(c) != key_before:
        restate_if_locked(
            db,
            p,
            b,
            [b.inc.occurred_date],
            f"{b.inc.ref}-P{c.person_no} reclassified {key_before[0].value} → {c.category.value}",
            f"إعادة تصنيف {b.inc.ref}-P{c.person_no}",
        )
    return to_read(db, p, c, b, warnings=_med(db, c, p))


def get_for_incident(db: Session, incident_id: uuid.UUID) -> list[InjuryCase]:
    return load_cases(db, [incident_id]).get(incident_id, [])
