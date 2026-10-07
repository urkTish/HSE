"""Airport pass reference lists, applications and issued passes (spec 2-access-permits §3.6-§3.9,
§4.4, §4.5, §5.4 AP-1…AP-14)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    BackgroundCheckStatus,
    CredentialReason,
    CustodyStatus,
    DeploymentStatus,
    HookKind,
    HookSubjectType,
    InductionType,
    PassApplicationStatus,
    PassApplicationType,
    ValidityStatus,
    WorkerStatus,
)
from app.core.clock import now, today
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EmployerType,
    EntityType,
    NotificationKind,
    ZoneType,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.text import like_pattern
from app.kpi.periods import add_months
from app.models import (
    Adp,
    AirportPass,
    Attachment,
    Deployment,
    InductionCourse,
    PassApplication,
    PassArea,
    PassCategory,
    Project,
    ProjectEngagement,
    User,
    Worker,
    Zone,
    ZoneAccessProfile,
)
from app.schemas.access_common import HookRequirementRead
from app.schemas.airport_passes import (
    AirportPassPage,
    AirportPassRead,
    BackgroundCheckRead,
    BackgroundCheckUpdate,
    PassApplicationCreate,
    PassApplicationPage,
    PassApplicationRead,
    PassApplicationTransitionRequest,
    PassApplicationUpdate,
    PassAreaCreate,
    PassAreaList,
    PassAreaRead,
    PassAreaUpdate,
    PassCategoryCreate,
    PassCategoryList,
    PassCategoryRead,
    PassCategoryUpdate,
    PassIssueRequest,
)
from app.schemas.hse_common import ApiWarning
from app.services import attachments, audit, notify, projects
from app.services.access import common, credentials, eligibility, lifecycle, profiles, workers
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
PS = PassApplicationStatus
OPEN = (PS.draft, PS.submitted, PS.endorsed, PS.lodged, PS.approved)
ID_SOON_DAYS = 30
STATUS_LABEL: dict[PassApplicationStatus, tuple[str, str]] = {
    PS.draft: ("Draft", "مسودة"),
    PS.submitted: ("Submitted", "مُقدَّم"),
    PS.endorsed: ("Endorsed by sponsor", "مُعتمد من الراعي"),
    PS.lodged: ("Lodged with authority", "مُقدَّم للجهة"),
    PS.approved: ("Approved", "موافق عليه"),
    PS.refused: ("Refused by issuing authority", "مرفوض من جهة الإصدار"),
    PS.issued: ("Issued", "صادر"),
    PS.withdrawn: ("Withdrawn", "مسحوب"),
    PS.cancelled: ("Cancelled", "ملغى"),
}


def _airport(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = projects.get_visible(db, p, project_id)
    common.require_airport(project)
    return project


def _hooks_json(items: list[Any]) -> list[dict[str, Any]]:
    out = []
    for h in items:
        d = h if isinstance(h, dict) else h.model_dump()
        out.append(
            {
                "kind": str(getattr(d["kind"], "value", d["kind"])),
                "code": d["code"],
                "trades": [str(getattr(t, "value", t)) for t in d.get("trades") or []],
            }
        )
    return out


# ---- AP-CAT --------------------------------------------------------------------------------------


def category_read(c: PassCategory) -> PassCategoryRead:
    return PassCategoryRead(
        id=c.id,
        project_id=c.project_id,
        code=c.code,
        name_en=c.name_en,
        name_ar=c.name_ar,
        escorted=c.escorted,
        background_check_required=c.background_check_required,
        max_validity_days=c.max_validity_days,
        card_colour=c.card_colour,
        allows_adp=c.allows_adp,
        hook_requirements=[HookRequirementRead(**h) for h in c.hook_requirements or []],
        active=c.active,
    )


def list_categories(db: Session, p: Principal, project_id: uuid.UUID) -> PassCategoryList:
    project = _airport(db, p, project_id)
    rows = db.scalars(
        select(PassCategory)
        .where(PassCategory.project_id == project.id)
        .order_by(PassCategory.code)
    )
    return PassCategoryList(items=[category_read(c) for c in rows])


def _check_category(db: Session, project_id: uuid.UUID, c: PassCategory) -> None:
    s = common.settings(db, project_id)
    if c.max_validity_days > s.pass_max_validity_months * 31:
        raise validation_error(
            "max_validity_days", f"At most {s.pass_max_validity_months * 31} days (setting)."
        )
    if c.escorted and c.allows_adp:
        raise validation_error("allows_adp", "Escorted categories cannot allow an ADP (DP-3).")
    if not c.escorted and not c.background_check_required:
        raise validation_error(
            "background_check_required", "Unescorted categories need a background check (AP-4)."
        )


def _cat_snapshot(c: PassCategory) -> dict[str, Any]:
    return {
        k: getattr(c, k)
        for k in (
            "code", "name_en", "name_ar", "escorted", "background_check_required",
            "max_validity_days", "card_colour", "allows_adp", "hook_requirements", "active",
        )
    }  # fmt: skip


def create_category(
    db: Session, p: Principal, project_id: uuid.UUID, body: PassCategoryCreate
) -> PassCategoryRead:
    project = _airport(db, p, project_id)
    p.require(project.id, C.access_settings_edit)
    code = body.code.strip().upper()
    if db.scalar(
        select(PassCategory.id).where(
            PassCategory.project_id == project.id, PassCategory.code == code
        )
    ):
        raise duplicate("code", "A category with this code already exists.")
    c = PassCategory(
        id=uuid.uuid4(),
        project_id=project.id,
        code=code,
        name_en=body.name_en,
        name_ar=body.name_ar,
        escorted=body.escorted,
        background_check_required=body.background_check_required,
        max_validity_days=body.max_validity_days,
        card_colour=body.card_colour,
        allows_adp=body.allows_adp,
        hook_requirements=_hooks_json(body.hook_requirements),
        active=body.active,
    )
    _check_category(db, project.id, c)
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.airport_pass_category,
        entity_id=c.id,
        project_id=project.id,
        after=_cat_snapshot(c),
    )
    return category_read(c)


def update_category(
    db: Session, p: Principal, category_id: uuid.UUID, body: PassCategoryUpdate
) -> PassCategoryRead:
    c = db.get(PassCategory, category_id)
    if c is None:
        raise not_found("Pass category")
    _airport(db, p, c.project_id)
    p.require(c.project_id, C.access_settings_edit)
    before = _cat_snapshot(c)
    ch = body.changes()
    if "hook_requirements" in ch:
        ch["hook_requirements"] = _hooks_json(ch["hook_requirements"])
    for k, v in ch.items():
        setattr(c, k, v)
    _check_category(db, c.project_id, c)
    db.flush()
    bf, af = audit.diff(before, _cat_snapshot(c))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(c.project_id),
            entity_type=EntityType.airport_pass_category,
            entity_id=c.id,
            project_id=c.project_id,
            before=bf,
            after=af,
        )
    return category_read(c)


# ---- AP-AREA -------------------------------------------------------------------------------------


def area_read(a: PassArea, refs: Refs) -> PassAreaRead:
    return PassAreaRead(
        id=a.id,
        project_id=a.project_id,
        code=a.code,
        name_en=a.name_en,
        name_ar=a.name_ar,
        colour=a.colour,
        area_kind=a.area_kind,
        zones=[z for z in (refs.zone(zid) for zid in a.zone_ids or []) if z is not None],
        active=a.active,
    )


def list_areas(db: Session, p: Principal, project_id: uuid.UUID) -> PassAreaList:
    project = _airport(db, p, project_id)
    rows = list(
        db.scalars(
            select(PassArea).where(PassArea.project_id == project.id).order_by(PassArea.code)
        )
    )
    refs = Refs(db).load(zones=[z for a in rows for z in a.zone_ids or []])
    return PassAreaList(items=[area_read(a, refs) for a in rows])


def _check_zones(db: Session, project_id: uuid.UUID, zone_ids: list[uuid.UUID]) -> None:
    for zid in zone_ids:
        z = db.get(Zone, zid)
        if z is None or z.project_id != project_id or z.zone_type != ZoneType.airside:
            raise validation_error("zone_ids", "Areas map only to airside zones of the project.")


def _sync_profiles(db: Session, a: PassArea) -> None:
    for zid in a.zone_ids or []:
        prof = db.get(ZoneAccessProfile, zid)
        if prof is not None and prof.airport_pass_area_code is None:
            z = db.get(Zone, zid)
            if z is not None and z.security_restricted_area:
                prof.airport_pass_area_code = a.code


def create_area(
    db: Session, p: Principal, project_id: uuid.UUID, body: PassAreaCreate
) -> PassAreaRead:
    project = _airport(db, p, project_id)
    p.require(project.id, C.access_settings_edit)
    code = body.code.strip().upper()
    if db.scalar(
        select(PassArea.id).where(PassArea.project_id == project.id, PassArea.code == code)
    ):
        raise duplicate("code", "An area with this code already exists.")
    _check_zones(db, project.id, body.zone_ids)
    a = PassArea(
        id=uuid.uuid4(),
        project_id=project.id,
        code=code,
        name_en=body.name_en,
        name_ar=body.name_ar,
        colour=body.colour,
        area_kind=body.area_kind,
        zone_ids=list(dict.fromkeys(body.zone_ids)),
        active=body.active,
    )
    db.add(a)
    db.flush()
    _sync_profiles(db, a)
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.airport_pass_area,
        entity_id=a.id,
        project_id=project.id,
        after={"code": a.code, "zone_ids": [str(z) for z in a.zone_ids]},
    )
    return area_read(a, Refs(db))


def update_area(
    db: Session, p: Principal, area_id: uuid.UUID, body: PassAreaUpdate
) -> PassAreaRead:
    a = db.get(PassArea, area_id)
    if a is None:
        raise not_found("Pass area")
    _airport(db, p, a.project_id)
    p.require(a.project_id, C.access_settings_edit)
    ch = body.changes()
    if "zone_ids" in ch:
        _check_zones(db, a.project_id, ch["zone_ids"])
        ch["zone_ids"] = list(dict.fromkeys(ch["zone_ids"]))
    before = {k: getattr(a, k) for k in ch}
    for k, v in ch.items():
        setattr(a, k, v)
    db.flush()
    _sync_profiles(db, a)
    bf, af = audit.diff(before, {k: getattr(a, k) for k in ch})
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.airport_pass_area,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
    return area_read(a, Refs(db))


# ---- AP-6 validity limit -------------------------------------------------------------------------


def max_valid_until(
    db: Session, w: Worker, d: Deployment, cat: PassCategory | None, day: date
) -> tuple[date | None, str | None]:
    s = common.settings(db, d.project_id)
    eng = db.get(ProjectEngagement, d.engagement_id) if d.engagement_id else None
    project = db.get(Project, d.project_id)
    terms: list[tuple[date | None, str]] = [
        (w.id_expiry_date, "worker.id_expiry_date"),
        (d.planned_demob_on, "deployment.planned_demob_on"),
        (eng.demobilisation_date if eng else None, "engagement.demobilisation_date"),
        (project.planned_end_date if project else None, "project.planned_end_date"),
    ]
    if cat is not None:
        if cat.code == "VIS":
            terms.append(
                (day + timedelta(days=s.visitor_pass_max_days - 1), "visitor_pass_max_days")
            )
        elif cat.code == "TEMP-E" or (cat.escorted and cat.code.startswith("TEMP")):
            terms.append(
                (
                    day + timedelta(days=s.temp_escorted_pass_max_days - 1),
                    "temp_escorted_pass_max_days",
                )
            )
        terms.append((day + timedelta(days=cat.max_validity_days), "category.max_validity_days"))
    best: tuple[date, str] | None = None
    for v, k in terms:
        if v is not None and (best is None or v < best[0]):
            best = (v, k)
    return (best[0], best[1]) if best else (None, None)


def _check_validity(db: Session, w: Worker, d: Deployment, cat: PassCategory, until: date) -> None:
    limit, field = max_valid_until(db, w, d, cat, today())
    if limit is not None and until > limit:
        raise ApiError(
            422,
            ErrorCode.VALIDITY_EXCEEDS_LIMIT,
            f"requested_valid_until is after {limit.isoformat()} ({field}) (AP-6).",
            f"الصلاحية المطلوبة تتجاوز {limit.isoformat()}.",
            meta={"limiting_factor": field, "max": limit.isoformat()},
        )


# ---- applications --------------------------------------------------------------------------------


def _can_bg(p: Principal | None, project_id: uuid.UUID) -> bool:
    return p is not None and p.grant(project_id, C.background_check_view) is not None


def _id_copy(db: Session, app_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(Attachment.id)
        .where(
            Attachment.owner_type == AttachmentOwner.pass_application_id_copy,
            Attachment.owner_id == app_id,
        )
        .order_by(Attachment.created_at.desc())
        .limit(1)
    )


def application_read(
    db: Session,
    p: Principal | None,
    a: PassApplication,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> PassApplicationRead:
    refs = refs or Refs(db)
    w = db.get(Worker, a.worker_id)
    d = db.get(Deployment, a.deployment_id)
    assert w is not None and d is not None  # noqa: S101
    cat = _category(db, a.project_id, a.pass_category)
    s = common.settings(db, a.project_id)
    day = today()
    days_lodged = (day - common.local_day(a.lodged_at)).days if a.lodged_at else None
    stale = bool(
        a.status == PS.lodged and days_lodged is not None and days_lodged > s.application_stale_days
    )
    en, ar = STATUS_LABEL[a.status]
    bg_ok = _can_bg(p, a.project_id)
    copy_id = _id_copy(db, a.id)
    extra: dict[str, Any] = {}
    if bg_ok:
        bg = lifecycle.background(a)
        extra["background_check"] = BackgroundCheckRead(
            status=BackgroundCheckStatus(
                bg.get("status")
                or (
                    BackgroundCheckStatus.not_required.value
                    if cat is not None and not cat.background_check_required
                    else BackgroundCheckStatus.submitted.value
                )
            ),
            check_date=date.fromisoformat(bg["check_date"]) if bg.get("check_date") else None,
            recheck_due=date.fromisoformat(bg["recheck_due"]) if bg.get("recheck_due") else None,
        )
        extra["outcome_note"] = a.outcome_note
    if copy_id and p is not None and p.grant(a.project_id, C.worker_unmask_id):
        extra["id_copy_attachment_id"] = copy_id
    return PassApplicationRead(
        id=a.id,
        application_no=a.application_no,
        project_id=a.project_id,
        application_type=a.application_type,
        worker=common.worker_ref(w, common.can_see_names(p, a.project_id)),
        deployment_id=d.id,
        sponsor_engagement=refs.eng(a.sponsor_engagement_id),
        sponsor_letter_ref=a.sponsor_letter_ref,
        client_sponsor=refs.user(a.client_sponsor_user_id),
        pass_category=a.pass_category,
        requested_area_codes=list(a.requested_area_codes or []),
        requested_valid_until=a.requested_valid_until,
        max_valid_until=max_valid_until(db, w, d, cat, day)[0],
        justification=a.justification,
        has_id_copy=copy_id is not None or a.id_copy_deleted_at is not None,
        prerequisite_snapshot=a.prerequisite_snapshot,
        submitted_at=a.submitted_at,
        submitted_by=refs.user(a.submitted_by_user_id),
        lodged_at=a.lodged_at,
        authority_ref=a.authority_ref,
        days_lodged=days_lodged if a.status == PS.lodged else None,
        stale=stale,
        status=a.status,
        status_label_en=en,
        status_label_ar=ar,
        issued_pass_id=a.issued_pass_id,
        warnings=warnings or [],
        created_at=a.created_at,
        updated_at=a.updated_at,
        **extra,
    )


def _bg_read_audit(db: Session, p: Principal, apps: list[PassApplication]) -> None:
    if not apps or not _can_bg(p, apps[0].project_id):
        return
    for a in apps:
        if a.background_enc is None and not a.outcome_note:
            continue
        audit.record(
            db,
            AuditAction.sensitive_field_read,
            p.actor(a.project_id),
            entity_type=EntityType.pass_application,
            entity_id=a.id,
            project_id=a.project_id,
            fields_read=["background_check", "outcome_note"],
        )


def _category(db: Session, project_id: uuid.UUID, code: str) -> PassCategory | None:
    return db.scalar(
        select(PassCategory).where(PassCategory.project_id == project_id, PassCategory.code == code)
    )


def get_application(
    db: Session, p: Principal, app_id: uuid.UUID
) -> tuple[PassApplication, Deployment]:
    a = db.get(PassApplication, app_id)
    if a is None:
        raise not_found("Pass application")
    projects.get_visible(db, p, a.project_id)
    d = db.get(Deployment, a.deployment_id)
    assert d is not None  # noqa: S101
    if workers.dep_covered(p, d, C.worker_view) is None:
        raise forbidden_error("This application is outside your scope.")
    return a, d


def read_application(db: Session, p: Principal, app_id: uuid.UUID) -> PassApplicationRead:
    a, _ = get_application(db, p, app_id)
    _bg_read_audit(db, p, [a])
    return application_read(db, p, a)


def list_applications(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[PassApplicationStatus] | None,
    application_type: PassApplicationType | None,
    worker_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    stale: bool | None,
    q: str | None,
) -> PassApplicationPage:
    project = _airport(db, p, project_id)
    if p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(PassApplication)
        .join(Deployment, Deployment.id == PassApplication.deployment_id)
        .join(Worker, Worker.id == PassApplication.worker_id)
        .where(PassApplication.project_id == project.id, workers.dep_clause(p, C.worker_view))
    )
    conds: list[ColumnElement[bool]] = []
    if statuses:
        conds.append(PassApplication.status.in_(statuses))
    if application_type:
        conds.append(PassApplication.application_type == application_type)
    if worker_id:
        conds.append(PassApplication.worker_id == worker_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        conds.append(PassApplication.sponsor_engagement_id.in_(ids))
    if stale is not None:
        s = common.settings(db, project.id)
        cutoff = common.local_midnight_utc(today() - timedelta(days=s.application_stale_days))
        cond = (PassApplication.status == PS.lodged) & (PassApplication.lodged_at < cutoff)
        conds.append(cond if stale else ~cond)
    if q:
        pat = like_pattern(q)
        conds.append(PassApplication.application_no.ilike(pat) | Worker.search_text.ilike(pat))
    stmt = stmt.where(*conds).order_by(PassApplication.created_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    rows = list(rows)
    _bg_read_audit(db, p, rows)
    refs = Refs(db).load(
        engs=[a.sponsor_engagement_id for a in rows],
        users=[u for a in rows for u in (a.client_sponsor_user_id, a.submitted_by_user_id)],
    )
    return PassApplicationPage(
        items=[application_read(db, p, a, refs) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _validate_areas(
    db: Session, project_id: uuid.UUID, d: Deployment, codes: list[str], justification: str
) -> list[str]:
    codes = list(dict.fromkeys(c.strip().upper() for c in codes))
    areas = {
        a.code: a
        for a in db.scalars(
            select(PassArea).where(PassArea.project_id == project_id, PassArea.active.is_(True))
        )
    }
    sites = set(d.site_ids or [])
    for c in codes:
        a = areas.get(c)
        if a is None:
            raise validation_error("requested_area_codes", f"Unknown area code {c}.")
        mapped = any(
            (z := db.get(Zone, zid)) is not None and z.site_id in sites for zid in a.zone_ids or []
        )
        if not mapped and len(justification.strip()) < 20:
            raise validation_error(
                "justification",
                f"Area {c} maps to no zone of the worker's sites: give a justification "
                "(≥ 20 characters).",
            )
    return codes


def _contractor_status(db: Session, engagement_id: uuid.UUID | None) -> ContractorStatus | None:
    c = common.engagement_contractor(db, engagement_id)
    return c.status if c else None


def _contractor_suspended() -> ApiError:
    return ApiError(
        403,
        ErrorCode.CONTRACTOR_SUSPENDED,
        "The contractor is suspended: new applications are blocked (LC-7).",
        "المقاول موقوف: الطلبات الجديدة محظورة.",
    )


def create_application(
    db: Session, p: Principal, project_id: uuid.UUID, body: PassApplicationCreate
) -> PassApplicationRead:
    project = _airport(db, p, project_id)
    d = db.get(Deployment, body.deployment_id)
    if d is None or d.project_id != project.id:
        raise validation_error("deployment_id", "Unknown deployment on this project.")
    common.require_cap(p, project.id, C.pass_application_create, d.site_ids, d.engagement_id)
    if d.status == DeploymentStatus.demobilised:
        raise validation_error("deployment_id", "The deployment is demobilised.")
    w = db.get(Worker, d.worker_id)
    assert w is not None  # noqa: S101
    if w.status == WorkerStatus.banned:
        raise ApiError(409, ErrorCode.WORKER_BANNED, "The worker is banned.", "العامل محظور.")
    if _contractor_status(db, d.engagement_id) in (
        ContractorStatus.suspended,
        ContractorStatus.blacklisted,
    ):
        raise _contractor_suspended()
    open_app = db.scalar(
        select(PassApplication).where(
            PassApplication.worker_id == w.id,
            PassApplication.project_id == project.id,
            PassApplication.status.in_(OPEN),
        )
    )
    if open_app is not None:
        raise ApiError(
            409,
            ErrorCode.APPLICATION_OPEN,
            f"{open_app.application_no} is still open for this worker (AP-3).",
            "يوجد طلب مفتوح لهذا العامل.",
            meta={"application_no": open_app.application_no, "id": str(open_app.id)},
        )
    cat = _category(db, project.id, body.pass_category.strip().upper())
    if cat is None or not cat.active:
        raise validation_error("pass_category", "Unknown pass category.")
    codes = _validate_areas(db, project.id, d, body.requested_area_codes, body.justification)
    _check_validity(db, w, d, cat, body.requested_valid_until)
    year = today().year
    seq = next_seq(db, PassApplication, project.id, year)
    a = PassApplication(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        application_no=make_ref("APA", project.code, year, seq, 4),
        project_id=project.id,
        application_type=body.application_type,
        worker_id=w.id,
        deployment_id=d.id,
        sponsor_engagement_id=d.engagement_id,
        sponsor_letter_ref=body.sponsor_letter_ref,
        pass_category=cat.code,
        requested_area_codes=codes,
        requested_valid_until=body.requested_valid_until,
        justification=body.justification,
        status=PS.draft,
        created_by_user_id=p.user.id,
    )
    if not cat.background_check_required:
        lifecycle.set_background(a, {"status": BackgroundCheckStatus.not_required.value})
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.pass_application,
        entity_id=a.id,
        project_id=project.id,
        after={
            "application_no": a.application_no,
            "worker_no": w.worker_no,
            "pass_category": cat.code,
            "requested_area_codes": codes,
            "requested_valid_until": a.requested_valid_until.isoformat(),
        },
    )
    return application_read(db, p, a)


def update_application(
    db: Session, p: Principal, app_id: uuid.UUID, body: PassApplicationUpdate
) -> PassApplicationRead:
    a, d = get_application(db, p, app_id)
    common.require_cap(p, a.project_id, C.pass_application_create, d.site_ids, d.engagement_id)
    if a.status != PS.draft:
        raise invalid_transition("Application", a.status, "edited")
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    ch = body.changes()
    before = {k: getattr(a, k) for k in ch}
    if "pass_category" in ch:
        ch["pass_category"] = ch["pass_category"].strip().upper()
        cat0 = _category(db, a.project_id, ch["pass_category"])
        if cat0 is None or not cat0.active:
            raise validation_error("pass_category", "Unknown pass category.")
    for k, v in ch.items():
        setattr(a, k, v)
    cat = _category(db, a.project_id, a.pass_category)
    assert cat is not None  # noqa: S101
    a.requested_area_codes = _validate_areas(
        db, a.project_id, d, list(a.requested_area_codes), a.justification
    )
    _check_validity(db, w, d, cat, a.requested_valid_until)
    a.updated_by_user_id = p.user.id
    a.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, {k: getattr(a, k) for k in ch})
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.pass_application,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
    return application_read(db, p, a)


def prerequisites(
    db: Session, w: Worker, d: Deployment, a: PassApplication, at: datetime
) -> list[eligibility.Item]:
    """AP-7: Valid GEN + AIR of the project, the induction requirements of the zones mapped by
    the requested areas, and the category hooks (HK-2)."""
    s = common.settings(db, a.project_id)
    courses = {
        c.code: c
        for c in db.scalars(
            select(InductionCourse).where(InductionCourse.project_id == a.project_id)
        )
    }
    needed: list[str] = []
    for kind in (InductionType.general_site, InductionType.airside):
        code = profiles.course_code(db, a.project_id, kind)
        if code:
            needed.append(code)
    for area in db.scalars(
        select(PassArea).where(
            PassArea.project_id == a.project_id, PassArea.code.in_(a.requested_area_codes)
        )
    ):
        for zid in area.zone_ids or []:
            z = db.get(Zone, zid)
            if z is not None:
                needed += list(profiles.ensure(db, z).required_inductions or [])
    items: list[eligibility.Item] = []
    for code in dict.fromkeys(needed):
        items += eligibility.induction_item(db, w.id, a.project_id, courses.get(code), code, at, s)
    cat = _category(db, a.project_id, a.pass_category)
    for h in (cat.hook_requirements if cat else None) or []:
        if h.get("trades") and d.trade.value not in h["trades"]:
            continue
        items.append(
            eligibility.hook_item(
                db, HookSubjectType.worker, w.id, HookKind(h["kind"]), h["code"], at, s
            )
        )
    return items


def _notify_update(db: Session, a: PassApplication, what_en: str, what_ar: str) -> None:
    users: set[uuid.UUID] = set(contractor_reps(db, a.project_id, a.sponsor_engagement_id))
    if a.submitted_by_user_id:
        users.add(a.submitted_by_user_id)
    if a.created_by_user_id:
        users.add(a.created_by_user_id)
    notify.notify(
        db,
        users,
        NotificationKind.pass_application_update,
        f"{a.application_no}: {what_en}",
        f"{a.application_no}: {what_ar}",
        None,
        None,
        EntityType.pass_application,
        a.id,
        a.project_id,
    )


def _photo(db: Session, worker_id: uuid.UUID) -> bool:
    return workers.photo_id(db, worker_id) is not None


def transition(
    db: Session, p: Principal, app_id: uuid.UUID, body: PassApplicationTransitionRequest
) -> PassApplicationRead:
    a, d = get_application(db, p, app_id)
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    to = body.to_status
    frm = a.status
    at = now()
    before = {"status": frm.value}
    details: dict[str, Any] = {}

    def need(cap: Capability) -> None:
        common.require_cap(p, a.project_id, cap, d.site_ids, d.engagement_id)

    def reason(min_len: int = 10) -> str:
        if not body.reason or len(body.reason.strip()) < min_len:
            raise validation_error(
                "reason", f"A reason of at least {min_len} characters is required."
            )
        return body.reason.strip()

    if frm == PS.draft and to == PS.submitted:
        need(C.pass_application_create)
        if d.status != DeploymentStatus.mobilised:
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "The worker's deployment must be mobilised (AP-5).",
                "يجب أن يكون العامل معبأً في المشروع.",
            )
        if w.status == WorkerStatus.banned:
            raise ApiError(409, ErrorCode.WORKER_BANNED, "The worker is banned.", "العامل محظور.")
        if _contractor_status(db, d.engagement_id) in (
            ContractorStatus.suspended,
            ContractorStatus.blacklisted,
        ):
            raise _contractor_suspended()
        if not _photo(db, w.id):
            raise ApiError(
                422,
                ErrorCode.PHOTO_REQUIRED,
                "A worker photo is required before submitting (AP-5).",
                "يلزم وجود صورة العامل قبل التقديم.",
            )
        if a.application_type in (PassApplicationType.new, PassApplicationType.renewal) and not (
            _id_copy(db, a.id)
        ):
            raise validation_error("id_copy", "Upload the ID copy before submitting.")
        if w.id_expiry_date is not None and w.id_expiry_date <= today() + timedelta(
            days=ID_SOON_DAYS
        ):
            raise ApiError(
                422,
                ErrorCode.ID_EXPIRES_SOON,
                f"The worker's ID expires within {ID_SOON_DAYS} days (AP-5).",
                "تنتهي هوية العامل خلال 30 يوماً.",
            )
        cat = _category(db, a.project_id, a.pass_category)
        assert cat is not None  # noqa: S101
        _check_validity(db, w, d, cat, a.requested_valid_until)
        a.submitted_at = at
        a.submitted_by_user_id = p.user.id
    elif frm == PS.submitted and to == PS.draft:
        need(C.pass_application_endorse)
        details["comment"] = reason(5)
    elif frm == PS.submitted and to == PS.endorsed:
        need(C.pass_application_endorse)
        sponsor_id = body.client_sponsor_user_id or p.user.id
        sponsor = db.get(User, sponsor_id)
        if (
            a.submitted_by_user_id in (p.user.id, sponsor_id)
            or sponsor is None
            or sponsor.employer_type not in (EmployerType.client, EmployerType.pmc_consultant)
        ):
            raise ApiError(
                422,
                ErrorCode.ENDORSER_NOT_ALLOWED,
                "The endorser must be client or PMC staff and not the submitter (AP-8).",
                "يجب أن يكون المعتمد من العميل أو الاستشاري وليس مقدم الطلب.",
            )
        items = prerequisites(db, w, d, a, at)
        failing = [i for i in items if i.status.value in ("not_met", "not_evaluated")]
        if failing:
            raise ApiError(
                422,
                ErrorCode.PREREQUISITES_NOT_MET,
                "Prerequisites are not met (AP-7).",
                "المتطلبات المسبقة غير مستوفاة.",
                meta={
                    "requirements": [
                        i.to_schema().model_dump(mode="json", exclude_none=True) for i in failing
                    ]
                },
            )
        a.prerequisite_snapshot = [i.to_schema().model_dump(mode="json") for i in items]
        a.client_sponsor_user_id = sponsor_id
    elif frm == PS.endorsed and to == PS.lodged:
        need(C.pass_application_process)
        if not body.authority_ref:
            raise validation_error("authority_ref", "The authority reference is required.")
        lodged = body.lodged_at or at
        if lodged > at:
            raise validation_error("lodged_at", "lodged_at cannot be in the future.")
        a.lodged_at = lodged
        a.authority_ref = body.authority_ref
    elif frm == PS.lodged and to == PS.approved:
        need(C.pass_application_process)
        cat = _category(db, a.project_id, a.pass_category)
        bg = lifecycle.background(a).get("status")
        if (
            cat is not None
            and cat.background_check_required
            and bg != BackgroundCheckStatus.cleared.value
        ):
            raise ApiError(
                422,
                ErrorCode.BACKGROUND_NOT_CLEARED,
                "This category needs a cleared background check before approval (AP-4).",
                "تتطلب هذه الفئة اجتياز التحقق الأمني قبل الموافقة.",
            )
        if (
            cat is not None
            and not cat.background_check_required
            and bg
            not in (
                None,
                BackgroundCheckStatus.not_required.value,
                BackgroundCheckStatus.in_progress.value,
                BackgroundCheckStatus.submitted.value,
                BackgroundCheckStatus.cleared.value,
            )
        ):
            raise ApiError(
                422,
                ErrorCode.BACKGROUND_NOT_CLEARED,
                "The background check status does not allow approval.",
                "حالة التحقق الأمني لا تسمح بالموافقة.",
            )
        a.decided_at = at
    elif frm == PS.lodged and to == PS.refused:
        need(C.pass_application_process)
        a.decided_at = at
        a.closed_at = at
        a.outcome_note = body.outcome_note
    elif frm in (PS.draft, PS.submitted, PS.endorsed, PS.lodged) and to == PS.withdrawn:
        own = p.user.id in (a.created_by_user_id, a.submitted_by_user_id)
        g = p.grant(a.project_id, C.pass_application_endorse)
        if g is None:
            need(C.pass_application_create)
            if not own and not p.grant(a.project_id, C.pass_application_create):
                raise forbidden_error()
        details["reason"] = reason()
        a.closed_at = at
    elif frm == PS.approved and to == PS.cancelled:
        need(C.pass_application_process)
        details["reason"] = reason()
        a.closed_at = at
    elif to == PS.issued:
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "Use POST /pass-applications/{id}/issue to record the issued pass.",
            "استخدم إجراء الإصدار لتسجيل التصريح.",
        )
    else:
        raise invalid_transition("Application", frm, to)
    a.status = to
    a.updated_by_user_id = p.user.id
    a.updated_at = at
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.pass_application,
        entity_id=a.id,
        project_id=a.project_id,
        before=before,
        after={"status": to.value},
        details=details or None,
    )
    en, ar = STATUS_LABEL[to]
    _notify_update(db, a, en, ar)
    return application_read(db, p, a)


def put_background(
    db: Session, p: Principal, app_id: uuid.UUID, body: BackgroundCheckUpdate
) -> PassApplicationRead:
    a, d = get_application(db, p, app_id)
    common.require_cap(p, a.project_id, C.background_check_view, d.site_ids, d.engagement_id)
    common.require_cap(p, a.project_id, C.pass_application_process, d.site_ids, d.engagement_id)
    if (
        a.status in (PS.withdrawn, PS.cancelled, PS.refused)
        and body.status != BackgroundCheckStatus.not_cleared
    ):
        raise invalid_transition("Application", a.status, "updated")
    data: dict[str, Any] = {"status": body.status.value}
    if body.status == BackgroundCheckStatus.cleared:
        if body.check_date is None:
            raise validation_error("check_date", "The check date is required for cleared.")
        if body.check_date > today():
            raise validation_error("check_date", "The check date cannot be in the future.")
        s = common.settings(db, a.project_id)
        data["check_date"] = body.check_date.isoformat()
        data["recheck_due"] = add_months(body.check_date, s.bg_recheck_months).isoformat()
    elif body.check_date is not None:
        data["check_date"] = body.check_date.isoformat()
    lifecycle.set_background(a, data)
    a.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(a.project_id),
        entity_type=EntityType.pass_application,
        entity_id=a.id,
        project_id=a.project_id,
        details={"background_check": "updated"},
    )
    if a.issued_pass_id:
        ps = db.get(AirportPass, a.issued_pass_id)
        if ps is not None:
            lifecycle.evaluate_pass(db, ps)
    return application_read(db, p, a)


def issue(db: Session, p: Principal, app_id: uuid.UUID, body: PassIssueRequest) -> AirportPassRead:
    """AP-9, AP-11."""
    a, d = get_application(db, p, app_id)
    common.require_cap(p, a.project_id, C.pass_application_process, d.site_ids, d.engagement_id)
    if a.status != PS.approved:
        raise invalid_transition("Application", a.status, PS.issued)
    codes = list(dict.fromkeys(c.strip().upper() for c in body.area_codes))
    extra = [c for c in codes if c not in (a.requested_area_codes or [])]
    if extra:
        raise ApiError(
            422,
            ErrorCode.AREA_NOT_REQUESTED,
            f"Areas {', '.join(extra)} were not requested (AP-9).",
            "مناطق غير مطلوبة في الطلب.",
        )
    if body.card_expiry_date < body.issued_on:  # a 1-day visitor pass expires on its issue day
        raise validation_error(
            "card_expiry_date", "The card expiry cannot be before the issue date."
        )
    if body.issued_on > today():
        raise validation_error("issued_on", "issued_on cannot be in the future.")
    if db.scalar(
        select(AirportPass.id).where(
            AirportPass.project_id == a.project_id, AirportPass.pass_no == body.pass_no
        )
    ):
        raise duplicate("pass_no", "This pass number already exists on the project.")
    cat = _category(db, a.project_id, a.pass_category)
    assert cat is not None  # noqa: S101
    s = common.settings(db, a.project_id)
    prev = list(
        db.scalars(
            select(AirportPass).where(
                AirportPass.worker_id == a.worker_id,
                AirportPass.project_id == a.project_id,
                AirportPass.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
            )
        )
    )
    ps = AirportPass(
        id=uuid.uuid4(),
        pass_no=body.pass_no,
        project_id=a.project_id,
        application_id=a.id,
        worker_id=a.worker_id,
        deployment_id=a.deployment_id,
        engagement_id=d.engagement_id,
        pass_category=cat.code,
        area_codes=codes,
        card_colour=cat.card_colour,
        escorted=cat.escorted,
        issued_on=body.issued_on,
        card_expiry_date=body.card_expiry_date,
        validity_status=ValidityStatus.active,
        custody_status=CustodyStatus.held,
        created_by_user_id=p.user.id,
    )
    db.add(ps)
    db.flush()
    at = common.local_midnight_utc(body.issued_on)
    for old in prev:
        lifecycle.revoke(
            db, old, CredentialReason.superseded, f"Replaced by {ps.pass_no}", p.user.id, s, at
        )
        old.return_due_on = body.issued_on + timedelta(days=s.pass_return_days)
        for adp in db.scalars(select(Adp).where(Adp.pass_id == old.id)):
            if not cat.escorted and cat.allows_adp:
                adp.pass_id = ps.id
    lifecycle.evaluate_pass(db, ps)
    a.status = PS.issued
    a.issued_pass_id = ps.id
    a.closed_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(a.project_id),
        entity_type=EntityType.airport_pass,
        entity_id=ps.id,
        project_id=a.project_id,
        after={
            "pass_no": ps.pass_no,
            "application_no": a.application_no,
            "area_codes": codes,
            "card_expiry_date": ps.card_expiry_date.isoformat(),
            "superseded": [o.pass_no for o in prev],
        },
    )
    _notify_update(db, a, "Pass issued", "تم إصدار التصريح")
    return pass_read(db, p, ps)


# ---- passes --------------------------------------------------------------------------------------


def pass_read(
    db: Session, p: Principal | None, ps: AirportPass, refs: Refs | None = None
) -> AirportPassRead:
    refs = refs or Refs(db)
    w = db.get(Worker, ps.worker_id)
    assert w is not None  # noqa: S101
    extra: dict[str, Any] = {}
    if _can_bg(p, ps.project_id) and not ps.escorted:
        bg = lifecycle.background(db.get(PassApplication, ps.application_id))
        if bg.get("recheck_due"):
            extra["background_recheck_due"] = date.fromisoformat(bg["recheck_due"])
    return AirportPassRead(
        id=ps.id,
        pass_no=ps.pass_no,
        project_id=ps.project_id,
        application_id=ps.application_id,
        worker=common.worker_ref(w, common.can_see_names(p, ps.project_id)),
        deployment_id=ps.deployment_id,
        engagement=refs.eng(ps.engagement_id),
        pass_category=ps.pass_category,
        area_codes=list(ps.area_codes or []),
        card_colour=ps.card_colour,
        escorted=ps.escorted,
        issued_on=ps.issued_on,
        card_expiry_date=ps.card_expiry_date,
        validity=credentials.validity_block(db, ps, refs),
        created_at=ps.created_at,
        updated_at=ps.updated_at,
        **extra,
    )


def get_pass(db: Session, p: Principal, pass_id: uuid.UUID) -> AirportPassRead:
    ps = db.get(AirportPass, pass_id)
    if ps is None:
        raise not_found("Airport pass")
    projects.get_visible(db, p, ps.project_id)
    d = db.get(Deployment, ps.deployment_id)
    assert d is not None  # noqa: S101
    if workers.dep_covered(p, d, C.worker_view) is None:
        raise forbidden_error("This pass is outside your scope.")
    return pass_read(db, p, ps)


def list_passes(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    validity_statuses: list[ValidityStatus] | None,
    custody_statuses: list[CustodyStatus] | None,
    return_overdue: bool | None,
    categories: list[str] | None,
    area_codes: list[str] | None,
    worker_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    expiring_within_days: int | None,
    q: str | None,
) -> AirportPassPage:
    project = _airport(db, p, project_id)
    if p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(AirportPass)
        .join(Deployment, Deployment.id == AirportPass.deployment_id)
        .join(Worker, Worker.id == AirportPass.worker_id)
        .where(AirportPass.project_id == project.id, workers.dep_clause(p, C.worker_view))
    )
    conds: list[ColumnElement[bool]] = []
    day = today()
    if validity_statuses:
        conds.append(AirportPass.validity_status.in_(validity_statuses))
    if custody_statuses:
        conds.append(AirportPass.custody_status.in_(custody_statuses))
    if return_overdue is not None:
        cond = (AirportPass.custody_status == CustodyStatus.return_due) & (
            AirportPass.return_due_on < day
        )
        conds.append(cond if return_overdue else ~cond)
    if categories:
        conds.append(AirportPass.pass_category.in_(categories))
    if area_codes:
        conds.append(AirportPass.area_codes.overlap(area_codes))
    if worker_id:
        conds.append(AirportPass.worker_id == worker_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        conds.append(AirportPass.engagement_id.in_(ids))
    if expiring_within_days is not None:
        conds += [
            AirportPass.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
            AirportPass.effective_valid_until <= day + timedelta(days=expiring_within_days),
        ]
    if q:
        pat = like_pattern(q)
        conds.append(AirportPass.pass_no.ilike(pat) | Worker.search_text.ilike(pat))
    stmt = stmt.where(*conds).order_by(AirportPass.issued_on.desc(), AirportPass.pass_no)
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(engs=[r.engagement_id for r in rows])
    return AirportPassPage(
        items=[pass_read(db, p, r, refs) for r in rows], total=total, page=page, page_size=page_size
    )


# ---- jobs ---------------------------------------------------------------------------------------


def delete_id_copies(db: Session, day: date | None = None) -> int:
    """P2-5: ID copies deleted id_copy_retention_days after Issued/Refused/Withdrawn/Cancelled;
    the deletion is audited."""
    day = day or today()
    n = 0
    for a in db.scalars(
        select(PassApplication).where(
            PassApplication.status.in_([PS.issued, PS.refused, PS.withdrawn, PS.cancelled]),
            PassApplication.closed_at.is_not(None),
            PassApplication.id_copy_deleted_at.is_(None),
        )
    ):
        s = common.settings(db, a.project_id)
        assert a.closed_at is not None  # noqa: S101
        if (day - common.local_day(a.closed_at)).days < s.id_copy_retention_days:
            continue
        files = list(
            db.scalars(
                select(Attachment).where(
                    Attachment.owner_type == AttachmentOwner.pass_application_id_copy,
                    Attachment.owner_id == a.id,
                )
            )
        )
        if not files:
            continue
        for f in files:
            attachments.erase(db, f)
        a.id_copy_deleted_at = now()
        audit.record(
            db,
            AuditAction.archive,
            entity_type=EntityType.pass_application,
            entity_id=a.id,
            project_id=a.project_id,
            details={"id_copy_deleted": len(files), "retention_days": s.id_copy_retention_days},
        )
        n += 1
    db.flush()
    return n
