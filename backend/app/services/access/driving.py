"""Airside driving permits and offences (spec 2-access-permits §3.10, §3.11, §5.5 DP-1…DP-11,
§6.5 points)."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    AreaCategory,
    CredentialReason,
    CustodyStatus,
    DeploymentStatus,
    LicenceClass,
    LicenceIssuer,
    OffenceStatus,
    PassAreaKind,
    PracticalTestResult,
    SuspensionState,
    ValidityStatus,
    VehicleClass,
    WorkerIdType,
)
from app.core.clock import now, today
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    NotificationKind,
    Role,
    ZoneType,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner, ReferenceList
from app.core.text import like_pattern
from app.data.reference import OFF_POINTS
from app.kpi.periods import add_months
from app.models import (
    Adp,
    AirportPass,
    CredentialSuspension,
    Deployment,
    Offence,
    PassArea,
    PassCategory,
    ReferenceItem,
    Vehicle,
    Worker,
    Zone,
)
from app.schemas.airside_driving import (
    AdpCreate,
    AdpIssueRequest,
    AdpPage,
    AdpPoints,
    AdpRead,
    AdpUpdate,
    OffenceCreate,
    OffencePage,
    OffenceRead,
    OffenceTransitionRequest,
)
from app.services import attachments, audit, hse_settings, notify, projects
from app.services.access import common, credentials, lifecycle, workers
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
LIVE = (ValidityStatus.active, ValidityStatus.suspended)
COUNTING = (OffenceStatus.recorded, OffenceStatus.disputed, OffenceStatus.upheld)
TEST_WINDOW_DAYS = 90
DP_KINDS: dict[AreaCategory, set[PassAreaKind]] = {
    AreaCategory.manoeuvring: {PassAreaKind.manoeuvring, PassAreaKind.apron},
    AreaCategory.apron: {PassAreaKind.apron},
    AreaCategory.airside_roads: {PassAreaKind.airside_roads},
}
DP_ANY_ROAD = {PassAreaKind.airside_roads, PassAreaKind.apron, PassAreaKind.manoeuvring}
CLASS_OK: dict[VehicleClass, set[LicenceClass]] = {
    VehicleClass.light: {
        LicenceClass.private,
        LicenceClass.public_transport,
        LicenceClass.heavy_transport,
        LicenceClass.heavy_equipment,
    },
    VehicleClass.heavy: {LicenceClass.heavy_transport, LicenceClass.heavy_equipment},
    VehicleClass.special_plant: {LicenceClass.heavy_equipment},
}


def _airport(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    project = projects.get_visible(db, p, project_id)
    common.require_airport(project)
    return project


# ---- points (§6.5) -------------------------------------------------------------------------------


def points_12m(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, as_of: date, window_days: int
) -> tuple[int, list[uuid.UUID]]:
    """Σ points of offences recorded/disputed/upheld with offence_date in (as_of − window,
    as_of] (DP-10: disputed keep counting until withdrawn)."""
    start = as_of - timedelta(days=window_days)
    rows = db.execute(
        select(Offence.id, Offence.points).where(
            Offence.worker_id == worker_id,
            Offence.project_id == project_id,
            Offence.status.in_(COUNTING),
            Offence.offence_date > start,
            Offence.offence_date <= as_of,
        )
    ).all()
    return sum(int(r[1]) for r in rows), [r[0] for r in rows]


def _suspensions_in_window(db: Session, a: Adp, as_of: date, days: int) -> int:
    start = common.local_midnight_utc(as_of - timedelta(days=days - 1))
    return int(
        db.scalar(
            select(func.count())
            .select_from(CredentialSuspension)
            .where(
                CredentialSuspension.credential_id == a.id,
                CredentialSuspension.reason_code.in_(
                    [CredentialReason.points_threshold, CredentialReason.violation]
                ),
                CredentialSuspension.raised_at >= start,
            )
        )
        or 0
    )


# ---- reads ---------------------------------------------------------------------------------------


def _pct(v: Decimal | None) -> str | None:
    return None if v is None else f"{v:.2f}"


def adp_read(
    db: Session, p: Principal | None, a: Adp, refs: Refs | None = None, as_of: date | None = None
) -> AdpRead:
    refs = refs or Refs(db)
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    s = common.settings(db, a.project_id)
    day = as_of or today()
    pts, ids = points_12m(db, a.worker_id, a.project_id, day, s.adp_points_window_days)
    return AdpRead(
        id=a.id,
        adp_no=a.adp_no,
        project_id=a.project_id,
        worker=common.worker_ref(w, common.can_see_names(p, a.project_id)),
        deployment_id=a.deployment_id,
        engagement=refs.eng(a.engagement_id),
        category=a.category,
        vehicle_classes=[VehicleClass(c) for c in a.vehicle_classes or []],
        licence_issuer=a.licence_issuer,
        licence_class=a.licence_class,
        licence_expiry_date=a.licence_expiry_date,
        theory_test_date=a.theory_test_date,
        theory_score_pct=_pct(a.theory_score_pct),
        practical_test_date=a.practical_test_date,
        practical_result=a.practical_result,
        practical_examiner=a.practical_examiner,
        practical_included_manoeuvring=a.practical_included_manoeuvring,
        rtf_competence=a.rtf_competence,
        issued_on=a.issued_on,
        own_valid_until=a.own_valid_until,
        pass_id=a.pass_id,
        points=AdpPoints(
            as_of=day,
            points_12m=pts,
            threshold=s.adp_points_threshold,
            window_start_exclusive=day - timedelta(days=s.adp_points_window_days),
            offence_ids=ids,
        ),
        suspension_count_window=_suspensions_in_window(
            db, a, day, s.adp_revoke_after_suspensions_window_days
        ),
        validity=credentials.validity_block(db, a, refs),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def get_adp_row(db: Session, p: Principal, adp_id: uuid.UUID) -> tuple[Adp, Deployment]:
    a = db.get(Adp, adp_id)
    if a is None:
        raise not_found("ADP")
    projects.get_visible(db, p, a.project_id)
    d = db.get(Deployment, a.deployment_id)
    assert d is not None  # noqa: S101
    if workers.dep_covered(p, d, C.worker_view) is None:
        raise forbidden_error("This ADP is outside your scope.")
    return a, d


def read_adp(db: Session, p: Principal, adp_id: uuid.UUID, as_of: date | None) -> AdpRead:
    a, _ = get_adp_row(db, p, adp_id)
    return adp_read(db, p, a, as_of=as_of)


def list_adps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    validity_statuses: list[ValidityStatus] | None,
    category: AreaCategory | None,
    worker_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    expiring_within_days: int | None,
    q: str | None,
) -> AdpPage:
    project = _airport(db, p, project_id)
    if p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(Adp)
        .join(Deployment, Deployment.id == Adp.deployment_id)
        .join(Worker, Worker.id == Adp.worker_id)
        .where(Adp.project_id == project.id, workers.dep_clause(p, C.worker_view))
    )
    conds: list[ColumnElement[bool]] = []
    if validity_statuses:
        conds.append(Adp.validity_status.in_(validity_statuses))
    if category:
        conds.append(Adp.category == category)
    if worker_id:
        conds.append(Adp.worker_id == worker_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        conds.append(Adp.engagement_id.in_(ids))
    if expiring_within_days is not None:
        conds += [
            Adp.validity_status.in_(LIVE),
            Adp.effective_valid_until <= today() + timedelta(days=expiring_within_days),
        ]
    if q:
        pat = like_pattern(q)
        conds.append(Adp.adp_no.ilike(pat) | Worker.search_text.ilike(pat))
    stmt = stmt.where(*conds).order_by(Adp.created_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(engs=[r.engagement_id for r in rows])
    return AdpPage(
        items=[adp_read(db, p, r, refs) for r in rows], total=total, page=page, page_size=page_size
    )


# ---- writes --------------------------------------------------------------------------------------


def _blocked_contractor(db: Session, engagement_id: uuid.UUID | None) -> None:
    c = common.engagement_contractor(db, engagement_id)
    if c is not None and c.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        raise ApiError(
            403,
            ErrorCode.CONTRACTOR_SUSPENDED,
            "The contractor is suspended: new applications are blocked (LC-7).",
            "المقاول موقوف: الطلبات الجديدة محظورة.",
        )


def _snapshot(a: Adp) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(a, k)
            for k in (
                "adp_no", "category", "vehicle_classes", "licence_issuer", "licence_class",
                "licence_expiry_date", "theory_test_date", "theory_score_pct",
                "practical_test_date", "practical_result", "practical_examiner",
                "practical_included_manoeuvring", "rtf_competence", "issued_on",
                "own_valid_until", "validity_status",
            )
        }
    )  # fmt: skip


def create_adp(db: Session, p: Principal, project_id: uuid.UUID, body: AdpCreate) -> AdpRead:
    project = _airport(db, p, project_id)
    d = db.get(Deployment, body.deployment_id)
    if d is None or d.project_id != project.id:
        raise validation_error("deployment_id", "Unknown deployment on this project.")
    common.require_cap(p, project.id, C.adp_apply, d.site_ids, d.engagement_id)
    if d.status != DeploymentStatus.mobilised:
        raise validation_error("deployment_id", "The worker must be mobilised.")
    _blocked_contractor(db, d.engagement_id)
    existing = db.scalar(
        select(Adp).where(
            Adp.worker_id == d.worker_id,
            Adp.project_id == project.id,
            Adp.validity_status.in_([*LIVE, ValidityStatus.pending]),
        )
    )
    if existing is not None:
        raise ApiError(
            409,
            ErrorCode.ADP_EXISTS,
            "The worker already has an ADP or application on this project (DP-2).",
            "لدى العامل تصريح قيادة أو طلب قائم في هذا المشروع.",
            meta={"id": str(existing.id)},
        )
    a = Adp(
        id=uuid.uuid4(),
        project_id=project.id,
        worker_id=d.worker_id,
        deployment_id=d.id,
        engagement_id=d.engagement_id,
        category=body.category,
        vehicle_classes=[c.value for c in body.vehicle_classes],
        licence_issuer=body.licence_issuer,
        licence_class=body.licence_class,
        licence_expiry_date=body.licence_expiry_date,
        validity_status=ValidityStatus.pending,
        created_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.adp,
        entity_id=a.id,
        project_id=project.id,
        after=_snapshot(a),
    )
    return adp_read(db, p, a)


TEST_FIELDS = {
    "theory_test_date",
    "theory_score_pct",
    "practical_test_date",
    "practical_result",
    "practical_examiner",
    "practical_included_manoeuvring",
    "rtf_competence",
}


def update_adp(db: Session, p: Principal, adp_id: uuid.UUID, body: AdpUpdate) -> AdpRead:
    a, d = get_adp_row(db, p, adp_id)
    ch = body.changes()
    if set(ch) & TEST_FIELDS:
        common.require_cap(p, a.project_id, C.adp_issue, d.site_ids, d.engagement_id)
    if set(ch) - TEST_FIELDS:
        common.require_cap(p, a.project_id, C.adp_apply, d.site_ids, d.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        if set(ch) == {"licence_expiry_date"} and a.validity_status in LIVE:
            pass  # a renewed licence may be recorded on an issued ADP (DP-7 auto-reinstate)
        else:
            raise invalid_transition("ADP", a.validity_status, "edited")
    before = _snapshot(a)
    if ch.get("vehicle_classes") is not None:
        ch["vehicle_classes"] = [getattr(c, "value", c) for c in ch["vehicle_classes"]]
    if ch.get("theory_score_pct") is not None:
        ch["theory_score_pct"] = Decimal(ch["theory_score_pct"])
        if ch["theory_score_pct"] > 100:
            raise validation_error("theory_score_pct", "0-100.")
    for k, v in ch.items():
        setattr(a, k, v)
    a.updated_by_user_id = p.user.id
    a.updated_at = now()
    if a.validity_status in LIVE:
        lifecycle.evaluate_adp(db, a)
    db.flush()
    bf, af = audit.diff(before, _snapshot(a))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.adp,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
    return adp_read(db, p, a)


def _qualifying_pass(db: Session, a: Adp, day: date) -> AirportPass | None:
    """DP-3: Active unescorted pass (category allows ADP) with areas of each covered kind."""
    need = DP_KINDS[a.category]
    kinds = {
        ar.code: ar.area_kind
        for ar in db.scalars(select(PassArea).where(PassArea.project_id == a.project_id))
    }
    cats = {
        c.code: c
        for c in db.scalars(select(PassCategory).where(PassCategory.project_id == a.project_id))
    }
    for ps in db.scalars(
        select(AirportPass).where(
            AirportPass.worker_id == a.worker_id,
            AirportPass.project_id == a.project_id,
            AirportPass.validity_status == ValidityStatus.active,
        )
    ):
        cat = cats.get(ps.pass_category)
        if ps.escorted or cat is None or not cat.allows_adp:
            continue
        if not lifecycle.live_valid(ps, day):
            continue
        have = {kinds.get(c) for c in ps.area_codes or []}
        if a.category == AreaCategory.airside_roads:
            if have & DP_ANY_ROAD:
                return ps
        elif need <= have:
            return ps
    return None


def issue_adp(db: Session, p: Principal, adp_id: uuid.UUID, body: AdpIssueRequest) -> AdpRead:
    a, d = get_adp_row(db, p, adp_id)
    common.require_cap(p, a.project_id, C.adp_issue, d.site_ids, d.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        raise invalid_transition("ADP", a.validity_status, ValidityStatus.active)
    s = common.settings(db, a.project_id)
    day = today()
    if body.issued_on > day:
        raise validation_error("issued_on", "issued_on cannot be in the future.")
    ps = _qualifying_pass(db, a, day)
    if ps is None:
        raise ApiError(
            422,
            ErrorCode.ADP_PASS_REQUIRED,
            "An Active unescorted airport pass covering the ADP category's areas is required "
            "(DP-3).",
            "يلزم تصريح مطار ساري بدون مرافقة يغطي مناطق فئة التصريح.",
        )
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    resident = w.id_type in (WorkerIdType.iqama, WorkerIdType.national_id)
    bad_classes = [
        c for c in a.vehicle_classes or [] if a.licence_class not in CLASS_OK[VehicleClass(c)]
    ]
    if (
        (resident and a.licence_issuer != LicenceIssuer.ksa)
        or a.licence_expiry_date <= day
        or bad_classes
    ):
        raise ApiError(
            422,
            ErrorCode.LICENCE_NOT_VALID,
            "The driving licence does not qualify (KSA licence for residents, not expired, "
            "classes allowed by the licence class) (DP-4).",
            "رخصة القيادة غير مؤهلة.",
            meta={"vehicle_classes_not_allowed": bad_classes},
        )
    if a.category == AreaCategory.manoeuvring and not (
        a.rtf_competence and a.practical_included_manoeuvring
    ):
        raise ApiError(
            422,
            ErrorCode.RTF_REQUIRED,
            "Manoeuvring ADPs need radiotelephony competence and a practical test in the "
            "manoeuvring area (DP-5).",
            "تصريح منطقة المناورة يتطلب كفاءة الاتصال اللاسلكي واختباراً عملياً فيها.",
        )
    lo = body.issued_on - timedelta(days=TEST_WINDOW_DAYS)
    theory_ok = (
        a.theory_test_date is not None
        and lo <= a.theory_test_date <= body.issued_on
        and a.theory_score_pct is not None
        and a.theory_score_pct >= s.adp_theory_pass_pct
    )
    practical_ok = (
        a.practical_test_date is not None
        and lo <= a.practical_test_date <= body.issued_on
        and a.practical_result == PracticalTestResult.passed
    )
    if not (theory_ok and practical_ok):
        raise ApiError(
            422,
            ErrorCode.TESTS_NOT_VALID,
            f"Theory ≥ {s.adp_theory_pass_pct} % and a passed practical test, both within "
            f"{TEST_WINDOW_DAYS} days before issue, are required (DP-6).",
            "يلزم اجتياز الاختبار النظري والعملي خلال 90 يوماً قبل الإصدار.",
        )
    limit = add_months(body.issued_on, s.adp_validity_months)
    if body.own_valid_until > limit or body.own_valid_until <= body.issued_on:
        raise validation_error("own_valid_until", f"Must be after issue and ≤ {limit.isoformat()}.")
    if db.scalar(select(Adp.id).where(Adp.project_id == a.project_id, Adp.adp_no == body.adp_no)):
        raise duplicate("adp_no", "This ADP number already exists on the project.")
    before = _snapshot(a)
    a.adp_no = body.adp_no
    a.issued_on = body.issued_on
    a.own_valid_until = body.own_valid_until
    a.pass_id = ps.id
    a.validity_status = ValidityStatus.active
    a.custody_status = CustodyStatus.held
    a.updated_by_user_id = p.user.id
    a.updated_at = now()
    lifecycle.evaluate_adp(db, a)
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.adp,
        entity_id=a.id,
        project_id=a.project_id,
        before=before,
        after=_snapshot(a),
    )
    return adp_read(db, p, a)


def withdraw_adp(db: Session, p: Principal, adp_id: uuid.UUID) -> AdpRead:
    a, d = get_adp_row(db, p, adp_id)
    common.require_cap(p, a.project_id, C.adp_apply, d.site_ids, d.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        raise invalid_transition("ADP", a.validity_status, ValidityStatus.withdrawn)
    a.validity_status = ValidityStatus.withdrawn
    a.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.adp,
        entity_id=a.id,
        project_id=a.project_id,
        before={"validity_status": "pending"},
        after={"validity_status": "withdrawn"},
    )
    return adp_read(db, p, a)


# ---- offences ------------------------------------------------------------------------------------


def offence_def(db: Session, code: str) -> tuple[int, bool, str, str] | None:
    r = db.get(ReferenceItem, (ReferenceList.airside_offence.value, code))
    if r is None:
        if code not in OFF_POINTS:
            return None
        labels = hse_settings.labels(db, ReferenceList.airside_offence)
        en, ar = labels.get(code, (code, code))
        pts, imm = OFF_POINTS[code]
        return pts, imm, en, ar
    pts = r.points if r.points is not None else OFF_POINTS.get(code, (0, False))[0]
    return pts, bool(r.immediate_suspension), r.label_en, r.label_ar


def offence_read(
    db: Session, p: Principal | None, o: Offence, refs: Refs | None = None
) -> OffenceRead:
    refs = refs or Refs(db)
    w = db.get(Worker, o.worker_id)
    assert w is not None  # noqa: S101
    a = db.get(Adp, o.adp_id) if o.adp_id else None
    v = db.get(Vehicle, o.vehicle_id) if o.vehicle_id else None
    d = offence_def(db, o.offence_code)
    zr = refs.zone(o.zone_id)
    assert zr is not None  # noqa: S101
    return OffenceRead(
        id=o.id,
        offence_no=o.offence_no,
        project_id=o.project_id,
        worker=common.worker_ref(w, common.can_see_names(p, o.project_id)),
        adp_id=o.adp_id,
        adp_no=a.adp_no if a else None,
        offence_code=o.offence_code,
        offence_label_en=d[2] if d else o.offence_code,
        offence_label_ar=d[3] if d else o.offence_code,
        offence_at=o.offence_at,
        zone=zr,
        vehicle=common.vehicle_ref(v) if v else None,
        points=o.points,
        immediate_suspension=o.immediate_suspension,
        reported_by=refs.user(o.reported_by_user_id) or attachments.UNKNOWN,
        incident_id=o.incident_id,
        notes=o.notes,
        status=o.status,
        evidence_count=attachments.count_for(db, AttachmentOwner.offence_evidence, o.id),
        resulting_actions=list(o.resulting_actions or []),
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def get_offence_row(db: Session, p: Principal, offence_id: uuid.UUID) -> Offence:
    o = db.get(Offence, offence_id)
    if o is None:
        raise not_found("Offence")
    projects.get_visible(db, p, o.project_id)
    g = p.grant(o.project_id, C.worker_view)
    if not common.grant_covers(g, None, o.engagement_id):
        raise forbidden_error("This offence is outside your scope.")
    return o


def read_offence(db: Session, p: Principal, offence_id: uuid.UUID) -> OffenceRead:
    return offence_read(db, p, get_offence_row(db, p, offence_id))


def list_offences(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[OffenceStatus] | None,
    codes: list[str] | None,
    worker_id: uuid.UUID | None,
    zone_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    date_from: date | None,
    date_to: date | None,
) -> OffencePage:
    project = _airport(db, p, project_id)
    g = p.grant(project.id, C.worker_view)
    if g is None:
        raise forbidden_error()
    stmt = select(Offence).where(Offence.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(Offence.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(Offence.status.in_(statuses))
    if codes:
        stmt = stmt.where(Offence.offence_code.in_(codes))
    if worker_id:
        stmt = stmt.where(Offence.worker_id == worker_id)
    if zone_id:
        stmt = stmt.where(Offence.zone_id == zone_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(Offence.engagement_id.in_(ids))
    if date_from:
        stmt = stmt.where(Offence.offence_date >= date_from)
    if date_to:
        stmt = stmt.where(Offence.offence_date <= date_to)
    stmt = stmt.order_by(Offence.offence_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(
        zones=[o.zone_id for o in rows], users=[o.reported_by_user_id for o in rows]
    )
    return OffencePage(
        items=[offence_read(db, p, o, refs) for o in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _adp_alert(db: Session, a: Adp, what_en: str, what_ar: str) -> None:
    users: set[uuid.UUID] = set(notify.managers(db))
    users.update(notify.users_with_role(db, Role.hse_officer, [a.project_id]))
    users.update(contractor_reps(db, a.project_id, a.engagement_id))
    notify.notify(
        db,
        users,
        NotificationKind.adp_suspended,
        f"{a.adp_no}: {what_en}",
        f"{a.adp_no}: {what_ar}",
        None,
        None,
        EntityType.adp,
        a.id,
        a.project_id,
    )


def apply_offence(db: Session, o: Offence, at: datetime | None = None) -> list[str]:
    """DP-8 / DP-9 consequences of a new offence on the worker's ADP."""
    if o.adp_id is None:
        return []
    a = db.get(Adp, o.adp_id)
    if a is None or a.validity_status not in LIVE:
        return []
    s = common.settings(db, a.project_id)
    at = at or now()
    actions: list[str] = []
    suspended = False
    if o.immediate_suspension:
        lifecycle.suspend(
            db,
            a,
            SuspensionState.system,
            CredentialReason.violation,
            f"{o.offence_no} {o.offence_code}",
            None,
            at=at,
        )
        actions.append("adp_suspended_violation")
        suspended = True
        _adp_alert(db, a, "suspended (violation)", "تم الإيقاف (مخالفة)")
    else:
        pts, _ = points_12m(db, o.worker_id, o.project_id, o.offence_date, s.adp_points_window_days)
        already = any(
            x.reason_code == CredentialReason.points_threshold
            for x in lifecycle.open_suspensions(db, a)
        )
        if pts >= s.adp_points_threshold and not already:
            lifecycle.suspend(
                db,
                a,
                SuspensionState.system,
                CredentialReason.points_threshold,
                f"{pts} points in {s.adp_points_window_days} days",
                None,
                at=at,
                suspension_end=o.offence_date + timedelta(days=s.adp_suspension_days - 1),
            )
            actions.append("adp_suspended_points")
            suspended = True
            _adp_alert(db, a, "suspended (points threshold)", "تم الإيقاف (تجاوز حد النقاط)")
    if suspended:
        n = _suspensions_in_window(
            db, a, o.offence_date, s.adp_revoke_after_suspensions_window_days
        )
        if n >= s.adp_revoke_after_suspensions:
            lifecycle.revoke(
                db, a, CredentialReason.violation, f"{n} suspensions (DP-9)", None, s, at
            )
            actions.append("adp_revoked")
            _adp_alert(db, a, "revoked (repeated suspensions)", "تم السحب (إيقافات متكررة)")
    db.flush()
    return actions


def create_offence(
    db: Session, p: Principal, project_id: uuid.UUID, body: OffenceCreate
) -> OffenceRead:
    project = _airport(db, p, project_id)
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise validation_error("worker_id", "Unknown worker.")
    d = db.scalar(
        select(Deployment)
        .where(Deployment.worker_id == w.id, Deployment.project_id == project.id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    if d is None:
        raise validation_error("worker_id", "The worker has no deployment on this project.")
    zone = db.get(Zone, body.zone_id)
    if zone is None or zone.project_id != project.id or zone.zone_type != ZoneType.airside:
        raise validation_error("zone_id", "Choose an airside zone of the project.")
    g = common.require_cap(p, project.id, C.offence_record, [zone.site_id], None)
    if g.engagement_ids is not None and d.engagement_id not in g.engagement_ids:
        raise forbidden_error()
    if body.offence_at > now():
        raise validation_error("offence_at", "offence_at cannot be in the future.")
    if body.vehicle_id is not None:
        v = db.get(Vehicle, body.vehicle_id)
        if v is None or v.project_id != project.id:
            raise validation_error("vehicle_id", "Unknown vehicle.")
    od = offence_def(db, body.offence_code)
    if od is None:
        raise validation_error("offence_code", "Unknown offence code.")
    adp = db.scalar(
        select(Adp).where(
            Adp.worker_id == w.id, Adp.project_id == project.id, Adp.validity_status.in_(LIVE)
        )
    )
    year = body.offence_at.year
    seq = next_seq(db, Offence, project.id, year)
    o = Offence(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        offence_no=make_ref("OFF", project.code, year, seq, 4),
        project_id=project.id,
        worker_id=w.id,
        engagement_id=d.engagement_id,
        adp_id=adp.id if adp else None,
        offence_code=body.offence_code,
        points=od[0],
        immediate_suspension=od[1],
        offence_at=body.offence_at,
        offence_date=common.local_day(body.offence_at),
        zone_id=zone.id,
        vehicle_id=body.vehicle_id,
        reported_by_user_id=p.user.id,
        incident_id=body.incident_id,
        notes=body.notes,
        status=OffenceStatus.recorded,
        resulting_actions=[],
        created_by_user_id=p.user.id,
    )
    db.add(o)
    db.flush()
    o.resulting_actions = apply_offence(db, o)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.airside_offence,
        entity_id=o.id,
        project_id=project.id,
        after={
            "offence_no": o.offence_no,
            "worker_no": w.worker_no,
            "offence_code": o.offence_code,
            "points": o.points,
            "resulting_actions": o.resulting_actions,
        },
    )
    return offence_read(db, p, o)


OFFENCE_MOVES = {
    (OffenceStatus.recorded, OffenceStatus.disputed),
    (OffenceStatus.recorded, OffenceStatus.upheld),
    (OffenceStatus.disputed, OffenceStatus.upheld),
    (OffenceStatus.recorded, OffenceStatus.withdrawn),
    (OffenceStatus.disputed, OffenceStatus.withdrawn),
    (OffenceStatus.upheld, OffenceStatus.withdrawn),
}


def transition_offence(
    db: Session, p: Principal, offence_id: uuid.UUID, body: OffenceTransitionRequest
) -> OffenceRead:
    o = get_offence_row(db, p, offence_id)
    if (o.status, body.to_status) not in OFFENCE_MOVES:
        raise invalid_transition("Offence", o.status, body.to_status)
    cap = (
        C.offence_record
        if body.to_status == OffenceStatus.disputed
        else (C.credential_suspend_confirm)
    )
    common.require_cap(p, o.project_id, cap, None, o.engagement_id)
    before = o.status
    o.status = body.to_status
    o.updated_at = now()
    o.updated_by_user_id = p.user.id
    db.flush()
    if body.to_status == OffenceStatus.withdrawn:
        # DP-10: points recomputed on read; never auto-reinstates → tell the HSE Officers
        notify.notify(
            db,
            notify.users_with_role(db, Role.hse_officer, [o.project_id]),
            NotificationKind.adp_suspended,
            f"{o.offence_no} withdrawn: review any ADP suspension",
            f"تم إلغاء المخالفة {o.offence_no}: راجع إيقاف تصريح القيادة",
            None,
            None,
            EntityType.airside_offence,
            o.id,
            o.project_id,
        )
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.airside_offence,
        entity_id=o.id,
        project_id=o.project_id,
        before={"status": before.value},
        after={"status": o.status.value},
        details={"reason": body.reason},
    )
    return offence_read(db, p, o)
