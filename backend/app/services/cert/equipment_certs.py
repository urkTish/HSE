"""Equipment inspection certificates and lines (spec 4-third-party-cert §3.6, §4.4, §6.1,
EC-1…EC-14, EQ-4, CF-1/CF-3, DF-2, VF-1…VF-7).

Validation is collected as `Issue`s so that the preview can list every problem while create
and Submit raise the first one."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    CertificateStatus,
    CertInspectionType,
    CertKind,
    CertSource,
    CertStatusReason,
    DefectCategory,
    DefectSource,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    LineResult,
    SafetyDevice,
    ServiceStatus,
    ServiceStatusReason,
    VerificationStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.models import (
    Attachment,
    ConfigurationEvent,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    Tpi,
)
from app.schemas.cert_common import (
    AllowedCertAction,
    CertTransitionRequest,
    CertValidity,
    VerificationCreate,
    VerificationList,
    VerificationRead,
)
from app.schemas.equipment_certs import (
    CertLineInput,
    CertLineRead,
    EquipmentCertificateCreate,
    EquipmentCertificateListItem,
    EquipmentCertificatePage,
    EquipmentCertificateRead,
    EquipmentCertificateUpdate,
    EquipmentCertPreview,
    EquipmentCertPreviewLine,
    LoadTestRead,
)
from app.schemas.hse_common import ApiWarning
from app.services import projects
from app.services.access import common as acommon
from app.services.cert import alerts, events, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.cert import tpis as tsvc
from app.services.cert import verification as vf
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
CS = CertificateStatus
VS = VerificationStatus
Q = EquipmentCertCategory
IT = CertInspectionType
PASSING = (LineResult.pass_, LineResult.pass_with_conditions)


# ---- access --------------------------------------------------------------------------------------


def get_row(db: Session, certificate_id: uuid.UUID) -> EquipmentCertificate:
    c = db.get(EquipmentCertificate, certificate_id)
    if c is None:
        raise not_found("Certificate")
    return c


def lines_of(db: Session, certificate_id: uuid.UUID) -> list[EquipmentCertLine]:
    return list(
        db.scalars(
            select(EquipmentCertLine)
            .where(EquipmentCertLine.certificate_id == certificate_id)
            .order_by(EquipmentCertLine.created_at, EquipmentCertLine.id)
        )
    )


def _deps(
    db: Session, c: EquipmentCertificate, lines: list[EquipmentCertLine]
) -> list[EquipmentDeployment]:
    out = []
    for line in lines:
        d = cc.latest_deployment_on(db, line.equipment_id, c.project_id)
        if d is not None:
            out.append(d)
    return out


def _covered(db: Session, p: Principal, c: EquipmentCertificate, cap: Capability) -> bool:
    g = p.grant(c.project_id, cap)
    if g is None:
        return False
    if g.engagement_ids is None and g.site_ids is None:
        return True
    deps = _deps(db, c, lines_of(db, c.id))
    return any(acommon.grant_covers(g, d.site_ids, d.engagement_id) for d in deps)


def get_visible(db: Session, p: Principal, certificate_id: uuid.UUID) -> EquipmentCertificate:
    c = get_row(db, certificate_id)
    if not _covered(db, p, c, C.cert_register_view):
        raise not_found("Certificate")
    return c


def _require_on(db: Session, p: Principal, c: EquipmentCertificate, cap: Capability) -> None:
    p.ensure_writer()
    if not _covered(db, p, c, cap):
        raise forbidden_error()


# ---- validity ------------------------------------------------------------------------------------


def compute_line(
    s: Any, item: EquipmentItem, c: EquipmentCertificate, line: EquipmentCertLine
) -> None:
    """§6.1 strictest-wins stored on the line."""
    months = cset.interval_months(s, item.category) or 12
    vu, lf, end = validity.line_validity(c.inspected_on, c.printed_next_due, months)
    line.valid_until, line.limiting_factor, line.interval_end = vu, lf, end


def line_validity_read(
    db: Session, c: EquipmentCertificate, line: EquipmentCertLine, at: datetime, s: Any = None
) -> CertValidity:
    d = acommon.local_day(at)
    if c.status in (CS.draft, CS.historic, CS.rejected):
        ev = validity.LineEval(False, None, line.valid_until)
        if c.status == CS.historic:
            ev.reason = ref.R.CERT_EXPIRED
    else:
        ev = validity.eval_line(db, c, line, at, s, c.project_id)
    return CertValidity(
        valid_until=line.valid_until,
        limiting_factor=line.limiting_factor,
        printed_date=c.printed_next_due,
        platform_end=line.interval_end,
        days_left=(line.valid_until - d).days if line.valid_until else None,
        in_force=ev.in_force,
        not_in_force_reason=ev.reason,
        expiring=ev.expiring,
        in_force_from=c.in_force_from if ev.in_force else None,
        unverified_window_until=ev.window_until,
    )


# ---- validation (EC-1…EC-8, EQ-4, CF-1, CF-3) ----------------------------------------------------


@dataclass
class Issue:
    status: int
    code: str
    en: str
    ar: str
    field: str | None = None
    meta: dict[str, Any] | None = None
    equipment_id: uuid.UUID | None = None

    def error(self) -> ApiError:
        if self.code == ErrorCode.VALIDATION_ERROR:
            return validation_error(self.field or "body", self.en)
        meta = dict(self.meta or {})
        if self.field:
            meta.setdefault("field", self.field)
        return ApiError(self.status, ErrorCode(self.code), self.en, self.ar, meta=meta or None)

    def warning(self) -> ApiWarning:
        return cc.warn(self.code, self.en, self.ar, self.field)


@dataclass
class Checked:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    tpi_reason: str | None = None
    items: dict[uuid.UUID, EquipmentItem] = field(default_factory=dict)


@dataclass
class Draft:
    """Certificate fields under validation (from a create body or a stored row)."""

    tpi_id: uuid.UUID
    cert_no: str
    inspection_type: CertInspectionType
    inspected_on: date
    issued_on: date
    printed_next_due: date | None
    tpi_verification_url: str | None
    configuration_event_id: uuid.UUID | None
    scan_attachment_id: uuid.UUID | None
    historic: bool
    lines: list[CertLineInput]


def _v(field_: str, en: str, eq: uuid.UUID | None = None) -> Issue:
    return Issue(422, ErrorCode.VALIDATION_ERROR, en, en, field_, equipment_id=eq)


def _attr_missing(item: EquipmentItem) -> str | None:
    """EQ-4 category-required attributes, first missing field."""
    docs = {d.get("doc_type") for d in item.documents or []}
    devs = set(item.safety_devices or [])
    if item.category in ref.CRANES:
        if item.rated_capacity_t is None:
            return "rated_capacity_t"
        if item.max_radius_m is None:
            return "max_radius_m"
        if "load_chart" not in docs:
            return "load_chart"
        if SafetyDevice.lmi_rci.value not in devs:
            return "safety_devices"
        if item.category == Q.tower_crane:
            if "foundation_design" not in docs:
                return "foundation_design"
            if "erection_drawing" not in docs:
                return "erection_drawing"
            if SafetyDevice.anemometer.value not in devs:
                return "anemometer"
    if item.category == Q.mewp:
        if item.max_height_m is None:
            return "max_height_m"
        if item.persons_capacity is None:
            return "persons_capacity"
    if item.category == Q.pressure_vessel:
        if not item.pressure:
            return "pressure"
        if "written_scheme" not in docs:
            return "written_scheme"
    return None


def _first_submit(db: Session, item_id: uuid.UUID, exclude: uuid.UUID | None) -> bool:
    stmt = (
        select(func.count())
        .select_from(EquipmentCertLine)
        .join(EquipmentCertificate, EquipmentCertificate.id == EquipmentCertLine.certificate_id)
        .where(
            EquipmentCertLine.equipment_id == item_id,
            EquipmentCertificate.status.notin_([CS.draft, CS.historic]),
        )
    )
    if exclude is not None:
        stmt = stmt.where(EquipmentCertificate.id != exclude)
    return not (db.scalar(stmt) or 0)


def _norm_cfg(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _event_for(db: Session, d: Draft, item_ids: set[uuid.UUID]) -> ConfigurationEvent | None:
    if d.configuration_event_id is not None:
        return db.get(ConfigurationEvent, d.configuration_event_id)
    return None


def check(
    db: Session,
    project_id: uuid.UUID,
    d: Draft,
    *,
    cert_id: uuid.UUID | None = None,
    submit: bool = False,
    at: datetime | None = None,
) -> Checked:
    out = Checked()
    at = at or now()
    day = acommon.local_day(at)
    s = cset.get(db, project_id)
    t = db.get(Tpi, d.tpi_id)
    if t is None:
        out.errors.append(
            Issue(404, ErrorCode.NOT_FOUND, "TPI not found.", "الجهة غير موجودة.", "tpi_id")
        )
        return out
    # EC-2 dates
    if d.issued_on < d.inspected_on:
        out.errors.append(_v("issued_on", "issued_on must be on or after inspected_on."))
    if d.issued_on > day:
        out.errors.append(_v("issued_on", "issued_on cannot be in the future."))
    if d.printed_next_due is not None and d.printed_next_due <= d.inspected_on:
        out.errors.append(_v("printed_next_due", "printed_next_due must be after inspected_on."))
    # EC-1
    q = select(EquipmentCertificate).where(
        EquipmentCertificate.tpi_id == d.tpi_id,
        func.upper(EquipmentCertificate.cert_no) == d.cert_no.strip().upper(),
    )
    if cert_id is not None:
        q = q.where(EquipmentCertificate.id != cert_id)
    other = db.scalar(q)
    new_items = {ln.equipment_id for ln in d.lines}
    if other is not None:
        old_items = {ln.equipment_id for ln in lines_of(db, other.id)}
        if old_items & new_items or not old_items:
            out.errors.append(
                Issue(
                    409,
                    ErrorCode.CERT_EXISTS,
                    "This certificate number already exists for this TPI.",
                    "رقم الشهادة مسجل مسبقاً لهذه الجهة.",
                    "cert_no",
                )
            )
        else:
            ex = db.get(EquipmentItem, next(iter(old_items)))
            out.errors.append(
                Issue(
                    409,
                    ErrorCode.CERT_NO_REUSED,
                    "This certificate number is already used on another item — "
                    "check for a fake certificate.",
                    "رقم الشهادة مستخدم لمعدة أخرى — تحقق من احتمال التزوير.",
                    "cert_no",
                    meta={
                        "existing_equipment_no": ex.equipment_no if ex else None,
                        "existing_certificate_id": str(other.id),
                    },
                )
            )
    # lines
    seen: set[uuid.UUID] = set()
    owners: set[uuid.UUID] = set()
    cats: set[str] = set()
    colour = s.lifting_gear_colour_scheme or {}
    max_vu: date | None = None
    for i, ln in enumerate(d.lines):
        f = f"lines[{i}]"
        if ln.equipment_id in seen:
            out.errors.append(_v(f"{f}.equipment_id", "One line per item.", ln.equipment_id))
            continue
        seen.add(ln.equipment_id)
        item = db.get(EquipmentItem, ln.equipment_id)
        if item is None:
            out.errors.append(
                Issue(
                    404,
                    ErrorCode.NOT_FOUND,
                    "Equipment not found.",
                    "المعدة غير موجودة.",
                    f"{f}.equipment_id",
                    equipment_id=ln.equipment_id,
                )
            )
            continue
        out.items[item.id] = item
        owners.add(item.owner_contractor_id)
        cats.add(item.category.value)
        dep = db.scalar(
            select(EquipmentDeployment).where(
                EquipmentDeployment.equipment_id == item.id,
                EquipmentDeployment.project_id == project_id,
                EquipmentDeployment.status != EquipmentDeploymentStatus.cancelled,
            )
        )
        if dep is None:
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.EQUIPMENT_NOT_DEPLOYED,
                    f"{item.equipment_no} is not deployed on this project.",
                    f"المعدة {item.equipment_no} غير معيّنة في هذا المشروع.",
                    f"{f}.equipment_id",
                    equipment_id=item.id,
                )
            )
        if item.service_status == ServiceStatus.retired:
            out.errors.append(
                Issue(
                    409,
                    ErrorCode.EQUIPMENT_RETIRED,
                    f"{item.equipment_no} is retired.",
                    f"المعدة {item.equipment_no} مسحوبة من الخدمة.",
                    f"{f}.equipment_id",
                    equipment_id=item.id,
                )
            )
        if item.service_status == ServiceStatus.blacklisted:
            out.errors.append(
                Issue(
                    409,
                    ErrorCode.EQUIPMENT_BLACKLISTED,
                    f"{item.equipment_no} is blacklisted.",
                    f"المعدة {item.equipment_no} محظورة.",
                    f"{f}.equipment_id",
                    equipment_id=item.id,
                )
            )
        # EC-5
        if cc.serial_norm(ln.serial_as_printed) != item.serial_norm:
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.SERIAL_MISMATCH,
                    f"Serial on the certificate does not match {item.equipment_no}.",
                    f"الرقم التسلسلي في الشهادة لا يطابق المعدة {item.equipment_no}.",
                    f"{f}.serial_as_printed",
                    equipment_id=item.id,
                )
            )
        passing = ln.result in PASSING
        # EC-8
        if (
            ln.swl_t is not None
            and item.rated_capacity_t is not None
            and Decimal(ln.swl_t) > item.rated_capacity_t
        ):
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.SWL_ABOVE_RATING,
                    "SWL is above the item's rated capacity.",
                    "الحمولة الآمنة أعلى من سعة المعدة المقررة.",
                    f"{f}.swl_t",
                    equipment_id=item.id,
                )
            )
        if passing and item.category in ref.LIFTING_CATEGORIES and ln.swl_t is None:
            out.errors.append(_v(f"{f}.swl_t", "SWL is required for lifting equipment.", item.id))
        if (
            passing
            and item.category in ref.LIFTING_DUTY_CATEGORIES
            and item.lifting_duty
            and ln.lifting_duty_certified
            and ln.swl_t is None
        ):
            out.errors.append(
                _v(f"{f}.swl_t", "SWL is required when lifting duty is certified (EC-9).", item.id)
            )
        # EC-7
        needs_lt = item.category in ref.LOAD_TEST_CATEGORIES and (
            d.inspection_type in (IT.initial, IT.after_configuration_change)
            or (d.inspection_type == IT.after_repair and ln.structural_repair)
        )
        lt = ln.load_test
        if (
            passing
            and needs_lt
            and not (
                lt is not None
                and lt.performed
                and lt.percent_of_swl is not None
                and Decimal(lt.percent_of_swl) >= 100
            )
        ):
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.LOAD_TEST_REQUIRED,
                    "A load test (≥ 100 % of SWL) is required for this inspection.",
                    "يلزم اختبار تحميل (100 % من الحمولة الآمنة على الأقل) لهذا الفحص.",
                    f"{f}.load_test",
                    equipment_id=item.id,
                )
            )
        # EC-12
        if (
            colour.get("enabled")
            and item.category == Q.lifting_accessory
            and passing
            and ln.colour_code is None
        ):
            out.errors.append(
                _v(f"{f}.colour_code", "Colour code is required (colour scheme enabled).", item.id)
            )
        # EQ-4 (at Submit of the first certificate)
        if submit and _first_submit(db, item.id, cert_id):
            miss = _attr_missing(item)
            if miss:
                out.errors.append(
                    Issue(
                        422,
                        ErrorCode.ATTRIBUTE_REQUIRED,
                        f"{item.equipment_no}: {miss} is required before the first certificate.",
                        f"{item.equipment_no}: الحقل {miss} مطلوب قبل أول شهادة.",
                        miss,
                        meta={"field": miss, "equipment_id": str(item.id)},
                        equipment_id=item.id,
                    )
                )
        # §6.1 / W01
        months = cset.interval_months(s, item.category) or 12
        vu, _lf, end = validity.line_validity(d.inspected_on, d.printed_next_due, months)
        max_vu = vu if max_vu is None or vu > max_vu else max_vu
        if d.printed_next_due is not None and d.printed_next_due > end:
            out.warnings.append(
                Issue(
                    200,
                    "W01",
                    f"Printed next due is beyond the {months}-month interval: valid "
                    f"until {vu.isoformat()}.",
                    f"تاريخ الفحص التالي المطبوع يتجاوز فترة {months} شهراً: "
                    f"صالحة حتى {vu.isoformat()}.",
                    "printed_next_due",
                    equipment_id=item.id,
                )
            )
        # CF-3
        evs = list(
            db.scalars(
                select(ConfigurationEvent).where(
                    ConfigurationEvent.equipment_id == item.id,
                    ConfigurationEvent.cleared_at.is_(None),
                )
            )
        )
        linked = (
            db.get(ConfigurationEvent, d.configuration_event_id)
            if d.configuration_event_id
            else None
        )
        if linked is not None and linked.equipment_id == item.id and linked not in evs:
            evs.append(linked)
        for ev in evs:
            if passing and _norm_cfg(ln.configuration_ref) != _norm_cfg(ev.new_configuration):
                out.warnings.append(
                    Issue(
                        200,
                        ErrorCode.CONFIGURATION_MISMATCH,
                        "Inspected configuration differs from the recorded change: "
                        f"{ev.new_configuration}.",
                        f"التهيئة المفحوصة تختلف عن التغيير المسجل: {ev.new_configuration}.",
                        f"{f}.configuration_ref",
                        equipment_id=item.id,
                    )
                )
                break
    # CF-1 linked event
    if d.configuration_event_id is not None:
        cev = db.get(ConfigurationEvent, d.configuration_event_id)
        if cev is None or cev.equipment_id not in new_items:
            out.errors.append(
                _v(
                    "configuration_event_id",
                    "The configuration event is not for an item on this certificate.",
                )
            )
        elif d.inspected_on < acommon.local_day(cev.occurred_at):
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.INSPECTION_BEFORE_EVENT,
                    "The inspection is before the configuration change.",
                    "الفحص سابق لتغيير التهيئة.",
                    "inspected_on",
                )
            )
    # EC-2 already expired
    if max_vu is not None and max_vu < day and not d.historic:
        out.errors.append(
            Issue(
                422,
                ErrorCode.CERT_ALREADY_EXPIRED,
                "This certificate has already expired.",
                "انتهت صلاحية هذه الشهادة.",
                "printed_next_due",
            )
        )
    # EC-3 / EC-4
    if not d.historic:
        acc = tsvc.acceptability(
            db, t, d.inspected_on, categories=sorted(cats), project_id=project_id
        )
        if not acc.ok:
            out.tpi_reason = acc.reason or "TPI_NOT_APPROVED"
            e = tsvc.not_acceptable(out.tpi_reason, "tpi_id")
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.TPI_NOT_ACCEPTABLE,
                    e.message,
                    e.message_ar or e.message,
                    "tpi_id",
                    meta={"reason": out.tpi_reason},
                )
            )
        if not tsvc.independent(db, t, owners):
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.TPI_NOT_INDEPENDENT,
                    "The TPI is not independent of the equipment owner.",
                    "الجهة غير مستقلة عن مالك المعدة.",
                    "tpi_id",
                )
            )
        elif acc.ok and tsvc.accreditation_lapsed_note(db, t, d.inspected_on):
            out.warnings.append(
                Issue(
                    200,
                    "TPI_ACCREDITATION_LAPSED",
                    "The TPI's accreditation has lapsed since this inspection.",
                    "انتهى اعتماد الجهة بعد هذا الفحص.",
                    "tpi_id",
                )
            )
    for w in vf.foreign_url_warning(t, d.tpi_verification_url):
        out.warnings.append(Issue(200, w.code, w.message, w.message_ar or w.message, w.field))
    if submit:  # noqa: SIM102
        if d.scan_attachment_id is None:
            out.errors.append(
                Issue(
                    422,
                    ErrorCode.SCAN_REQUIRED,
                    "Attach the certificate scan (PDF) before submitting.",
                    "أرفق نسخة الشهادة (PDF) قبل التقديم.",
                    "scan_attachment_id",
                )
            )
    return out


def _check_scan(db: Session, scan_id: uuid.UUID | None, cert_id: uuid.UUID | None) -> None:
    if scan_id is None:
        return
    a = db.get(Attachment, scan_id)
    if (
        a is None
        or a.owner_type != AttachmentOwner.equipment_certificate_scan
        or (cert_id is not None and a.owner_id != cert_id)
    ):
        raise validation_error("scan_attachment_id", "Upload the scan to this certificate first.")


def _draft_of(
    c: EquipmentCertificate, lines: list[EquipmentCertLine], historic: bool = False
) -> Draft:
    return Draft(
        tpi_id=c.tpi_id,
        cert_no=c.cert_no,
        inspection_type=c.inspection_type,
        inspected_on=c.inspected_on,
        issued_on=c.issued_on,
        printed_next_due=c.printed_next_due,
        tpi_verification_url=c.tpi_verification_url,
        configuration_event_id=c.configuration_event_id,
        scan_attachment_id=c.scan_attachment_id,
        historic=historic,
        lines=[_line_input(ln) for ln in lines],
    )


def _line_input(ln: EquipmentCertLine) -> CertLineInput:
    return CertLineInput.model_validate(
        {
            "equipment_id": ln.equipment_id,
            "serial_as_printed": ln.serial_as_printed,
            "result": ln.result,
            "swl_t": ln.swl_t,
            "configuration_ref": ln.configuration_ref,
            "load_test": ln.load_test,
            "structural_repair": ln.structural_repair,
            "lifting_duty_certified": ln.lifting_duty_certified,
            "colour_code": ln.colour_code,
            "limitations": ln.limitations or [],
            "defects": ln.defects_input or [],
        }
    )


def _raise_first(ch: Checked) -> None:
    if ch.errors:
        order = {404: 0, 409: 1, 422: 2}
        first = sorted(ch.errors, key=lambda i: order.get(i.status, 3))[0]
        raise first.error()


# ---- read ----------------------------------------------------------------------------------------


_ACTIONS: dict[CertificateStatus, tuple[str, str]] = {
    CS.submitted: ("Submit", "تقديم"),
    CS.draft: ("Return to submitter", "إعادة لمقدمها"),
    CS.accepted: ("Accept", "قبول"),
    CS.rejected: ("Reject", "رفض"),
    CS.suspended: ("Suspend", "إيقاف"),
    CS.revoked: ("Revoke", "إلغاء"),
    CS.historic: ("Attach as history", "إرفاق كسجل تاريخي"),
}


def allowed(
    db: Session, p: Principal, c: EquipmentCertificate, cap_check: bool = True
) -> list[AllowedCertAction]:
    out: list[CertificateStatus] = []

    def has(cap: Capability) -> bool:
        try:
            p.ensure_writer()
        except ApiError:
            return False
        return _covered(db, p, c, cap)

    if c.status == CS.draft:
        if has(C.equipment_edit):
            out.append(CS.submitted)
        if has(C.cert_review):
            out.append(CS.historic)
    elif c.status == CS.submitted:
        if has(C.cert_review) and not cc.contractor_only(p, c.project_id):
            out += [CS.draft, CS.rejected]
            if c.submitted_by_user_id != p.user.id:
                out.append(CS.accepted)
    elif c.status == CS.accepted:
        if has(C.cert_suspend):
            out.append(CS.suspended)
        if has(C.cert_review) and not cc.contractor_only(p, c.project_id):
            out.append(CS.revoked)
    elif c.status == CS.suspended:
        if has(C.cert_suspend) and c.status_reason != CertStatusReason.configuration_changed:
            out.append(CS.accepted)
        if has(C.cert_review) and not cc.contractor_only(p, c.project_id):
            out.append(CS.revoked)
    labels = dict(_ACTIONS)
    if c.status == CS.suspended:
        labels[CS.accepted] = ("Reinstate", "إعادة التفعيل")
    return [
        AllowedCertAction(to_status=s, label_en=labels[s][0], label_ar=labels[s][1]) for s in out
    ]


def _load_test(v: dict[str, Any] | None) -> LoadTestRead | None:
    if not v:
        return None
    return LoadTestRead(
        performed=bool(v.get("performed")),
        percent_of_swl=v.get("percent_of_swl"),
        test_weight_t=v.get("test_weight_t"),
    )


def line_read(
    db: Session, c: EquipmentCertificate, ln: EquipmentCertLine, at: datetime, s: Any = None
) -> CertLineRead:
    item = db.get(EquipmentItem, ln.equipment_id)
    assert item is not None  # noqa: S101
    defects = list(
        db.scalars(
            select(EquipmentDefect)
            .where(EquipmentDefect.cert_line_id == ln.id)
            .order_by(EquipmentDefect.raised_at)
        )
    )
    return CertLineRead(
        id=ln.id,
        equipment=cc.equipment_ref(db, item),
        serial_as_printed=ln.serial_as_printed,
        result=ln.result,
        swl_t=ln.swl_t,
        configuration_ref=ln.configuration_ref,
        load_test=_load_test(ln.load_test),
        structural_repair=ln.structural_repair,
        lifting_duty_certified=ln.lifting_duty_certified,
        colour_code=ln.colour_code,
        limitations=cc.limitation_reads(ln.limitations),
        defects=[cc.defect_ref(x) for x in defects],
        validity=line_validity_read(db, c, ln, at, s),
        superseded_by_line_id=ln.superseded_by_line_id,
        suspended_for_configuration=ln.suspended_for_configuration,
    )


def cert_read(db: Session, p: Principal, c: EquipmentCertificate) -> EquipmentCertificateRead:
    at = now()
    s = cset.get(db, c.project_id)
    lines = lines_of(db, c.id)
    t = tsvc.get(db, c.tpi_id)
    refs = Refs(db).load(users=[c.submitted_by_user_id, c.reviewed_by_user_id])
    warnings: list[ApiWarning] = []
    if c.status in (CS.draft, CS.submitted):
        ch = check(db, c.project_id, _draft_of(c, lines), cert_id=c.id, at=at)
        warnings = [w.warning() for w in ch.warnings]
        warnings += [e.warning() for e in ch.errors if e.code == ErrorCode.CERT_NO_REUSED]
    else:
        warnings = [
            cc.warn(w.code, w.message, w.message_ar or w.message, w.field)
            for w in vf.foreign_url_warning(t, c.tpi_verification_url)
        ]
    line_reads = [line_read(db, c, ln, at, s) for ln in lines]
    if any(lr.validity.unverified_window_until for lr in line_reads):
        warnings.append(
            cc.warn(
                "CERT_UNVERIFIED",
                "Accepted but not yet verified with the TPI.",
                "مقبولة ولم يتم التحقق منها لدى الجهة بعد.",
            )
        )
    vus = [ln.valid_until for ln in lines if ln.valid_until]
    hse = cc.is_hse(p, c.project_id) or p.grant(c.project_id, C.cert_register_view) is not None
    return EquipmentCertificateRead(
        id=c.id,
        project_id=c.project_id,
        cert_no=c.cert_no,
        tpi=cc.tpi_ref(t, p, c.project_id),
        inspection_type=c.inspection_type,
        inspected_on=c.inspected_on,
        issued_on=c.issued_on,
        printed_next_due=c.printed_next_due,
        inspector_name=c.inspector_name if hse else None,
        inspector_staff_no=c.inspector_staff_no,
        scan_attachment_id=c.scan_attachment_id,
        tpi_verification_url=c.tpi_verification_url,
        configuration_event_id=c.configuration_event_id,
        status=c.status,
        status_reason=c.status_reason,
        status_reason_text=c.status_reason_text,
        verification_status=c.verification_status,
        verification_due_on=c.verification_due_on,
        source=c.source,
        submitted_by=refs.user(c.submitted_by_user_id),
        submitted_at=c.submitted_at,
        reviewed_by=refs.user(c.reviewed_by_user_id),
        reviewed_at=c.reviewed_at,
        accepted_at=c.accepted_at,
        verified_at=c.verified_at,
        in_force_from=c.in_force_from,
        valid_until=max(vus) if vus else None,
        lines=line_reads,
        warnings=warnings,
        allowed_actions=allowed(db, p, c),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def read(db: Session, p: Principal, certificate_id: uuid.UUID) -> EquipmentCertificateRead:
    return cert_read(db, p, get_visible(db, p, certificate_id))


def list_certificates(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None = None,
    statuses: list[CertificateStatus] | None = None,
    verification_statuses: list[VerificationStatus] | None = None,
    tpi_id: uuid.UUID | None = None,
    equipment_id: uuid.UUID | None = None,
    categories: list[EquipmentCertCategory] | None = None,
    inspection_types: list[CertInspectionType] | None = None,
    source: CertSource | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    in_force: bool | None = None,
    expiring_days: int | None = None,
    verification_overdue: bool | None = None,
) -> EquipmentCertificatePage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, C.cert_register_view)
    if g is None:
        raise forbidden_error()
    stmt = select(EquipmentCertificate).where(EquipmentCertificate.project_id == project.id)

    def line_exists(*conds: Any) -> Any:
        sub = (
            select(EquipmentCertLine.id)
            .join(EquipmentItem, EquipmentItem.id == EquipmentCertLine.equipment_id)
            .where(EquipmentCertLine.certificate_id == EquipmentCertificate.id, *conds)
        )
        return exists(sub)

    def dep_exists(*conds: Any) -> Any:
        sub = (
            select(EquipmentDeployment.id)
            .join(
                EquipmentCertLine,
                EquipmentCertLine.equipment_id == EquipmentDeployment.equipment_id,
            )
            .where(
                EquipmentCertLine.certificate_id == EquipmentCertificate.id,
                EquipmentDeployment.project_id == EquipmentCertificate.project_id,
                *conds,
            )
        )
        return exists(sub)

    if g.engagement_ids is not None:
        stmt = stmt.where(dep_exists(EquipmentDeployment.engagement_id.in_(list(g.engagement_ids))))
    if g.site_ids is not None:
        stmt = stmt.where(dep_exists(EquipmentDeployment.site_ids.overlap(list(g.site_ids))))
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                EquipmentCertificate.cert_no.ilike(pat),
                dep_exists(EquipmentDeployment.tag.ilike(pat)),
                line_exists(EquipmentItem.equipment_no.ilike(pat)),
            )
        )
    if statuses:
        stmt = stmt.where(EquipmentCertificate.status.in_(statuses))
    if verification_statuses:
        stmt = stmt.where(EquipmentCertificate.verification_status.in_(verification_statuses))
    if tpi_id:
        stmt = stmt.where(EquipmentCertificate.tpi_id == tpi_id)
    if equipment_id:
        stmt = stmt.where(line_exists(EquipmentCertLine.equipment_id == equipment_id))
    if categories:
        stmt = stmt.where(line_exists(EquipmentItem.category.in_(categories)))
    if inspection_types:
        stmt = stmt.where(EquipmentCertificate.inspection_type.in_(inspection_types))
    if source is not None:
        stmt = stmt.where(EquipmentCertificate.source == source)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(dep_exists(EquipmentDeployment.engagement_id.in_(ids)))
    d0 = today()
    if verification_overdue is not None:
        cond = (
            EquipmentCertificate.status.in_([CS.submitted, CS.accepted])
            & EquipmentCertificate.verification_status.in_([VS.not_verified, VS.unable_to_verify])
            & (EquipmentCertificate.verification_due_on < d0)
        )
        stmt = stmt.where(cond if verification_overdue else ~cond)
    stmt = stmt.order_by(EquipmentCertificate.inspected_on.desc(), EquipmentCertificate.cert_no)
    at = now()
    s = cset.get(db, project.id)
    if in_force is None and expiring_days is None:
        rows, total = paginate(db, stmt, page, page_size)
        items = [_list_item(db, c, at, s) for c in rows]
    else:
        all_items = [_list_item(db, c, at, s) for c in db.scalars(stmt)]
        if in_force is not None:
            all_items = [i for i in all_items if i.in_force == in_force]
        if expiring_days is not None:
            lim = d0 + timedelta(days=expiring_days)
            all_items = [
                i for i in all_items if i.in_force and i.valid_until and i.valid_until <= lim
            ]
        total = len(all_items)
        items = all_items[(page - 1) * page_size : page * page_size]
    return EquipmentCertificatePage(items=items, total=total, page=page, page_size=page_size)


def _list_item(
    db: Session, c: EquipmentCertificate, at: datetime, s: Any
) -> EquipmentCertificateListItem:
    lines = lines_of(db, c.id)
    t = db.get(Tpi, c.tpi_id)
    tags: list[str] = []
    cats: list[str] = []
    best: tuple[date | None, Any] = (None, None)
    any_force = False
    for ln in lines:
        item = db.get(EquipmentItem, ln.equipment_id)
        if item is not None and item.category.value not in cats:
            cats.append(item.category.value)
        dep = cc.latest_deployment_on(db, ln.equipment_id, c.project_id)
        if dep is not None and len(tags) < 5:
            tags.append(dep.tag)
        if c.status not in (CS.draft, CS.historic, CS.rejected):
            ev = validity.eval_line(db, c, ln, at, s, c.project_id)
            any_force = any_force or ev.in_force
        if ln.valid_until and (best[0] is None or ln.valid_until > best[0]):
            best = (ln.valid_until, ln.limiting_factor)
    return EquipmentCertificateListItem(
        id=c.id,
        cert_no=c.cert_no,
        tpi_code=t.tpi_code if t else "",
        inspection_type=c.inspection_type,
        inspected_on=c.inspected_on,
        status=c.status,
        verification_status=c.verification_status,
        line_count=len(lines),
        equipment_tags=tags,
        categories=cats,
        valid_until=best[0],
        limiting_factor=best[1],
        in_force=any_force,
        source=c.source,
        submitted_at=c.submitted_at,
    )


# ---- create / update / preview -------------------------------------------------------------------


def _draft_from_body(body: EquipmentCertificateCreate) -> Draft:
    return Draft(
        tpi_id=body.tpi_id,
        cert_no=body.cert_no.strip(),
        inspection_type=body.inspection_type,
        inspected_on=body.inspected_on,
        issued_on=body.issued_on,
        printed_next_due=body.printed_next_due,
        tpi_verification_url=body.tpi_verification_url,
        configuration_event_id=body.configuration_event_id,
        scan_attachment_id=body.scan_attachment_id,
        historic=body.historic,
        lines=list(body.lines),
    )


def _require_create(
    db: Session, p: Principal, project_id: uuid.UUID, lines: Iterable[CertLineInput], historic: bool
) -> None:
    project = projects.get_visible(db, p, project_id)
    cap = C.cert_review if historic else C.equipment_edit
    g = cc.require(p, project.id, cap)
    if g.engagement_ids is None and g.site_ids is None:
        return
    for ln in lines:
        dep = cc.latest_deployment_on(db, ln.equipment_id, project.id)
        if dep is None or not acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
            raise forbidden_error()


def _line_values(ln: CertLineInput) -> dict[str, Any]:
    return {
        "equipment_id": ln.equipment_id,
        "serial_as_printed": ln.serial_as_printed.strip(),
        "result": ln.result,
        "swl_t": ln.swl_t,
        "configuration_ref": ln.configuration_ref,
        "load_test": ln.load_test.model_dump(mode="json") if ln.load_test else None,
        "structural_repair": ln.structural_repair,
        "lifting_duty_certified": ln.lifting_duty_certified,
        "colour_code": ln.colour_code,
        "limitations": [x.model_dump(mode="json") for x in ln.limitations],
        "defects_input": [x.model_dump(mode="json") for x in ln.defects],
    }


def _write_lines(db: Session, c: EquipmentCertificate, lines: list[CertLineInput]) -> None:
    s = cset.get(db, c.project_id)
    for old in lines_of(db, c.id):
        db.delete(old)
    db.flush()
    for ln in lines:
        item = db.get(EquipmentItem, ln.equipment_id)
        assert item is not None  # noqa: S101
        row = EquipmentCertLine(id=uuid.uuid4(), certificate_id=c.id, **_line_values(ln))
        compute_line(s, item, c, row)
        db.add(row)
    db.flush()


def create(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: EquipmentCertificateCreate,
    *,
    source: CertSource = CertSource.manual,
    batch_id: uuid.UUID | None = None,
) -> EquipmentCertificateRead:
    _require_create(db, p, project_id, body.lines, body.historic)
    d = _draft_from_body(body)
    ch = check(db, project_id, d)
    _raise_first(ch)
    if body.scan_attachment_id is not None:
        _check_scan(db, body.scan_attachment_id, None)
    c = new_row(db, p, project_id, body, source=source, batch_id=batch_id)
    return cert_read(db, p, c)


def new_row(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    body: EquipmentCertificateCreate,
    *,
    source: CertSource = CertSource.manual,
    batch_id: uuid.UUID | None = None,
    seed_fake: bool = False,
) -> EquipmentCertificate:
    data = body.model_dump(exclude={"lines", "historic"})
    data["cert_no"] = body.cert_no.strip()
    c = EquipmentCertificate(
        id=uuid.uuid4(),
        project_id=project_id,
        status=CS.historic if body.historic else CS.draft,
        verification_status=VS.not_verified,
        source=source,
        import_batch_id=batch_id,
        alerts_sent=[],
        **data,
    )
    cc.stamp(c, p, create=True)
    db.add(c)
    db.flush()
    _write_lines(db, c, list(body.lines))
    if body.scan_attachment_id is not None:
        a = db.get(Attachment, body.scan_attachment_id)
        if a is not None and a.owner_type == AttachmentOwner.equipment_certificate_scan:
            a.owner_id = c.id
    cc.record(
        db,
        p,
        AuditAction.create,
        EntityType.equipment_certificate,
        c,
        project_id,
        details={"lines": len(body.lines)},
    )
    return c


def preview(
    db: Session, p: Principal, project_id: uuid.UUID, body: EquipmentCertificateCreate
) -> EquipmentCertPreview:
    project = projects.get_visible(db, p, project_id)
    _require_create(db, p, project.id, body.lines, bool(body.historic))
    d = _draft_from_body(body)
    ch = check(db, project.id, d, submit=True)
    ch.errors = [
        e for e in ch.errors if e.code != ErrorCode.SCAN_REQUIRED or body.scan_attachment_id is None
    ]
    s = cset.get(db, project.id)
    day = today()
    lines = []
    for ln in body.lines:
        item = ch.items.get(ln.equipment_id)
        months = (cset.interval_months(s, item.category) if item else None) or 12
        vu, lf, end = validity.line_validity(body.inspected_on, body.printed_next_due, months)
        lines.append(
            EquipmentCertPreviewLine(
                equipment_id=ln.equipment_id,
                validity=CertValidity(
                    valid_until=vu,
                    limiting_factor=lf,
                    printed_date=body.printed_next_due,
                    platform_end=end,
                    days_left=(vu - day).days,
                    in_force=False,
                    not_in_force_reason=None,
                    expiring=False,
                    in_force_from=None,
                ),
                errors=[e.warning() for e in ch.errors if e.equipment_id == ln.equipment_id],
                warnings=[w.warning() for w in ch.warnings if w.equipment_id == ln.equipment_id],
            )
        )
    return EquipmentCertPreview(
        tpi_acceptable=ch.tpi_reason is None,
        tpi_reason=ch.tpi_reason,
        errors=[e.warning() for e in ch.errors if e.equipment_id is None],
        warnings=[w.warning() for w in ch.warnings if w.equipment_id is None],
        lines=lines,
    )


def update(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: EquipmentCertificateUpdate
) -> EquipmentCertificateRead:
    c = get_visible(db, p, certificate_id)
    _require_on(db, p, c, C.equipment_edit)
    if c.status != CS.draft:
        raise invalid_transition("Certificate", c.status.value, "edit")
    before = cc.snap(c)
    ch_ = body.changes()
    new_lines = ch_.pop("lines", None)
    for k, v in ch_.items():
        setattr(c, k, v.strip() if k == "cert_no" and isinstance(v, str) else v)
    if "scan_attachment_id" in ch_:
        _check_scan(db, c.scan_attachment_id, c.id)
    if new_lines is not None:
        _require_create(db, p, c.project_id, body.lines or [], False)
    lines_in = (
        list(body.lines) if body.lines is not None else [_line_input(x) for x in lines_of(db, c.id)]
    )
    d = _draft_from_body_like(c, lines_in)
    _raise_first(check(db, c.project_id, d, cert_id=c.id))
    cc.stamp(c, p)
    db.flush()
    _write_lines(db, c, lines_in)
    cc.record(db, p, AuditAction.update, EntityType.equipment_certificate, c, c.project_id, before)
    return cert_read(db, p, c)


def _draft_from_body_like(c: EquipmentCertificate, lines: list[CertLineInput]) -> Draft:
    d = _draft_of(c, [])
    d.lines = lines
    return d


# ---- transitions (§4.4) --------------------------------------------------------------------------


def _reason(body: CertTransitionRequest, n: int = 1) -> str:
    r = (body.reason or "").strip()
    if len(r) < n:
        raise validation_error("reason", f"Give a reason (≥ {n} characters).")
    return r


def _items(db: Session, c: EquipmentCertificate) -> list[EquipmentItem]:
    out = []
    for ln in lines_of(db, c.id):
        it = db.get(EquipmentItem, ln.equipment_id)
        if it is not None:
            out.append(it)
    return out


def _publish(db: Session, c: EquipmentCertificate) -> None:
    events.publish(
        db,
        "cert.status_changed",
        project_id=c.project_id,
        item_ids=[ln.equipment_id for ln in lines_of(db, c.id)],
    )


def recompute_items(
    db: Session, c: EquipmentCertificate, p: Principal | None, at: datetime | None = None
) -> None:
    from app.services.cert import equipment as esvc  # noqa: PLC0415

    for item in _items(db, c):
        esvc.recompute(db, item, at, p)


def transition(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: CertTransitionRequest
) -> EquipmentCertificateRead:
    c = get_visible(db, p, certificate_id)
    src, dst = c.status, body.to_status
    before = cc.snap(c)
    at = now()
    details: dict[str, Any] = {"from": src.value, "to": dst.value}
    if src == CS.draft and dst == CS.submitted:
        _require_on(db, p, c, C.equipment_edit)
        lines = lines_of(db, c.id)
        if c.scan_attachment_id is None:
            latest = db.scalar(
                select(Attachment)
                .where(
                    Attachment.owner_type == AttachmentOwner.equipment_certificate_scan,
                    Attachment.owner_id == c.id,
                )
                .order_by(Attachment.created_at.desc())
                .limit(1)
            )
            if latest is not None:
                c.scan_attachment_id = latest.id
        _raise_first(check(db, c.project_id, _draft_of(c, lines), cert_id=c.id, submit=True, at=at))
        submit(db, p, c, at)
    elif src == CS.draft and dst == CS.historic:
        _require_on(db, p, c, C.cert_review)
        lines = lines_of(db, c.id)
        if any(ln.valid_until and ln.valid_until >= today() for ln in lines):
            raise validation_error(
                "to_status", "Only an already-expired certificate can be attached as history."
            )
        c.status = CS.historic
    elif src == CS.submitted and dst == CS.draft:
        _require_on(db, p, c, C.cert_review)
        c.status_reason_text = _reason(body, 10)
        c.status = CS.draft
        if c.submitted_by_user_id:
            alerts.send(
                db,
                [c.submitted_by_user_id],
                NotificationKind.certificate_returned,
                f"Certificate {c.cert_no} returned",
                f"أعيدت الشهادة {c.cert_no}",
                EntityType.equipment_certificate,
                c.id,
                c.project_id,
                body_en=c.status_reason_text,
                body_ar=c.status_reason_text,
            )
    elif src == CS.submitted and dst == CS.accepted:
        _require_on(db, p, c, C.cert_review)
        if cc.contractor_only(p, c.project_id):
            raise forbidden_error()
        if c.submitted_by_user_id == p.user.id:
            raise cc.sod()
        lines = lines_of(db, c.id)
        ch = check(db, c.project_id, _draft_of(c, lines), cert_id=c.id, at=at)
        _raise_first(
            Checked(errors=[e for e in ch.errors if e.code != ErrorCode.CERT_ALREADY_EXPIRED])
        )
        if any(w.code == ErrorCode.CONFIGURATION_MISMATCH for w in ch.warnings):
            if not body.configuration_mismatch_confirmed:
                raise ApiError(
                    422,
                    ErrorCode.CONFIGURATION_MISMATCH,
                    "The inspected configuration differs from the recorded change — "
                    "confirm to accept.",
                    "التهيئة المفحوصة تختلف عن التغيير المسجل — أكّد للقبول.",
                )
            c.configuration_mismatch_confirmed = True
        accept(db, p, c, at)
    elif src == CS.submitted and dst == CS.rejected:
        _require_on(db, p, c, C.cert_review)
        c.status_reason_text = _reason(body)
        c.status_reason = body.reason_code or CertStatusReason.document_review
        c.status = CS.rejected
        c.reviewed_by_user_id, c.reviewed_at = p.user.id, at
        c.ended_on = today()
    elif src == CS.accepted and dst == CS.suspended:
        _require_on(db, p, c, C.cert_suspend)
        c.status_reason_text = _reason(body)
        c.status_reason = body.reason_code or CertStatusReason.hse_suspension
        if c.status_reason == CertStatusReason.configuration_changed:
            raise validation_error("reason_code", "Record a configuration event instead.")
        c.status = CS.suspended
    elif src == CS.suspended and dst == CS.accepted:
        _require_on(db, p, c, C.cert_suspend)
        if c.status_reason == CertStatusReason.configuration_changed:
            raise ApiError(
                409,
                ErrorCode.CONFIGURATION_CHANGED,
                "A configuration change needs a new certificate; it cannot be reinstated.",
                "تغيير التهيئة يتطلب شهادة جديدة؛ لا يمكن إعادة التفعيل.",
            )
        c.status_reason_text = _reason(body)
        c.status_reason = None
        c.status = CS.accepted
    elif src in (CS.accepted, CS.suspended) and dst == CS.revoked:
        _require_on(db, p, c, C.cert_review)
        if cc.contractor_only(p, c.project_id):
            raise forbidden_error()
        c.status_reason_text = _reason(body)
        c.status_reason = body.reason_code or CertStatusReason.tpi_revocation_notice
        c.status = CS.revoked
        c.ended_on = today()
    else:
        raise invalid_transition("Certificate", src.value, dst.value)
    cc.stamp(c, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.equipment_certificate,
        c,
        c.project_id,
        before,
        details,
    )
    if c.status != src:  # noqa: SIM102
        if c.status in (CS.accepted, CS.suspended, CS.revoked) or src in (
            CS.accepted,
            CS.suspended,
        ):
            recompute_items(db, c, p, at)
            _publish(db, c)
    return cert_read(db, p, c)


def submit(db: Session, p: Principal | None, c: EquipmentCertificate, at: datetime) -> None:
    s = cset.get(db, c.project_id)
    c.status = CS.submitted
    c.status_reason_text = None
    c.submitted_by_user_id = p.user.id if p is not None else c.submitted_by_user_id
    c.submitted_at = at
    c.verification_due_on = vf.due_on(acommon.local_day(at), s.verification_due_days)
    tags = [d.tag for d in _deps(db, c, lines_of(db, c.id))]
    alerts.send(
        db,
        alerts.officers(db, c.project_id),
        NotificationKind.certificate_submitted,
        f"Certificate {c.cert_no} submitted for review ({', '.join(tags[:3])})",
        f"قُدمت الشهادة {c.cert_no} للمراجعة ({', '.join(tags[:3])})",
        EntityType.equipment_certificate,
        c.id,
        c.project_id,
    )


def accept(db: Session, p: Principal | None, c: EquipmentCertificate, at: datetime) -> None:
    """Submitted → Accepted: EC-6 failures, DF-2 defects, EC-10 supersession, in force when
    verified."""
    from app.services.cert import defects as dsvc  # noqa: PLC0415
    from app.services.cert import equipment as esvc  # noqa: PLC0415

    c.status = CS.accepted
    c.status_reason = None
    c.reviewed_by_user_id = p.user.id if p is not None else None
    c.reviewed_at = at
    c.accepted_at = at
    db.flush()
    for ln in lines_of(db, c.id):
        item = db.get(EquipmentItem, ln.equipment_id)
        if item is None:
            continue
        eng = esvc.engagement_for(db, item, c.project_id)
        failed = ln.result == LineResult.fail
        if failed:
            _supersede_older(db, c, ln)
            esvc.set_status(
                db,
                item,
                ServiceStatus.out_of_service,
                ServiceStatusReason.failed_inspection,
                p,
                ref_=c.cert_no,
                at=at,
            )
            rec: set[uuid.UUID] = set()
            for us in esvc.stop_use_recipients(db, item).values():
                rec |= us
            alerts.send(
                db,
                rec,
                NotificationKind.equipment_stop_use,
                f"STOP USE: {item.equipment_no} failed its TPI inspection ({c.cert_no})",
                f"أوقف الاستخدام: المعدة {item.equipment_no} لم تجتز فحص الجهة ({c.cert_no})",
                EntityType.equipment_item,
                item.id,
                c.project_id,
                email=True,
            )
        defects_in = list(ln.defects_input or [])
        if (
            failed
            and not any(x.get("category") == DefectCategory.A.value for x in defects_in)
            and not defects_in
        ):
            defects_in = [
                {
                    "category": "A",
                    "description_en": f"Failed TPI inspection {c.cert_no}",
                    "description_ar": f"لم تجتز فحص الجهة {c.cert_no}",
                }
            ]
        for x in defects_in:
            dsvc.new_defect(
                db,
                c.project_id,
                item=item,
                scaffold=None,
                engagement_id=eng.id if eng else None,
                source=DefectSource.tpi_inspection,
                category=DefectCategory(x["category"]),
                description_en=x["description_en"],
                description_ar=x.get("description_ar"),
                raised_at=at,
                p=p,
                cert_line_id=ln.id,
                source_ref=c.cert_no,
                tpi_due_date=date.fromisoformat(x["tpi_due_date"])
                if x.get("tpi_due_date")
                else None,
                apply_effects=not failed,
            )
    maybe_in_force(db, c, p, at)


def _supersede_older(db: Session, c: EquipmentCertificate, ln: EquipmentCertLine) -> None:
    """EC-10: older lines of the same item → superseded by `ln`."""
    rows = db.execute(
        select(EquipmentCertificate, EquipmentCertLine)
        .join(EquipmentCertLine, EquipmentCertLine.certificate_id == EquipmentCertificate.id)
        .where(
            EquipmentCertLine.equipment_id == ln.equipment_id,
            EquipmentCertLine.id != ln.id,
            EquipmentCertLine.superseded_by_line_id.is_(None),
            EquipmentCertificate.status.in_([CS.accepted, CS.expired]),
            EquipmentCertificate.inspected_on <= c.inspected_on,
        )
    ).all()
    for oc, ol in rows:
        if oc.id == c.id or (oc.inspected_on == c.inspected_on and oc.created_at > c.created_at):
            continue
        ol.superseded_by_line_id = ln.id
        db.flush()
        if oc.status == CS.accepted and all(x.superseded_by_line_id for x in lines_of(db, oc.id)):
            oc.status = CS.superseded
            oc.status_reason = CertStatusReason.newer_certificate
            oc.ended_on = today()
            cc.record(
                db,
                None,
                AuditAction.status_change,
                EntityType.equipment_certificate,
                oc,
                oc.project_id,
                details={"from": "accepted", "to": "superseded", "by": c.cert_no},
            )


def maybe_in_force(db: Session, c: EquipmentCertificate, p: Principal | None, at: datetime) -> None:
    """Accepted and verified → in force: older lines superseded (EC-10), CF-1 events cleared,
    items recomputed."""
    from app.services.cert import equipment as esvc  # noqa: PLC0415

    if (
        c.status != CS.accepted
        or c.verification_status != VS.verified
        or c.in_force_from is not None
    ):
        recompute_items(db, c, p, at)
        return
    c.in_force_from = max(x for x in (c.accepted_at, c.verified_at) if x is not None)
    db.flush()
    for ln in lines_of(db, c.id):
        if ln.result not in PASSING:
            continue
        _supersede_older(db, c, ln)
        item = db.get(EquipmentItem, ln.equipment_id)
        if item is not None:
            esvc.clear_config_events(db, item, ln, c)
    db.flush()
    recompute_items(db, c, p, at)


# ---- verification --------------------------------------------------------------------------------


def verifications(db: Session, p: Principal, certificate_id: uuid.UUID) -> VerificationList:
    c = get_visible(db, p, certificate_id)
    return vf.list_for(db, p, CertKind.equipment, c)


def verify(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: VerificationCreate
) -> VerificationRead:
    c = get_visible(db, p, certificate_id)
    items = _items(db, c)
    tags = [d.tag for d in _deps(db, c, lines_of(db, c.id))]

    def on_change(before: VS, after: VS, rec: Any) -> None:
        at = rec.performed_at
        if after == VS.verified:
            maybe_in_force(db, c, p, at)
        elif after == VS.failed:
            vf.fail_effects(c)
            c.ended_on = today()
            recompute_items(db, c, p, at)
        _publish(db, c)

    return vf.record(
        db,
        p,
        CertKind.equipment,
        c,
        body,
        holder_contractors=[i.owner_contractor_id for i in items],
        on_change=on_change,
        holder_ref=", ".join(tags[:3]) or c.cert_no,
    )


# ---- jobs ----------------------------------------------------------------------------------------


def expiry_job(db: Session, at: datetime | None = None) -> int:
    """EC-13: Accepted → Expired when every line's valid_until < today; items recomputed."""
    at = at or now()
    d = acommon.local_day(at)
    n = 0
    for c in db.scalars(
        select(EquipmentCertificate).where(EquipmentCertificate.status == CS.accepted)
    ):
        lines = lines_of(db, c.id)
        if lines and all(ln.valid_until is not None and ln.valid_until < d for ln in lines):
            c.status = CS.expired
            c.ended_on = d
            cc.record(
                db,
                None,
                AuditAction.status_change,
                EntityType.equipment_certificate,
                c,
                c.project_id,
                details={"from": "accepted", "to": "expired"},
            )
            recompute_items(db, c, None, at)
            _publish(db, c)
            n += 1
    return n
