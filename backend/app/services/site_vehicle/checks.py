"""7b.3 Daily pre-use checks (spec 7b-fleet-driver §3.3, PU-1…PU-6): a 6d checklist response
(owner type `vehicle_check`, templates VPU-L / VPU-H / VPU-B by driver group), findings, the
defect hold (PU-3, CA source `site_vehicle`) or a Phase 4 Defect (source `pre_use_check`) for
plant linked to a Phase 4 item, paper fallback (PU-5) and the driver authorisation flag (PU-6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, VehicleStatus
from app.core.cert_enums import DefectCategory, DefectSource
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import (
    FindingSeverity,
    ResponseOwnerType,
    ResponseResult,
)
from app.core.hse_enums import AttachmentOwner, CaSourceType, InspectionType
from app.core.site_vehicle_enums import (
    SiteVehCheckSource,
    SiteVehPolicy,
    SiteVehWarning,
)
from app.models import (
    ChecklistResponse,
    CorrectiveAction,
    Deployment,
    DriverAuthorisation,
    EquipmentDefect,
    FieldFinding,
    Project,
    Site,
    Vehicle,
    VehicleCheck,
    Worker,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.site_vehicle import (
    SiteVehCheckCreate,
    SiteVehCheckForm,
    SiteVehCheckPage,
    SiteVehCheckRead,
    SiteVehFindingRead,
    SiteVehMissingByContractor,
    SiteVehMissingRead,
    SiteVehMissingRow,
)
from app.services.field import common as fc
from app.services.field import execution, library, scoring
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.site_vehicle import common as c
from app.services.site_vehicle import vehicles as sv

C = Capability
D = Decimal


# ---- reading -------------------------------------------------------------------------------------


def check_read(
    db: Session,
    p: Principal | None,
    ch: VehicleCheck,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> SiteVehCheckRead:
    refs = refs or Refs(db)
    v = db.get(Vehicle, ch.vehicle_id)
    w = db.get(Worker, ch.driver_worker_id)
    assert v is not None and w is not None  # noqa: S101
    names = p is None or c.names_visible(p, ch.project_id)
    fs = (
        list(
            db.scalars(
                select(FieldFinding)
                .where(FieldFinding.response_id == ch.response_id)
                .order_by(FieldFinding.finding_no)
            )
        )
        if ch.response_id
        else []
    )
    findings = []
    for f in fs:
        ref, _ = fc.ca_info(db, f.ca_id)
        findings.append(
            SiteVehFindingRead(
                finding_no=f.finding_no,
                item_code=f.item_code,
                severity=f.severity,
                critical_item=f.critical_item,
                ca_id=f.ca_id,
                ca_ref=ref,
            )
        )
    dfx = db.get(EquipmentDefect, ch.phase4_defect_id) if ch.phase4_defect_id else None
    auth = db.get(DriverAuthorisation, ch.authorisation_id) if ch.authorisation_id else None
    return SiteVehCheckRead(
        id=ch.id,
        check_no=ch.check_no,
        project_id=ch.project_id,
        vehicle=sv.vehicle_ref(v),
        engagement=refs.eng(ch.engagement_id),
        driver=c.worker_ref(w, names),
        driver_group=ch.driver_group,
        driver_authorised=ch.driver_authorised,
        authorisation_no=auth.auth_no if auth else None,
        check_date=ch.check_date,
        template_code=ch.template_code,
        response_id=ch.response_id,
        passed=ch.passed,
        critical_fail_count=ch.critical_fail_count,
        failed_items=list(ch.failed_items or []),
        source=ch.source,
        paper_photo_id=ch.paper_photo_id,
        recorded_by=refs.user(ch.recorded_by_user_id) if names else None,
        completed_at=ch.completed_at,
        findings=findings,
        phase4_defect_id=ch.phase4_defect_id,
        phase4_defect_no=dfx.defect_no if dfx else None,
        hold_set=ch.hold_set,
        hold_cleared_at=ch.hold_cleared_at,
        hold_repair_note=ch.hold_repair_note,
        warnings=warnings if warnings is not None else [ApiWarning(**x) for x in ch.warnings or []],
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )


def _visible(db: Session, p: Principal, ch: VehicleCheck | Any) -> bool:
    g = c.view_grant(p, ch.project_id)
    return c.covers_any(db, g, [ch.engagement_id, ch.driver_engagement_id])


def get_check(db: Session, p: Principal, check_id: uuid.UUID) -> VehicleCheck:
    ch = db.get(VehicleCheck, check_id)
    if ch is None or not p.can_see_project(ch.project_id):
        raise not_found("Pre-use check")
    c.require_live(db, ch.project_id)
    if not _visible(db, p, ch):
        raise not_found("Pre-use check")
    return ch


def read_check(db: Session, p: Principal, check_id: uuid.UUID) -> SiteVehCheckRead:
    return check_read(db, p, get_check(db, p, check_id))


def list_checks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
    vehicle_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    passed: bool | None,
    source: SiteVehCheckSource | None,
    driver_authorised: bool | None,
    page: int,
    page_size: int,
) -> SiteVehCheckPage:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    c.view_grant(p, project_id)
    V = VehicleCheck  # noqa: N806
    stmt = select(V).where(V.project_id == project_id)
    if date_from:
        stmt = stmt.where(V.check_date >= date_from)
    if date_to:
        stmt = stmt.where(V.check_date <= date_to)
    if vehicle_id:
        stmt = stmt.where(V.vehicle_id == vehicle_id)
    if engagement_ids:
        stmt = stmt.where(V.engagement_id.in_(engagement_ids))
    if passed is not None:
        stmt = stmt.where(V.passed.is_(passed))
    if source:
        stmt = stmt.where(V.source == source)
    if driver_authorised is not None:
        stmt = stmt.where(V.driver_authorised.is_(driver_authorised))
    rows = [x for x in db.scalars(stmt.order_by(V.check_date.desc(), V.seq.desc()))
            if _visible(db, p, x)]  # fmt: skip
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    refs = Refs(db).load(
        engs=[x.engagement_id for x in rows], users=[x.recorded_by_user_id for x in rows]
    )
    return SiteVehCheckPage(
        items=[check_read(db, p, x, refs) for x in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def form(
    db: Session, p: Principal, project_id: uuid.UUID, vehicle_id: uuid.UUID
) -> SiteVehCheckForm:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    p.require(project_id, C.pre_use_record)
    v = sv.get_row(db, p, vehicle_id)
    if v.project_id != project_id:
        raise not_found("Site vehicle")
    t = _template(db, v, now())
    d = c.local_day()
    existing = db.scalar(
        select(VehicleCheck.check_no)
        .where(VehicleCheck.vehicle_id == v.id, VehicleCheck.check_date == d)
        .order_by(VehicleCheck.completed_at.desc())
        .limit(1)
    )
    r, _ = c.readiness(db, v, d)
    return SiteVehCheckForm(
        vehicle=sv.vehicle_ref(v),
        template=library.template_read(db, t),
        check_date=d,
        existing_check_no=existing,
        on_defect_hold=c.active_hold(db, v.id) is not None,
        readiness=r,
    )


def missing(
    db: Session, p: Principal, project_id: uuid.UUID, day: date | None
) -> SiteVehMissingRead:
    """PU-1 for a day: the required vehicles and those still without a Completed check."""
    c.project(db, p, project_id)
    cf = c.require_live(db, project_id)
    d = day or c.local_day()
    vs = sv.visible_vehicles(db, p, project_id)
    ctx = sv.Ctx.load(db, vs, d)
    req = [v for v in vs if sv.required_on(cf, v, d)]
    refs = Refs(db).load(engs=[v.engagement_id for v in req])
    per: dict[uuid.UUID, list[int]] = {}
    items = []
    for v in req:
        acc = per.setdefault(v.engagement_id, [0, 0])
        acc[0] += 1
        if v.id in ctx.today:
            acc[1] += 1
        else:
            items.append(
                SiteVehMissingRow(
                    vehicle=sv.vehicle_ref(v),
                    engagement=refs.eng(v.engagement_id),
                    readiness=ctx.readiness(v)[0],
                )
            )
    rows = sorted(per.items(), key=lambda kv: refs.engs[kv[0]].contractor.short_code)
    return SiteVehMissingRead(
        date=d,
        working_day=cf.working_day(d),
        required=len(req),
        completed=sum(x[1] for x in per.values()),
        items=items,
        by_contractor=[
            SiteVehMissingByContractor(
                engagement=refs.eng(e), required=n, completed=k, missing=n - k
            )
            for e, (n, k) in rows
        ],
    )


# ---- recording -----------------------------------------------------------------------------------


def _template(db: Session, v: Vehicle, at: datetime) -> Any:
    if v.driver_group is None:
        raise validation_error("vehicle_id", "The vehicle has no use class / driver group.")
    code = c.TEMPLATE_BY_GROUP[v.driver_group]
    t = library.published(db, code, at)
    if t is None:
        raise validation_error("vehicle_id", f"Template {code} is not published (6d).")
    return t


def site_for(db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None) -> uuid.UUID:
    sites = c.eng_sites(db, engagement_id)
    if sites:
        return sites[0]
    sid = db.scalar(
        select(Site.id).where(Site.project_id == project_id).order_by(Site.code).limit(1)
    )
    if sid is None:
        raise validation_error("vehicle_id", "The project has no site.")
    return sid


def driver_deployment(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID) -> Deployment:
    dep = db.scalar(
        select(Deployment)
        .where(
            Deployment.project_id == project_id,
            Deployment.worker_id == worker_id,
            Deployment.status == DeploymentStatus.mobilised,
        )
        .limit(1)
    )
    if dep is None:
        raise validation_error(
            "driver_worker_id", "The driver has no Mobilised deployment on this project."
        )
    return dep


def driver_check(
    db: Session, cf: c.Cfg, project_id: uuid.UUID, worker_id: uuid.UUID, v: Vehicle, d: date
) -> tuple[DriverAuthorisation | None, list[ApiWarning]]:
    """PU-6 (also JM-2)."""
    auth = c.covering_auth(db, project_id, worker_id, v.driver_group, d)
    if auth is not None:
        return auth, []
    if cf.auth_policy == SiteVehPolicy.block:
        raise c.err(
            422,
            ErrorCode.DRIVER_NOT_AUTHORISED,
            "The driver holds no Active authorisation for this vehicle group "
            "(driver_auth_policy block).",
            "لا يحمل السائق تفويضاً سارياً لفئة هذه المركبة (سياسة المنع).",
            "driver_worker_id",
        )
    return None, [sv.warn(SiteVehWarning.DRIVER_NOT_AUTHORISED_WARN, "driver_worker_id")]


def create_check(
    db: Session, p: Principal, project_id: uuid.UUID, body: SiteVehCheckCreate
) -> SiteVehCheckRead:
    proj = c.project(db, p, project_id)
    cf = c.require_live(db, project_id)
    g = p.require(project_id, C.pre_use_record)
    v = db.get(Vehicle, body.vehicle_id)
    if v is None or v.project_id != project_id or not c.is_site(v):
        raise validation_error("vehicle_id", "Not a site vehicle of this project.")
    if v.status == VehicleStatus.withdrawn:
        raise validation_error("vehicle_id", "The vehicle is withdrawn.")
    dep = driver_deployment(db, project_id, body.driver_worker_id)
    if not c.covers_any(db, g, [v.engagement_id, dep.engagement_id]):
        raise forbidden_error("This vehicle and driver are outside your scope.")
    today = c.local_day()
    d = body.check_date or today
    if d > today:
        raise validation_error("check_date", "Cannot be in the future.")
    if cf.live_from is not None and d < cf.live_from:
        raise validation_error("check_date", "Before site_vehicles_from.")
    completed_at = body.completed_at or now()
    if completed_at > now():
        raise validation_error("completed_at", "Cannot be in the future.")
    exists = db.scalar(
        select(VehicleCheck.id).where(VehicleCheck.vehicle_id == v.id, VehicleCheck.check_date == d)
    )
    if exists is not None and c.active_hold(db, v.id) is None:
        raise c.err(
            422,
            ErrorCode.PRE_USE_CHECK_EXISTS,
            "This vehicle already has a pre-use check on this date.",
            "يوجد فحص يومي لهذه المركبة في هذا التاريخ.",
            "check_date",
        )
    if body.source == SiteVehCheckSource.paper and body.paper_photo is None:
        raise validation_error("paper_photo", "A photo of the signed paper card is required.")
    t = _template(db, v, completed_at)
    auth, warns = driver_check(db, cf, project_id, body.driver_worker_id, v, d)
    if not v.docs_verified_at and v.plate_type.value != "none":
        warns.append(sv.warn(SiteVehWarning.VEHICLE_DOCS_UNVERIFIED))
    raw = [x.model_dump(mode="json") for x in body.answers]
    sc = scoring.evaluate(t.items, raw, airside=True, require_all=True)
    by_code = {x.item_code: (i, x) for i, x in enumerate(body.answers)}
    pass_mark = max(D(t.pass_mark_pct), fc.cfg(db, project_id).dec("inspection_pass_mark_pct"))
    pct = sc.pct
    passed = not (sc.critical_fails or (pct is not None and pct < pass_mark))
    seq, no = c.next_check_no(db, project_id, d)
    site_id = site_for(db, project_id, v.engagement_id)
    r = ChecklistResponse(
        project_id=project_id,
        client_uuid=uuid.uuid4(),
        owner_type=ResponseOwnerType.vehicle_check,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        inspection_type=InspectionType.plant_vehicle,
        site_id=site_id,
        engagement_id=v.engagement_id,
        airside=False,
        started_at=completed_at,
        completed_at=completed_at,
        completed_date=d,
        received_at=now(),
        inspector_id=p.user.id,
        answers=[],
        applicable_count=sc.applicable_count,
        compliant_count=sc.compliant_count,
        applicable_weight=sc.applicable_weight,
        earned_weight=sc.earned_weight,
        score_pct=scoring.q(pct) if pct is not None else None,
        critical_fail_count=sc.critical_fails,
        result=ResponseResult.pass_ if passed else ResponseResult.fail,
        submitted=True,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    raw_warn: list[dict[str, Any]] = []
    r.answers = execution.store_answers(db, p.user.id, r, sc, by_code, raw_warn)
    photo = None
    if body.paper_photo is not None:
        photo = fc.store_photos(
            db, AttachmentOwner.field_photo, r.id, project_id, [body.paper_photo], p.user.id,
            "paper_photo",
        )[0]  # fmt: skip
    failed = [ev.code for ev in sc.evals if ev.non_compliant]
    ch = VehicleCheck(
        id=uuid.uuid4(),
        project_id=project_id,
        check_no=no,
        seq=seq,
        vehicle_id=v.id,
        engagement_id=v.engagement_id,
        driver_worker_id=body.driver_worker_id,
        driver_engagement_id=dep.engagement_id,
        driver_group=v.driver_group,
        driver_authorised=auth is not None,
        authorisation_id=auth.id if auth else None,
        check_date=d,
        response_id=r.id,
        template_code=t.template_code,
        passed=passed,
        critical_fail_count=sc.critical_fails,
        failed_items=failed,
        source=body.source,
        paper_photo_id=photo,
        recorded_by_user_id=p.user.id,
        completed_at=completed_at,
        created_by_user_id=p.user.id,
    )
    db.add(ch)
    db.flush()
    outcomes(db, p, proj, v, ch, r, sc, by_code)
    all_warns = warns + [ApiWarning(**x) for x in raw_warn]
    ch.warnings = [w.model_dump() for w in all_warns]
    db.flush()
    c.refresh(db, v)
    c.record(db, p, AuditAction.create, EntityType.vehicle_check, ch, project_id)
    return check_read(db, p, ch, warnings=all_warns)


def outcomes(
    db: Session,
    p: Principal | None,
    proj: Project,
    v: Vehicle,
    ch: VehicleCheck,
    r: ChecklistResponse,
    sc: scoring.Score,
    by_code: dict[str, tuple[int, Any]],
    *,
    raised_at: datetime | None = None,
    seed_fake: bool = False,
) -> None:
    """Findings (PU-3, PU-4) and the PU-3 hold / Phase 4 defect."""
    uid = p.user.id if p else None
    findings: list[FieldFinding] = []
    for n, ev in enumerate([e for e in sc.evals if e.non_compliant], start=1):
        sev = scoring.finding_severity(ev, audit=False) or FindingSeverity.minor
        a = by_code.get(ev.code, (0, None))[1]
        note = (getattr(a, "note", None) or ev.item.get("text_en") or "").strip()
        ff = FieldFinding(
            project_id=proj.id,
            response_id=r.id,
            finding_no=f"{ch.check_no}-F{n:02d}",
            item_code=ev.code,
            severity=sev,
            critical_item=ev.critical,
            description_en=note[:1000] or None,
            responsible_engagement_id=v.engagement_id,
            site_id=r.site_id,
            engagement_id=v.engagement_id,
            completed_date=ch.check_date,
            created_by_user_id=uid,
        )
        db.add(ff)
        findings.append(ff)
    db.flush()
    critical = [f for f in findings if f.critical_item]
    if not critical:
        return
    item = c.phase4_items(db, [v.id]).get(v.id)
    texts = ", ".join(f.item_code or "" for f in critical)
    if item is not None:
        from app.services.cert.defects import new_defect  # noqa: PLC0415

        dfx = new_defect(
            db,
            proj.id,
            item=item,
            scaffold=None,
            engagement_id=v.engagement_id,
            source=DefectSource.pre_use_check,
            category=DefectCategory.A,
            description_en=f"Pre-use check {ch.check_no}: critical item(s) failed ({texts}).",
            description_ar=f"فشل بند حرج في الفحص اليومي {ch.check_no}.",
            raised_at=raised_at or ch.completed_at,
            p=p,
            raised_by_worker_id=ch.driver_worker_id,
            source_ref=ch.check_no,
            seed_fake=seed_fake,
        )
        ch.phase4_defect_id = dfx.id
        return
    ch.hold_set = True
    ca = fc.make_ca(
        db, proj, CaSourceType.site_vehicle, ch.id, r.site_id, None, v.engagement_id,
        FindingSeverity.critical.value,
        f"Defect hold {v.vehicle_no} ({v.fleet_no}): {texts}",
        f"Pre-use check {ch.check_no} failed critical item(s) {texts}; the vehicle is on "
        "defect hold until repaired and a passing check is recorded (7b PU-3).",
        None, uid, uid,
    )  # fmt: skip
    for f in critical:
        f.ca_id = ca.id
        f.ca_required = True
    db.flush()
    users = c.rep_users(db, proj.id, v.engagement_id) | c.officer_users(db, proj.id)
    c.send(
        db,
        users,
        NotificationKind.vehicle_defect_hold,
        f"Defect hold on {v.vehicle_no} ({v.fleet_no}): {texts} failed in {ch.check_no}.",
        f"إيقاف المركبة {v.vehicle_no} بسبب عيب في بند حرج ({ch.check_no}).",
        proj.id,
        EntityType.vehicle,
        v.id,
    )


def ca_ref_of(db: Session, check_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(CorrectiveAction.ref).where(
            CorrectiveAction.source_type == CaSourceType.site_vehicle,
            CorrectiveAction.source_id == check_id,
        )
    )
