"""Option 7a vehicle accident details (spec 7a-vehicle-accident-details v1.1): the incident's
vehicle section, vehicle rows (§3.2), the Najm / police report archive (VA-14, VA-15) and the
hooks Phase 1 calls (VA-1 lock, VA-2 completeness, VA-5 authority, VA-13 recorded-not-counted,
VA-14 close check). Personal fields follow P7a-1 (capability 29)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import LicenceIssuer, PlateType, ValidityStatus, VehicleStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role, ZoneType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.followup_enums import FuWaiverReason
from app.core.hse_enums import (
    AttachmentOwner,
    CaseCategory,
    ExternalBody,
    IncidentStatus,
    PersonType,
)
from app.core.vehicle_enums import (
    COMPANY_OWNERSHIP,
    VehCategory,
    VehDocState,
    VehDriverKind,
    VehLicenceCheck,
    VehOwnership,
    VehReportAuthority,
    VehRoadType,
    VehWarning,
)
from app.models import (
    Adp,
    Attachment,
    Deployment,
    Incident,
    IncidentVehicle,
    InjuryCase,
    Offence,
    Project,
    Vehicle,
    Worker,
    Zone,
)
from app.models.followup import FuRequirement, FuSubmission
from app.schemas.hse_common import ApiWarning
from app.schemas.vehicle import (
    VehAccidentReportRead,
    VehAccidentReportUpdate,
    VehDocsRead,
    VehIncidentVehicleCreate,
    VehIncidentVehicleList,
    VehIncidentVehicleRead,
    VehIncidentVehicleUpdate,
    VehPrefillDriver,
    VehPrefillRead,
    VehPrefillVehicle,
    VehPrompt,
    VehReportFileRead,
    VehSectionRead,
    VehSubmissionOffer,
    VehVehicleRef,
    VehWorkerRef,
)
from app.services import audit, notify
from app.services import vehicle_rules as rules
from app.services.common import ensure_open
from app.services.hse_common import Refs, check_engagement, covers, project_role_users
from app.services.permissions import Principal, forbidden_error

ST = IncidentStatus
MAX_ROWS = 10
MAX_REPORT_FILES = 5
REPORT_FILE_MAX_BYTES = 10 * 1024 * 1024
REASON_MIN = 20
REPORT_ALERT_DAYS = 7
WORKER_PERSONS = (PersonType.contractor_worker, PersonType.client_pmc_staff)
RTA_RULES = ("POL-RTA", "NAJM-V")
INCIDENT_FIELDS = (
    "vehicle_involved",
    "road_type",
    "road_location",
    "journey_purpose",
    "light",
    "surface",
    "report_authority",
    "report_no",
    "report_date",
    "liability_pct_own",
    "third_party_damage_desc",
    "third_party_damage_cost_sar",
)
ROW_SIMPLE = (
    "ownership",
    "role",
    "plate_type",
    "category",
    "make_model",
    "damage",
    "damage_cost_sar",
    "insurer",
    "policy_no",
    "seat_belt",
    "speed_kmh",
    "speed_limit_kmh",
    "speed_source",
    "driver_kind",
    "external_driver_name",
    "licence_issuer",
    "licence_class",
    "licence_expiry",
    "licence_no",
    "hours_on_duty",
    "driver_case_no",
    "adp_offence_id",
)
PERSONAL_ROW = (
    "worker_id",
    "external_driver_name",
    "licence_issuer",
    "licence_class",
    "licence_expiry",
    "licence_no",
    "hours_on_duty",
    "insurer",
    "policy_no",
    "adp_offence_id",
)


# ---- errors --------------------------------------------------------------------------------------


def _err(status: int, code: ErrorCode, en: str, ar: str, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def locked_error() -> ApiError:
    return _err(
        422,
        ErrorCode.VEHICLE_INVOLVED_LOCKED,
        "A vehicle mechanism, agency, damaged vehicle, vehicle overturn or airside vehicle flag "
        "is recorded: vehicle_involved cannot be cleared (VA-1).",
        "تم تسجيل مؤشر مركبة؛ لا يمكن إلغاء حادث المركبة.",
    )


# ---- loading -------------------------------------------------------------------------------------


def rows_of(db: Session, incident_id: uuid.UUID) -> list[IncidentVehicle]:
    return list(
        db.scalars(
            select(IncidentVehicle)
            .where(IncidentVehicle.incident_id == incident_id)
            .order_by(IncidentVehicle.seq)
        )
    )


def rows_for(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[IncidentVehicle]]:
    out: dict[uuid.UUID, list[IncidentVehicle]] = {}
    if ids:
        for r in db.scalars(
            select(IncidentVehicle)
            .where(IncidentVehicle.incident_id.in_(list(ids)))
            .order_by(IncidentVehicle.seq)
        ):
            out.setdefault(r.incident_id, []).append(r)
    return out


def report_files(db: Session, incident_id: uuid.UUID) -> list[Attachment]:
    return list(
        db.scalars(
            select(Attachment)
            .where(
                Attachment.owner_type == AttachmentOwner.incident_accident_report,
                Attachment.owner_id == incident_id,
            )
            .order_by(Attachment.created_at)
        )
    )


def signal(inc: Incident, cases: Sequence[InjuryCase]) -> bool:
    return rules.vehicle_signal(
        [c.mechanism for c in cases],
        [c.agency for c in cases],
        inc.pd_asset_type,
        inc.do_category,
        inc.airside_flags or [],
    )


# ---- permissions ---------------------------------------------------------------------------------


def can_write(p: Principal, inc: Incident) -> bool:
    if inc.status in (ST.closed, ST.voided):
        return False
    g = p.grant(inc.project_id, Capability.incident_classify)
    if covers(g, inc.site_id, None):
        return True
    return inc.status == ST.draft and inc.created_by_user_id == p.user.id


def identity_ok(p: Principal, inc: Incident, engagement_id: uuid.UUID | None = None) -> bool:
    g = p.grant(inc.project_id, Capability.injury_identity_view)
    return covers(g, inc.site_id, engagement_id or inc.responsible_engagement_id)


def approved(db: Session, inc: Incident) -> bool:
    from app.models import Investigation  # noqa: PLC0415

    inv = db.get(Investigation, inc.id)
    return inv is not None and inv.approved_at is not None


def check_reason(db: Session, inc: Incident, reason: str | None) -> str | None:
    """§4: edits after the investigation is approved need a reason ≥ 20 characters."""
    if not approved(db, inc):
        return None
    if not reason or len(reason.strip()) < REASON_MIN:
        raise validation_error(
            "reason", "Give a reason of at least 20 characters (investigation approved)."
        )
    return reason.strip()


def _ensure_writable(db: Session, p: Principal, inc: Incident) -> Project:
    project = db.get(Project, inc.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    if inc.status in (ST.closed, ST.voided):
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The incident is closed; the vehicle section cannot be edited.",
            "الحادثة مغلقة؛ لا يمكن تعديل قسم المركبات.",
        )
    if not can_write(p, inc):
        raise forbidden_error()
    return project


# ---- incident-level fields (called from incidents.create / update) -------------------------------


def apply_incident(
    db: Session,
    inc: Incident,
    data: dict[str, Any],
    cases: Sequence[InjuryCase],
) -> list[ApiWarning]:
    """Sets the §3.1 fields present in `data` and enforces VA-1, VA-5, VA-13 and the zone rule.
    Returns non-blocking warnings (VA-7)."""
    for k in INCIDENT_FIELDS:
        if k in data:
            setattr(inc, k, data[k])
    if inc.report_no is not None:
        inc.report_no = inc.report_no.strip() or None
    return enforce(db, inc, cases, explicit_false="vehicle_involved" in data)


def enforce(
    db: Session, inc: Incident, cases: Sequence[InjuryCase], explicit_false: bool = False
) -> list[ApiWarning]:
    if signal(inc, cases):
        if explicit_false and not inc.vehicle_involved:
            raise locked_error()
        inc.vehicle_involved = True
    if inc.road_type is not None and inc.zone_id is not None:
        zone = db.get(Zone, inc.zone_id)
        is_air = zone is not None and zone.zone_type == ZoneType.airside
        if (inc.road_type == VehRoadType.airside) != is_air:
            raise _err(
                422,
                ErrorCode.ROAD_TYPE_ZONE_MISMATCH,
                "Road type airside is allowed only in an airside zone, and an airside zone needs "
                "road type airside.",
                "نوع الطريق الجانب الجوي يتطلب منطقة جانب جوي والعكس.",
            )
    if (
        inc.road_type == VehRoadType.public_road
        and inc.report_authority == VehReportAuthority.none_internal
    ):
        raise _err(
            422,
            ErrorCode.ACCIDENT_REPORT_AUTHORITY_REQUIRED,
            "A public-road accident needs a Najm, traffic police or airport operator report "
            "(VA-5).",
            "حادث الطريق العام يتطلب محضر نجم أو المرور أو مشغل المطار.",
        )
    if inc.report_date is not None and inc.report_date < inc.occurred_date:
        raise validation_error("report_date", "The report date cannot be before the incident.")
    if (inc.third_party_damage_cost_sar or 0) < 0:
        raise validation_error("third_party_damage_cost_sar", "Must be ≥ 0.")
    inc.recorded_not_counted = bool(inc.vehicle_involved) and rules.recorded_not_counted(
        inc.journey_purpose
    )
    if inc.road_type == VehRoadType.public_road and inc.report_no is None:
        if inc.report_alert_on is None:
            inc.report_alert_on = inc.occurred_date + timedelta(days=REPORT_ALERT_DAYS)
    else:
        inc.report_alert_on = None
    return commuting_warnings(inc, cases)


def commuting_warnings(inc: Incident, cases: Sequence[InjuryCase]) -> list[ApiWarning]:
    """VA-7: a commuting case on a vehicle incident whose journey is not commuting."""
    if not inc.vehicle_involved or inc.journey_purpose is None:
        return []
    if rules.recorded_not_counted(inc.journey_purpose):
        return []
    if not any(c.commuting for c in cases):
        return []
    return [
        ApiWarning(
            code=VehWarning.COMMUTING_PURPOSE_MISMATCH,
            message="A case is marked commuting but the journey purpose is not commuting.",
            message_ar="حالة مسجلة كتنقل بينما غرض الرحلة ليس تنقلاً.",
            field="journey_purpose",
        )
    ]


def on_case(db: Session, c: InjuryCase) -> list[ApiWarning]:
    """Called when a case is saved: VA-1 (agency / mechanism) and the VA-7 warning."""
    inc = db.get(Incident, c.incident_id)
    if inc is None:
        return []
    cases = list(db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id)))
    if signal(inc, cases) and not inc.vehicle_involved:
        inc.vehicle_involved = True
        inc.recorded_not_counted = rules.recorded_not_counted(inc.journey_purpose)
        db.flush()
    return commuting_warnings(inc, cases)


# ---- completeness (VA-2) and close (VA-14) -------------------------------------------------------


def missing_for_report(inc: Incident, rows: Sequence[IncidentVehicle]) -> list[str]:
    if not inc.vehicle_involved:
        return []
    out = []
    if inc.road_type is None:
        out.append("road_type")
    if not rows:
        out.append("vehicles")
    return out


def missing_for_investigation(inc: Incident, rows: Sequence[IncidentVehicle]) -> list[str]:
    if not inc.vehicle_involved:
        return []
    out = missing_for_report(inc, rows)
    if inc.journey_purpose is None:
        out.append("journey_purpose")
    if inc.road_type == VehRoadType.public_road:
        if not inc.road_location:
            out.append("road_location")
        if inc.report_authority is None:
            out.append("report_authority")
    for r in rows:
        out += [f"{r.label}.{f}" for f in rules.row_missing(r, occurred=inc.occurred_date)]
    return out


def check_report(db: Session, inc: Incident) -> None:
    """VA-2 at Draft → Reported."""
    rows = rows_of(db, inc.id)
    missing = missing_for_report(inc, rows)
    if missing == ["vehicles"]:
        raise _err(
            422,
            ErrorCode.VEHICLE_REQUIRED,
            "Add at least one vehicle (ownership and role) before reporting.",
            "أضف مركبة واحدة على الأقل قبل الإبلاغ.",
            missing=missing,
        )
    if missing:
        raise _err(
            422,
            ErrorCode.VEHICLE_SECTION_INCOMPLETE,
            "The vehicle section is incomplete: " + ", ".join(missing) + ".",
            "قسم المركبات غير مكتمل.",
            missing=missing,
        )


def check_investigation(db: Session, inc: Incident) -> None:
    """VA-2 before the investigation is submitted for approval (and before a quick close)."""
    missing = missing_for_investigation(inc, rows_of(db, inc.id))
    if missing:
        raise _err(
            422,
            ErrorCode.VEHICLE_SECTION_INCOMPLETE,
            "The vehicle section is incomplete: " + ", ".join(missing) + ".",
            "قسم المركبات غير مكتمل.",
            missing=missing,
        )


def _rta_reqs(db: Session, inc: Incident) -> list[FuRequirement]:
    return list(
        db.scalars(
            select(FuRequirement).where(
                FuRequirement.incident_id == inc.id,
                FuRequirement.rule_code.in_(RTA_RULES),
            )
        )
    )


def waived(db: Session, inc: Incident) -> bool:
    """VA-5: the 6f police / Najm requirement waived as body_confirmed_not_required."""
    return any(
        r.waived_at is not None
        and r.waiver_reason_code == FuWaiverReason.body_confirmed_not_required
        for r in _rta_reqs(db, inc)
    )


def report_required(db: Session, inc: Incident) -> bool:
    return (
        inc.vehicle_involved
        and inc.report_authority is not None
        and inc.report_authority != VehReportAuthority.none_internal
        and not waived(db, inc)
    )


def missing_to_close(db: Session, inc: Incident, files: Sequence[Attachment]) -> list[str]:
    if not report_required(db, inc):
        return []
    out = []
    if not inc.report_no:
        out.append("report_no")
    if inc.report_date is None:
        out.append("report_date")
    if not [f for f in files if f.superseded_by_id is None]:
        out.append("report_files")
    return out


def close_gaps(db: Session, inc: Incident) -> list[str]:
    return missing_to_close(db, inc, report_files(db, inc.id))


def check_close(db: Session, inc: Incident) -> None:
    """VA-14 on every transition to Closed."""
    missing = close_gaps(db, inc)
    if missing:
        raise _err(
            422,
            ErrorCode.ACCIDENT_REPORT_MISSING,
            "The accident report is missing: " + ", ".join(missing) + ".",
            "محضر الحادث غير مكتمل.",
            missing=missing,
        )


def on_closed(db: Session, inc: Incident) -> None:
    """VA-4: documents at the time are recomputed once more and frozen at Closed."""
    for r in rows_of(db, inc.id):
        _compute(db, inc, r)
    db.flush()


# ---- vehicle rows --------------------------------------------------------------------------------


def _vehicle(db: Session, project_id: uuid.UUID, vid: uuid.UUID) -> Vehicle:
    v = db.get(Vehicle, vid)
    if v is None or v.project_id != project_id:
        raise validation_error("vehicle_id", "The vehicle is not in this project's register.")
    return v


def register_match(
    db: Session,
    ar: str | None,
    en: str | None,
    digits: str | None,
    project_id: uuid.UUID | None = None,
) -> Vehicle | None:
    """VA-6: register vehicle with the same normalised plate (any project unless given)."""
    key = rules.plate_key(ar, en, digits)
    if key is None or digits is None:
        return None
    stmt = select(Vehicle).where(
        Vehicle.plate_digits.is_not(None), Vehicle.status != VehicleStatus.withdrawn
    )
    if project_id is not None:
        stmt = stmt.where(Vehicle.project_id == project_id)
    for v in db.scalars(stmt):
        if rules.plate_key(v.plate_letters_ar, v.plate_letters_en, v.plate_digits) == key:
            return v
    return None


def _deployed(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID, day: date) -> Deployment:
    deps = list(
        db.scalars(
            select(Deployment).where(
                Deployment.worker_id == worker_id, Deployment.project_id == project_id
            )
        )
    )
    for d in deps:
        if d.mobilised_on <= day and (d.demobilised_on is None or d.demobilised_on >= day):
            return d
    raise validation_error(
        "worker_id", "The driver must be a worker deployed on the project at the time."
    )


def adp_of(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID) -> Adp | None:
    return db.scalars(
        select(Adp)
        .where(
            Adp.worker_id == worker_id,
            Adp.project_id == project_id,
            Adp.validity_status.not_in([ValidityStatus.pending, ValidityStatus.withdrawn]),
        )
        .order_by(Adp.licence_expiry_date.desc())
        .limit(1)
    ).first()


def _apply_row(db: Session, inc: Incident, row: IncidentVehicle, data: dict[str, Any]) -> None:
    project_id = inc.project_id
    for k in ROW_SIMPLE:
        if k in data:
            setattr(row, k, data[k])
    for k in ("plate_letters_ar", "plate_letters_en", "plate_digits"):
        if k in data:
            v = (data[k] or "").strip()
            setattr(row, k, (v.upper() if k == "plate_letters_en" else v) or None)
    if "engagement_id" in data:
        row.engagement_id = data["engagement_id"]
    for k in ("pre_use_check_id", "journey_plan_id"):  # 7b §11.8 links
        if k in data:
            setattr(row, k, data[k])
    if "vehicle_id" in data:
        row.vehicle_id = data["vehicle_id"]
        if row.vehicle_id is not None:
            v = _vehicle(db, project_id, row.vehicle_id)
            row.plate_type = v.plate_type
            row.plate_letters_ar = v.plate_letters_ar
            row.plate_letters_en = v.plate_letters_en
            row.plate_digits = v.plate_digits
            if "category" not in data:
                row.category = VehCategory(v.category.value)
            if "make_model" not in data:
                row.make_model = v.make_model[:60]
            if "engagement_id" not in data or row.engagement_id is None:
                row.engagement_id = v.engagement_id
    if data.get("docs") is not None:
        if row.vehicle_id is not None:
            raise validation_error(
                "docs", "Documents are computed from the register vehicle (VA-4)."
            )
        docs = data["docs"]
        row.doc_istimara = VehDocState(docs["istimara"])
        row.doc_insurance = VehDocState(docs["insurance"])
        row.doc_mvpi = VehDocState(docs["mvpi"])
    worker_changed = "worker_id" in data and data["worker_id"] != row.worker_id
    if "worker_id" in data:
        row.worker_id = data["worker_id"]
    if worker_changed and row.worker_id is not None:
        _deployed(db, project_id, row.worker_id, inc.occurred_date)
        given = {"licence_issuer", "licence_class", "licence_expiry"} & set(data)
        adp = adp_of(db, project_id, row.worker_id)
        if adp is not None and not given:
            row.licence_issuer = adp.licence_issuer
            row.licence_class = adp.licence_class
            row.licence_expiry = adp.licence_expiry_date
            row.licence_prefilled_from_adp = True
        elif given:
            row.licence_prefilled_from_adp = False
    elif {"licence_issuer", "licence_class", "licence_expiry"} & set(data):
        row.licence_prefilled_from_adp = False
    _validate_row(db, inc, row)


def _validate_row(db: Session, inc: Incident, row: IncidentVehicle) -> None:
    project = db.get(Project, inc.project_id)
    assert project is not None  # noqa: S101
    if row.engagement_id is not None:
        check_engagement(db, project, row.engagement_id)
    if row.ownership not in COMPANY_OWNERSHIP and row.vehicle_id is not None:
        raise validation_error(
            "vehicle_id", "Only own, contractor or hired rows link the register."
        )
    if row.ownership != VehOwnership.third_party and (row.insurer or row.policy_no):
        raise validation_error(
            "insurer", "Insurer and policy are entered for third-party vehicles only."
        )
    if row.plate_type == PlateType.none:
        row.plate_letters_ar = row.plate_letters_en = row.plate_digits = None
    kind = row.driver_kind
    if row.worker_id is not None and kind != VehDriverKind.worker:
        raise validation_error("worker_id", "A worker driver needs driver_kind worker.")
    if row.external_driver_name and kind != VehDriverKind.external:
        raise validation_error(
            "external_driver_name", "An external driver name needs driver_kind external."
        )
    if kind == VehDriverKind.none:
        row.licence_issuer = row.licence_class = row.licence_expiry = None
        row.licence_no = None
        row.hours_on_duty = None
    if row.licence_no and row.licence_issuer in (None, LicenceIssuer.ksa):
        raise validation_error(
            "licence_no",
            "A KSA licence number is never stored (it equals the holder's ID); enter a number "
            "for GCC or international licences only.",
        )
    if row.driver_case_no is not None:
        ok = db.scalar(
            select(InjuryCase.id).where(
                InjuryCase.incident_id == inc.id, InjuryCase.person_no == row.driver_case_no
            )
        )
        if ok is None:
            raise validation_error("driver_case_no", "No injury case with this number.")
    if row.adp_offence_id is not None:
        o = db.get(Offence, row.adp_offence_id)
        if o is None or o.project_id != inc.project_id:
            raise validation_error("adp_offence_id", "The offence is not on this project.")
    _check_7b_links(db, inc, row)
    if row.ownership == VehOwnership.third_party and row.plate_digits:
        hit = register_match(db, row.plate_letters_ar, row.plate_letters_en, row.plate_digits)
        if hit is not None:
            raise _err(
                422,
                ErrorCode.PLATE_IS_REGISTERED,
                "This plate is in the vehicle register; record it as an own, contractor or hired "
                "vehicle (VA-6).",
                "هذه اللوحة مسجلة في سجل المركبات؛ سجّلها كمركبة الشركة أو المقاول أو مستأجرة.",
            )
    _compute(db, inc, row)


def _check_7b_links(db: Session, inc: Incident, row: IncidentVehicle) -> None:
    """7a v1.2 (7b §11.8): optional links to a 7b pre-use check / journey plan of the same
    project and, when the row links a register vehicle, of that vehicle."""
    from app.models import JourneyPlan, VehicleCheck  # noqa: PLC0415

    recs: list[tuple[str, VehicleCheck | JourneyPlan | None, bool]] = [
        ("pre_use_check_id", db.get(VehicleCheck, row.pre_use_check_id), False)
        if row.pre_use_check_id
        else ("pre_use_check_id", None, True),
        ("journey_plan_id", db.get(JourneyPlan, row.journey_plan_id), False)
        if row.journey_plan_id
        else ("journey_plan_id", None, True),
    ]
    for fld, rec, unset in recs:
        if unset:
            continue
        if rec is None or rec.project_id != inc.project_id:
            raise validation_error(fld, "Unknown record on this project.")
        if row.vehicle_id is None or rec.vehicle_id != row.vehicle_id:
            raise validation_error(fld, "The record is for another vehicle (link the vehicle).")


def _compute(db: Session, inc: Incident, row: IncidentVehicle) -> None:
    """VA-3 licence check and VA-4 documents at the time."""
    day = inc.occurred_date
    if row.vehicle_id is not None:
        v = db.get(Vehicle, row.vehicle_id)
        if v is not None:
            row.doc_istimara = rules.doc_state(v.istimara_expiry, day)
            row.doc_insurance = rules.doc_state(v.insurance_expiry, day)
            row.doc_mvpi = rules.doc_state(v.mvpi_expiry, day)
    adp_classes: list[str] = []
    if row.worker_id is not None and row.plate_type in (None, PlateType.none):
        adp = adp_of(db, inc.project_id, row.worker_id)
        adp_classes = list(adp.vehicle_classes or []) if adp else []
    row.licence_check = rules.licence_check(
        row.driver_kind, row.licence_class, row.licence_expiry, row.category, day, adp_classes
    )
    row.occurred_date = day


def docs_expired(row: IncidentVehicle) -> bool:
    return VehDocState.expired in (row.doc_istimara, row.doc_insurance, row.doc_mvpi)


def licence_bad(row: IncidentVehicle) -> bool:
    return row.licence_check in (
        VehLicenceCheck.expired,
        VehLicenceCheck.wrong_class,
        VehLicenceCheck.no_licence,
    )


def row_warnings(row: IncidentVehicle) -> list[ApiWarning]:
    out = []
    if docs_expired(row):
        out.append(
            ApiWarning(
                code=VehWarning.VEHICLE_DOCS_EXPIRED_AT_TIME,
                message=f"{row.label}: a vehicle document was expired at the time of the incident.",
                message_ar=f"{row.label}: مستند المركبة كان منتهياً وقت الحادث.",
                field="docs_valid_at_time",
            )
        )
    if licence_bad(row):
        out.append(
            ApiWarning(
                code=VehWarning.LICENCE_NOT_VALID_AT_TIME,
                message=f"{row.label}: the driver's licence was not valid at the time "
                f"({row.licence_check.value if row.licence_check else ''}).",
                message_ar=f"{row.label}: رخصة السائق لم تكن سارية وقت الحادث.",
                field="licence_check",
            )
        )
    return out


def prompts(rows: Sequence[IncidentVehicle]) -> list[VehPrompt]:
    out = []
    for r in rows:
        for w in row_warnings(r):
            out.append(
                VehPrompt(
                    code=w.code,
                    vehicle_seq=r.seq,
                    message_en="Consider as a root cause: vehicle documents / licence not valid "
                    f"at the time ({r.label}).",
                    message_ar=f"يجب النظر كسبب جذري: مستندات المركبة / الرخصة غير سارية وقت "
                    f"الحادث ({r.label}).",
                )
            )
    return out


def _alert_prompt(db: Session, inc: Incident, row: IncidentVehicle) -> None:
    """§7: in-app alert to the investigation lead and HSE Officers, once per row."""
    from app.models import Investigation  # noqa: PLC0415

    if row.prompt_alerted or not row_warnings(row):
        return
    inv = db.get(Investigation, inc.id)
    who = set(project_role_users(db, inc.project_id, Role.hse_officer))
    if inv is not None and inv.lead_investigator_id is not None:
        who.add(inv.lead_investigator_id)
    notify.notify(
        db,
        who,
        NotificationKind.vehicle_docs_not_valid,
        f"{inc.ref} {row.label}: vehicle documents / licence not valid at the time",
        f"{inc.ref} {row.label}: مستندات المركبة / الرخصة غير سارية وقت الحادث",
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=inc.project_id,
    )
    row.prompt_alerted = True


def _snapshot(r: IncidentVehicle) -> dict[str, Any]:
    keys: tuple[str, ...] = ("seq", "ownership", "engagement_id", "vehicle_id", "category")
    keys += ("role", "damage", "seat_belt", "driver_kind", "licence_check")
    keys += ("licence_prefilled_from_adp", "worker_id", "speed_kmh")
    return {k: getattr(r, k) for k in keys}


def _audit_row(
    db: Session,
    p: Principal,
    inc: Incident,
    row: IncidentVehicle,
    action: AuditAction,
    before: dict[str, Any] | None,
    reason: str | None,
) -> None:
    after = _snapshot(row) if action != AuditAction.archive else None
    bf, af = (
        audit.diff(before, after)
        if before is not None and after is not None
        else (
            before,
            after,
        )
    )
    if action == AuditAction.update and not af:
        return
    audit.record(
        db,
        action,
        p.actor(inc.project_id),
        entity_type=EntityType.incident_vehicle,
        entity_id=row.id,
        project_id=inc.project_id,
        before=bf,
        after=af,
        details={"incident_id": str(inc.id), **({"reason": reason} if reason else {})},
    )


def _get_row(db: Session, p: Principal, row_id: uuid.UUID) -> tuple[IncidentVehicle, Incident]:
    from app.services import incidents as inc_svc  # noqa: PLC0415

    row = db.get(IncidentVehicle, row_id)
    if row is None:
        raise not_found("Incident vehicle")
    inc = inc_svc.get_incident(db, p, row.incident_id)
    return row, inc


def create_row(
    db: Session, p: Principal, incident_id: uuid.UUID, body: VehIncidentVehicleCreate
) -> VehIncidentVehicleRead:
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    _ensure_writable(db, p, inc)
    reason = check_reason(db, inc, body.reason)
    if not inc.vehicle_involved:
        raise validation_error(
            "vehicle_involved", "Mark the incident as a vehicle incident before adding vehicles."
        )
    existing = rows_of(db, inc.id)
    if len(existing) >= MAX_ROWS:
        raise validation_error("vehicles", "At most 10 vehicles per incident.")
    seq = max((r.seq for r in existing), default=0) + 1
    row = IncidentVehicle(
        incident_id=inc.id,
        project_id=inc.project_id,
        occurred_date=inc.occurred_date,
        seq=seq,
        ownership=body.ownership,
        role=body.role,
        created_by_user_id=p.user.id,
        licence_prefilled_from_adp=False,
        prompt_alerted=False,
        seed_fake=False,
    )
    data = body.model_dump(exclude={"reason"})
    data = {
        k: v for k, v in data.items() if k in body.model_fields_set or k in ("ownership", "role")
    }
    _apply_row(db, inc, row, data)
    db.add(row)
    db.flush()
    _audit_row(db, p, inc, row, AuditAction.create, None, reason)
    _alert_prompt(db, inc, row)
    inc.updated_at = now()
    db.flush()
    return row_read(db, p, inc, row)


def update_row(
    db: Session, p: Principal, row_id: uuid.UUID, body: VehIncidentVehicleUpdate
) -> VehIncidentVehicleRead:
    row, inc = _get_row(db, p, row_id)
    _ensure_writable(db, p, inc)
    ch = body.changes()
    reason = check_reason(db, inc, ch.pop("reason", None))
    before = _snapshot(row)
    if "docs" in ch and ch["docs"] is not None:
        ch["docs"] = dict(ch["docs"])
    _apply_row(db, inc, row, ch)
    row.updated_at = now()
    db.flush()
    _audit_row(db, p, inc, row, AuditAction.update, before, reason)
    _alert_prompt(db, inc, row)
    db.flush()
    return row_read(db, p, inc, row)


def delete_row(db: Session, p: Principal, row_id: uuid.UUID, reason: str | None) -> None:
    row, inc = _get_row(db, p, row_id)
    _ensure_writable(db, p, inc)
    why = check_reason(db, inc, reason)
    if inc.status != ST.draft and len(rows_of(db, inc.id)) <= 1:
        raise _err(
            422,
            ErrorCode.VEHICLE_REQUIRED,
            "A reported vehicle incident keeps at least one vehicle.",
            "يجب أن تبقى مركبة واحدة على الأقل.",
        )
    _audit_row(db, p, inc, row, AuditAction.archive, _snapshot(row), why)
    db.delete(row)
    db.flush()


def list_rows(db: Session, p: Principal, incident_id: uuid.UUID) -> VehIncidentVehicleList:
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    return VehIncidentVehicleList(items=reads(db, p, inc, rows_of(db, inc.id)))


# ---- read models ---------------------------------------------------------------------------------


@dataclass
class _Ctx:
    refs: Refs
    vehicles: dict[uuid.UUID, Vehicle]
    workers: dict[uuid.UUID, Worker]
    worker_engs: dict[uuid.UUID, uuid.UUID | None]


def _ctx(db: Session, inc: Incident, rows: Sequence[IncidentVehicle]) -> _Ctx:
    vids = [r.vehicle_id for r in rows if r.vehicle_id]
    wids = [r.worker_id for r in rows if r.worker_id]
    vehicles = {v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(vids)))}
    workers = {w.id: w for w in db.scalars(select(Worker).where(Worker.id.in_(wids)))}
    worker_engs: dict[uuid.UUID, uuid.UUID | None] = {}
    for d in db.scalars(
        select(Deployment).where(
            Deployment.worker_id.in_(wids), Deployment.project_id == inc.project_id
        )
    ):
        worker_engs[d.worker_id] = d.engagement_id
    refs = Refs(db).load(
        engs=[r.engagement_id for r in rows] + list(worker_engs.values()),
    )
    return _Ctx(refs, vehicles, workers, worker_engs)


LC_EN = {
    VehLicenceCheck.valid: "licence valid",
    VehLicenceCheck.expired: "licence expired",
    VehLicenceCheck.wrong_class: "licence class does not cover the vehicle",
    VehLicenceCheck.no_licence: "no licence",
    VehLicenceCheck.not_checked: "licence not checked",
}
LC_AR = {
    VehLicenceCheck.valid: "الرخصة سارية",
    VehLicenceCheck.expired: "الرخصة منتهية",
    VehLicenceCheck.wrong_class: "فئة الرخصة لا تشمل المركبة",
    VehLicenceCheck.no_licence: "لا توجد رخصة",
    VehLicenceCheck.not_checked: "لم يتم فحص الرخصة",
}


def driver_summary(row: IncidentVehicle, ctx: _Ctx) -> tuple[str, str]:
    """P7a-1: 'Driver: worker of GULFPAVE · licence valid' (no name, class or date)."""
    lc = row.licence_check or VehLicenceCheck.not_checked
    if row.driver_kind == VehDriverKind.none:
        return "No driver (parked)", "لا يوجد سائق (متوقفة)"
    if row.driver_kind == VehDriverKind.worker:
        eid = ctx.worker_engs.get(row.worker_id) if row.worker_id else None
        eng = ctx.refs.eng(eid or row.engagement_id)
        of = f" of {eng.short_code}" if eng else ""
        of_ar = f" لدى {eng.short_code}" if eng else ""
        return f"Driver: worker{of} · {LC_EN[lc]}", f"السائق: عامل{of_ar} · {LC_AR[lc]}"
    if row.driver_kind == VehDriverKind.external:
        return f"Driver: external · {LC_EN[lc]}", f"السائق: خارجي · {LC_AR[lc]}"
    return "Driver: not recorded", "السائق: غير مسجل"


def _row(
    db: Session, p: Principal, inc: Incident, row: IncidentVehicle, ctx: _Ctx
) -> tuple[VehIncidentVehicleRead, list[str]]:
    ident = identity_ok(p, inc, row.engagement_id)
    third = row.ownership in (VehOwnership.third_party, VehOwnership.unknown)
    show_plate = ident or not third
    v = ctx.vehicles.get(row.vehicle_id) if row.vehicle_id else None
    suggested = None
    if v is None and row.ownership in COMPANY_OWNERSHIP and row.plate_digits:
        hit = register_match(
            db, row.plate_letters_ar, row.plate_letters_en, row.plate_digits, inc.project_id
        )
        if hit is not None:
            suggested = VehVehicleRef(id=hit.id, vehicle_no=hit.vehicle_no)
    w = ctx.workers.get(row.worker_id) if row.worker_id else None
    en, ar = driver_summary(row, ctx)
    read_fields: list[str] = []
    if ident:
        read_fields = [f for f in PERSONAL_ROW if getattr(row, f) is not None]
        if third and row.plate_digits:
            read_fields.append("plate")
    redacted = [] if ident else ["driver_identity"]
    if not show_plate and row.plate_digits:
        redacted.append("plate")
    out = VehIncidentVehicleRead(
        id=row.id,
        incident_id=row.incident_id,
        seq=row.seq,
        label=row.label,
        ownership=row.ownership,
        engagement=ctx.refs.eng(row.engagement_id),
        vehicle=VehVehicleRef(id=v.id, vehicle_no=v.vehicle_no) if v else None,
        suggested_vehicle=suggested,
        plate_type=row.plate_type,
        plate_letters_ar=row.plate_letters_ar if show_plate else None,
        plate_letters_en=row.plate_letters_en if show_plate else None,
        plate_digits=row.plate_digits if show_plate else None,
        category=row.category,
        make_model=row.make_model,
        role=row.role,
        damage=row.damage,
        damage_cost_sar=row.damage_cost_sar,
        docs_valid_at_time=VehDocsRead(
            istimara=row.doc_istimara or VehDocState.unknown,
            insurance=row.doc_insurance or VehDocState.unknown,
            mvpi=row.doc_mvpi or VehDocState.unknown,
            source="register" if row.vehicle_id else "entered",
        ),
        insurer=row.insurer if ident else None,
        policy_no=row.policy_no if ident else None,
        seat_belt=row.seat_belt,
        speed_kmh=row.speed_kmh,
        speed_limit_kmh=row.speed_limit_kmh,
        speed_source=row.speed_source,
        driver_kind=row.driver_kind,
        worker=(
            VehWorkerRef(
                id=w.id,
                worker_no=w.worker_no,
                full_name_en=w.full_name_en,
                full_name_ar=w.full_name_ar,
            )
            if w is not None and ident
            else None
        ),
        external_driver_name=row.external_driver_name if ident else None,
        licence_issuer=row.licence_issuer if ident else None,
        licence_class=row.licence_class if ident else None,
        licence_expiry=row.licence_expiry if ident else None,
        licence_no=row.licence_no if ident else None,
        licence_prefilled_from_adp=row.licence_prefilled_from_adp,
        licence_check=row.licence_check,
        hours_on_duty=row.hours_on_duty if ident else None,
        driver_case_no=row.driver_case_no,
        adp_offence_id=row.adp_offence_id if ident else None,
        pre_use_check_id=row.pre_use_check_id,
        pre_use_check_no=_link_no(db, "check", row.pre_use_check_id),
        journey_plan_id=row.journey_plan_id,
        journey_plan_no=_link_no(db, "plan", row.journey_plan_id),
        driver_summary_en=en,
        driver_summary_ar=ar,
        redacted_groups=redacted,
        warnings=row_warnings(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return out, read_fields


def _link_no(db: Session, kind: str, rid: uuid.UUID | None) -> str | None:
    from app.models import JourneyPlan, VehicleCheck  # noqa: PLC0415

    if rid is None:
        return None
    if kind == "check":
        c = db.get(VehicleCheck, rid)
        return c.check_no if c else None
    j = db.get(JourneyPlan, rid)
    return j.plan_no if j else None


def reads(
    db: Session, p: Principal, inc: Incident, rows: Sequence[IncidentVehicle]
) -> list[VehIncidentVehicleRead]:
    ctx = _ctx(db, inc, rows)
    out = []
    for r in rows:
        read, fields = _row(db, p, inc, r, ctx)
        out.append(read)
        if fields:
            audit.record(
                db,
                AuditAction.sensitive_field_read,
                p.actor(inc.project_id),
                entity_type=EntityType.incident_vehicle,
                entity_id=r.id,
                project_id=inc.project_id,
                fields_read=fields,
            )
    return out


def row_read(
    db: Session, p: Principal, inc: Incident, row: IncidentVehicle
) -> VehIncidentVehicleRead:
    return reads(db, p, inc, [row])[0]


def _file_read(a: Attachment, refs: Refs) -> VehReportFileRead:
    from app.services.attachments import UNKNOWN  # noqa: PLC0415

    return VehReportFileRead(
        id=a.id,
        file_name=a.file_name,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        uploaded_by=refs.user(a.uploaded_by_user_id) or UNKNOWN,
        created_at=a.created_at,
        superseded=a.superseded_by_id is not None,
        superseded_by_id=a.superseded_by_id,
        superseded_at=a.superseded_at,
    )


def report_read(db: Session, p: Principal, inc: Incident) -> VehAccidentReportRead:
    files = report_files(db, inc.id)
    visible = identity_ok(p, inc)
    refs = Refs(db).load(users=[a.uploaded_by_user_id for a in files]) if visible else Refs(db)
    return VehAccidentReportRead(
        incident_id=inc.id,
        report_authority=inc.report_authority,
        report_no=inc.report_no,
        report_date=inc.report_date,
        liability_pct_own=inc.liability_pct_own,
        required_to_close=report_required(db, inc),
        waived=waived(db, inc),
        locked=inc.status == ST.closed,
        missing_to_close=missing_to_close(db, inc, files),
        file_count=len([f for f in files if f.superseded_by_id is None]),
        files_visible=visible,
        files=[_file_read(a, refs) for a in files] if visible else [],
    )


def submission_offer(db: Session, inc: Incident) -> VehSubmissionOffer | None:
    """AC21: report_no entered and the police / Najm notification still open."""
    if not inc.report_no or inc.road_type != VehRoadType.public_road:
        return None
    from app.services.followup.requirements import is_open  # noqa: PLC0415

    for r in sorted(_rta_reqs(db, inc), key=lambda x: x.due_at):
        subs = list(db.scalars(select(FuSubmission).where(FuSubmission.requirement_id == r.id)))
        if is_open(r, subs):
            return VehSubmissionOffer(body=r.body, reference_no=inc.report_no, requirement_id=r.id)
    from app.models import ExternalNotification  # noqa: PLC0415
    from app.services.incidents import load_cases, required_notifications  # noqa: PLC0415

    cases = load_cases(db, [inc.id]).get(inc.id, [])
    done = {
        n.body
        for n in db.scalars(
            select(ExternalNotification).where(ExternalNotification.incident_id == inc.id)
        )
    }
    for req in required_notifications(inc, cases):
        if req.body in (ExternalBody.police, ExternalBody.najm) and req.body not in done:
            if req.reason.startswith(("POL-", "NAJM-")):
                continue  # under the 6f profile: recorded through the requirement
            return VehSubmissionOffer(
                body=req.body, reference_no=inc.report_no, requirement_id=None
            )
    return None


def section_read(
    db: Session, p: Principal, inc: Incident, cases: Sequence[InjuryCase]
) -> VehSectionRead | None:
    if not inc.vehicle_involved:
        return None
    rows = rows_of(db, inc.id)
    proposed = []
    if rules.recorded_not_counted(inc.journey_purpose):
        proposed = [c.id for c in cases if c.person_type in WORKER_PERSONS and not c.commuting]
    return VehSectionRead(
        vehicle_involved_locked=signal(inc, cases),
        road_type=inc.road_type,
        road_location=inc.road_location,
        journey_purpose=inc.journey_purpose,
        light=inc.light,
        surface=inc.surface,
        third_party_damage_desc=inc.third_party_damage_desc,
        third_party_damage_cost_sar=inc.third_party_damage_cost_sar,
        recorded_not_counted=inc.recorded_not_counted,
        vehicles=reads(db, p, inc, rows),
        accident_report=report_read(db, p, inc),
        missing_for_report=missing_for_report(inc, rows),
        missing_for_investigation=missing_for_investigation(inc, rows),
        investigation_prompts=prompts(rows),
        commuting_proposed_case_ids=proposed,
        report_submission_offer=submission_offer(db, inc),
    )


# ---- accident report (VA-14, VA-15) --------------------------------------------------------------


def get_report(db: Session, p: Principal, incident_id: uuid.UUID) -> VehAccidentReportRead:
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    return report_read(db, p, inc)


def put_report(
    db: Session, p: Principal, incident_id: uuid.UUID, body: VehAccidentReportUpdate
) -> VehAccidentReportRead:
    """Sets the report record. VA-15: creates no client requirement or notification."""
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    _ensure_writable(db, p, inc)
    if not inc.vehicle_involved:
        raise validation_error("vehicle_involved", "Not a vehicle incident.")
    reason = check_reason(db, inc, body.reason)
    keys = ("report_authority", "report_no", "report_date", "liability_pct_own")
    before = {k: getattr(inc, k) for k in keys}
    data = {k: getattr(body, k) for k in keys if k in body.model_fields_set}
    cases = inc_svc.load_cases(db, [inc.id]).get(inc.id, [])
    apply_incident(db, inc, data, cases)
    inc.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, {k: getattr(inc, k) for k in keys})
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(inc.project_id),
            entity_type=EntityType.incident,
            entity_id=inc.id,
            project_id=inc.project_id,
            before=bf,
            after=af,
            details={"accident_report": True, **({"reason": reason} if reason else {})},
        )
    return report_read(db, p, inc)


def file_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """Attachment owner hook: report files are capability 29 only (P7a-1, VA-15); files may be
    added until Voided (also after Closed, VA-14)."""
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, owner_id)
    if not identity_ok(p, inc):
        raise forbidden_error("Accident report files need capability 29.")
    if write:
        g = p.grant(inc.project_id, Capability.incident_classify)
        own_draft = inc.status == ST.draft and inc.created_by_user_id == p.user.id
        if not covers(g, inc.site_id, None) and not own_draft:
            raise forbidden_error()
    return inc.project_id, inc.status != ST.voided


def ensure_deletable(db: Session, a: Attachment) -> None:
    inc = db.get(Incident, a.owner_id)
    if inc is not None and inc.status == ST.closed:
        raise _err(
            409,
            ErrorCode.ACCIDENT_REPORT_LOCKED,
            "The incident is closed: accident report files are archived and cannot be deleted; "
            "upload a corrected file to supersede one (VA-14).",
            "الحادثة مغلقة: ملفات محضر الحادث مؤرشفة ولا يمكن حذفها.",
        )


def upload_file(
    db: Session,
    p: Principal,
    incident_id: uuid.UUID,
    file_name: str,
    content: bytes,
    supersedes_id: uuid.UUID | None,
) -> VehAccidentReportRead:
    from app.services import attachments as att  # noqa: PLC0415
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    project = db.get(Project, inc.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    project_id, editable = file_owner(db, p, inc.id, write=True)
    if not editable:
        raise ApiError(
            409, ErrorCode.INVALID_TRANSITION, "The incident is voided.", "الحادثة ملغاة."
        )
    if not inc.vehicle_involved:
        raise validation_error("vehicle_involved", "Not a vehicle incident.")
    if len(content) > REPORT_FILE_MAX_BYTES:
        raise ApiError(
            422,
            ErrorCode.FILE_TOO_LARGE,
            "Report files must be 10 MB or smaller.",
            "الحد الأقصى 10 ميغابايت.",
        )
    ctype = att._content_type(file_name, content)
    files = report_files(db, inc.id)
    current = [f for f in files if f.superseded_by_id is None]
    old = None
    if supersedes_id is not None:
        old = next((f for f in current if f.id == supersedes_id), None)
        if old is None:
            raise validation_error("supersedes_id", "Not a current report file of this incident.")
    elif len(current) >= MAX_REPORT_FILES:
        raise validation_error("file", "At most 5 report files; supersede one instead.")
    a = att.store(
        db,
        AttachmentOwner.incident_accident_report,
        inc.id,
        project_id,
        file_name,
        content,
        ctype,
        p.user.id,
    )
    details: dict[str, Any] = {
        "owner_type": AttachmentOwner.incident_accident_report.value,
        "owner_id": str(inc.id),
        "size": len(content),
    }
    if old is not None:
        old.superseded_by_id = a.id
        old.superseded_at = now()
        details["supersedes"] = str(old.id)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.attachment,
        entity_id=a.id,
        project_id=project_id,
        details=details,
    )
    return report_read(db, p, inc)


# ---- prefill (VA-3, VA-4, VA-6) ------------------------------------------------------------------


def prefill(
    db: Session,
    p: Principal,
    incident_id: uuid.UUID,
    vehicle_id: uuid.UUID | None,
    plate_letters_ar: str | None,
    plate_letters_en: str | None,
    plate_digits: str | None,
    worker_id: uuid.UUID | None,
) -> VehPrefillRead:
    from app.services import incidents as inc_svc  # noqa: PLC0415

    inc = inc_svc.get_incident(db, p, incident_id)
    day = inc.occurred_date
    v: Vehicle | None = None
    if vehicle_id is not None:
        v = _vehicle(db, inc.project_id, vehicle_id)
    elif plate_digits:
        v = register_match(db, plate_letters_ar, plate_letters_en, plate_digits, inc.project_id)
    registered = v is not None or (
        bool(plate_digits)
        and register_match(db, plate_letters_ar, plate_letters_en, plate_digits) is not None
    )
    refs = Refs(db)
    veh = None
    if v is not None:
        veh = VehPrefillVehicle(
            id=v.id,
            vehicle_no=v.vehicle_no,
            engagement=refs.eng(v.engagement_id),
            category=VehCategory(v.category.value),
            make_model=v.make_model[:60],
            plate_type=v.plate_type,
            plate_letters_ar=v.plate_letters_ar,
            plate_letters_en=v.plate_letters_en,
            plate_digits=v.plate_digits,
            docs_valid_at_time=VehDocsRead(
                istimara=rules.doc_state(v.istimara_expiry, day),
                insurance=rules.doc_state(v.insurance_expiry, day),
                mvpi=rules.doc_state(v.mvpi_expiry, day),
                source="register",
            ),
        )
    driver = None
    if worker_id is not None and identity_ok(p, inc):
        _deployed(db, inc.project_id, worker_id, day)
        adp = adp_of(db, inc.project_id, worker_id)
        issuer = adp.licence_issuer if adp else None
        driver = VehPrefillDriver(
            worker_id=worker_id,
            has_adp=adp is not None,
            adp_no=adp.adp_no if adp else None,
            licence_issuer=issuer,
            licence_class=adp.licence_class if adp else None,
            licence_expiry=adp.licence_expiry_date if adp else None,
            licence_number_field=issuer in (LicenceIssuer.gcc, LicenceIssuer.international),
        )
        audit.record(
            db,
            AuditAction.sensitive_field_read,
            p.actor(inc.project_id),
            entity_type=EntityType.incident,
            entity_id=inc.id,
            project_id=inc.project_id,
            fields_read=["driver_licence_prefill"],
        )
    return VehPrefillRead(vehicle=veh, plate_registered=registered, driver=driver)


# ---- register list support -----------------------------------------------------------------------


def list_extras(db: Session, incidents: Sequence[Incident]) -> dict[uuid.UUID, list[str]]:
    """Plates of own / contractor / hired rows per incident (never third parties, §8)."""
    ids = [i.id for i in incidents if i.vehicle_involved]
    out: dict[uuid.UUID, list[str]] = {}
    for iid, rows in rows_for(db, ids).items():
        out[iid] = [
            f"{r.plate_letters_ar or r.plate_letters_en or ''} {r.plate_digits}".strip()
            for r in rows
            if r.ownership in COMPANY_OWNERSHIP and r.plate_digits
        ]
    return out


def count_rows(db: Session, incident_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(IncidentVehicle)
            .where(IncidentVehicle.incident_id == incident_id)
        )
        or 0
    )


# ---- §7 reminder: report_no missing 7 days after a public-road accident --------------------------


def report_reminders(db: Session, day: date) -> int:
    n = 0
    for inc in db.scalars(
        select(Incident).where(
            Incident.report_alert_on.is_not(None),
            Incident.report_alert_on <= day,
            Incident.report_no.is_(None),
            Incident.status.not_in([ST.draft, ST.voided]),
        )
    ):
        who = set(project_role_users(db, inc.project_id, Role.hse_officer))
        notify.notify(
            db,
            who,
            NotificationKind.accident_report_missing,
            f"{inc.ref}: Najm / police report number not yet recorded",
            f"{inc.ref}: لم يتم تسجيل رقم محضر نجم / المرور بعد",
            entity_type=EntityType.incident,
            entity_id=inc.id,
            project_id=inc.project_id,
        )
        inc.report_alert_on = day + timedelta(days=REPORT_ALERT_DAYS)
        n += 1
    db.flush()
    return n


def vehicle_injury(cases: Sequence[InjuryCase]) -> bool:
    """VA-10 / VA-12: an injury beyond first aid (any person type)."""
    return any(c.category != CaseCategory.FAC for c in cases)
