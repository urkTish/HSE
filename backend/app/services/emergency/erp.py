"""ERP revisions with scenarios (§3.1, §3.2, §4.1, ER-3…ER-8), assembly points (§3.3, ER-6,
§4.3), emergency contacts (§3.4) and zone emergency profiles (§3.5)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind, QrTokenStatus
from app.core.clock import now
from app.core.emergency_enums import ActiveStatus, Agency, ErpAction, ErpStatus, ScenarioType
from app.core.enums import AirsideArea, AuditAction, Capability, EntityType, SiteStatus, ZoneStatus
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.ptw_enums import PermitStatus
from app.models import AssemblyPoint, EmergencyContact, Erp, Permit, Site, Zone
from app.models import ZoneEmergencyProfile as Profile
from app.schemas.emergency import (
    ApCreate,
    ApPage,
    ApRead,
    ApUpdate,
    ContactCreate,
    ContactPage,
    ContactRead,
    ContactUpdate,
    ErpCreate,
    ErpPage,
    ErpRead,
    ErpTransition,
    ErpUpdate,
    ReviewTrigger,
    ScenarioRead,
    ZoneProfileInput,
    ZoneProfileList,
    ZoneProfileRead,
)
from app.services.access import common as acommon
from app.services.common import invalid_transition
from app.services.emergency import common as ec
from app.services.emergency import reference as ref
from app.services.permissions import Principal
from app.services.train.validity import add_months

C = Capability
RESTRICTED = (AirsideArea.ils_critical, AirsideArea.ils_sensitive)


# ---- ERP -----------------------------------------------------------------------------------------


def erp_read(db: Session, e: Erp) -> ErpRead:
    d = ec.local_day()
    in_force = ec.erp_in_force(db, e.project_id)
    return ErpRead(
        id=e.id,
        erp_no=e.erp_no,
        project_id=e.project_id,
        revision=e.revision,
        title_en=e.title_en,
        title_ar=e.title_ar,
        document_ref=e.document_ref,
        document_attachment_id=e.document_attachment_id,
        site_ids=list(e.site_ids or []),
        scenarios=[ScenarioRead.model_validate(s) for s in e.scenarios or []],
        client_acceptance_ref=e.client_acceptance_ref,
        accepted_on=e.accepted_on,
        airport_interface_ref=e.airport_interface_ref,
        prepared_by=ec.user_ref(db, e.prepared_by_user_id),
        approved_by=ec.user_ref(db, e.approved_by_user_id),
        approved_at=e.approved_at,
        review_due_on=e.review_due_on,
        overdue=e.status == ErpStatus.approved and ec.erp_overdue(e, d),
        in_force=in_force is not None and in_force.id == e.id,
        review_required=e.review_required,
        review_triggers=[ReviewTrigger.model_validate(t) for t in e.review_triggers or []],
        status=e.status,
        status_reason=e.status_reason,
    )


def _erp(db: Session, p: Principal, erp_id: uuid.UUID) -> Erp:
    e = db.get(Erp, erp_id)
    if e is None or not p.can_see_project(e.project_id):
        raise not_found("Emergency response plan")
    ec.need(p, e.project_id, C.emergency_view, write=False)
    return e


def list_erps(db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int) -> ErpPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    rows = list(
        db.scalars(select(Erp).where(Erp.project_id == project_id).order_by(Erp.revision.desc()))
    )
    items = [erp_read(db, e) for e in rows[(page - 1) * size : page * size]]
    return ErpPage(items=items, total=len(rows), page=page, page_size=size)


def create_erp(db: Session, p: Principal, project_id: uuid.UUID, body: ErpCreate) -> ErpRead:
    pr = ec.project(db, p, project_id)
    p.require(project_id, C.erp_prepare)
    open_ = db.scalar(
        select(Erp.id).where(
            Erp.project_id == project_id,
            Erp.status.in_((ErpStatus.draft, ErpStatus.submitted)),
        )
    )
    if open_ is not None:
        raise invalid_transition("Emergency response plan", "draft", "new revision")
    cur = ec.erp_in_force(db, project_id)
    n = int(db.scalar(select(func.max(Erp.revision)).where(Erp.project_id == project_id)) or 0)
    e = Erp(
        id=uuid.uuid4(),
        erp_no=f"ERP-{pr.code}-r{n + 1}",
        project_id=project_id,
        revision=n + 1,
        title_en=body.title_en or (cur.title_en if cur else f"Emergency Response Plan — {pr.code}"),
        title_ar=body.title_ar or (cur.title_ar if cur else "خطة الاستجابة للطوارئ"),
        document_ref=body.document_ref or (cur.document_ref if cur else f"{pr.code}-ERP"),
        document_attachment_id=cur.document_attachment_id if cur else None,
        site_ids=list(cur.site_ids or []) if cur else [],
        scenarios=[dict(s) for s in cur.scenarios or []] if cur else [],
        client_acceptance_ref=None,
        accepted_on=None,
        airport_interface_ref=cur.airport_interface_ref if cur else None,
        prepared_by_user_id=p.user.id,
        review_required=False,
        review_triggers=[],
        status=ErpStatus.draft,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(e)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.erp, e, project_id)
    return erp_read(db, e)


def read_erp(db: Session, p: Principal, erp_id: uuid.UUID) -> ErpRead:
    return erp_read(db, _erp(db, p, erp_id))


def _rescue_work(db: Session, project_id: uuid.UUID, work_type: str) -> bool:
    """ER-4: an Issued or Active permit of that type in the last 90 days."""
    since = now() - timedelta(days=90)
    row = db.scalar(
        select(Permit.id)
        .where(
            Permit.project_id == project_id,
            Permit.work_types.contains([work_type]),
            or_(
                Permit.status.in_((PermitStatus.issued, PermitStatus.active)),
                Permit.issued_at >= since,
            ),
        )
        .limit(1)
    )
    return row is not None


def check_scenarios(db: Session, project_id: uuid.UUID, site_ids: list[Any], sc: list[Any]) -> None:
    c = ec.cfg(db, project_id)
    seen: set[str] = set()
    for i, s in enumerate(sc):
        fld = f"scenarios.{i}"
        if s["scenario_code"] in seen:
            raise validation_error(fld, "Scenario codes must be unique in the revision.")
        seen.add(s["scenario_code"])
        if site_ids and not {str(x) for x in s["site_ids"]} <= {str(x) for x in site_ids}:
            raise validation_error(fld, "Scenario sites must be sites of the plan.")
        if not (s.get("response_summary_en") or s.get("response_summary_ar")):
            raise validation_error(fld, "Give the response summary in at least one language.")
        mn = c.minimum(ref.DT(s["drill_type"]))
        if mn is not None and int(s["drill_frequency_months"]) > mn:
            raise ec.err(
                422,
                ErrorCode.DRILL_FREQUENCY_TOO_LOW,
                f"{s['scenario_code']}: the drill frequency may not exceed {mn} months (ER-5).",
                f"لا يجوز أن يتجاوز تكرار التمرين {mn} شهراً.",
                field=fld,
                minimum_months=mn,
            )
        st = ScenarioType(s["scenario_type"])
        bare = not s.get("rescue_plan_refs") and not s.get("no_such_work")
        if (
            st in ref.RESCUE_SCENARIOS
            and bare
            and _rescue_work(db, project_id, ref.RESCUE_SCENARIOS[st])
        ):
            raise ec.err(
                422,
                ErrorCode.RESCUE_PLAN_REF_REQUIRED,
                f"{s['scenario_code']}: name a rescue plan reference (ER-4).",
                "اذكر مرجع خطة الإنقاذ.",
                field=fld,
            )


def update_erp(db: Session, p: Principal, erp_id: uuid.UUID, body: ErpUpdate) -> ErpRead:
    e = _erp(db, p, erp_id)
    p.require(e.project_id, C.erp_prepare)
    if e.status != ErpStatus.draft:
        raise invalid_transition("Emergency response plan", e.status, "edited")
    from app.services.cert import common as cc  # noqa: PLC0415

    snap = cc.snap(e)
    ch = body.model_dump(exclude_unset=True, mode="json")
    if "site_ids" in ch and ch["site_ids"] is not None:
        for sid in ch["site_ids"]:
            ec.site_or_422(db, e.project_id, uuid.UUID(sid))
    sites = ch.get("site_ids") if ch.get("site_ids") is not None else [str(x) for x in e.site_ids]
    if ch.get("scenarios") is not None:
        check_scenarios(db, e.project_id, list(sites or []), ch["scenarios"])
    for k, v in ch.items():
        if k == "site_ids":
            e.site_ids = [uuid.UUID(x) for x in v or []]
        elif k == "scenarios":
            e.scenarios = list(v or [])
        elif k == "accepted_on":
            e.accepted_on = body.accepted_on
        elif k == "document_attachment_id":
            e.document_attachment_id = body.document_attachment_id
        else:
            setattr(e, k, v)
    e.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, EntityType.erp, e, e.project_id, before=snap)
    return erp_read(db, e)


def completeness(db: Session, e: Erp) -> list[str]:
    """ER-3: missing items (codes for the meta list)."""
    c = ec.cfg(db, e.project_id)
    out: list[str] = []
    sites = list(
        db.scalars(
            select(Site).where(Site.project_id == e.project_id, Site.status == SiteStatus.active)
        )
    )
    in_plan = set(e.site_ids or [])
    out += [f"site:{s.code}" for s in sites if s.id not in in_plan]
    served: set[uuid.UUID] = set()
    for ap in ec.active_aps(db, e.project_id):
        served |= set(ap.zones_served or [])
    for z in db.scalars(
        select(Zone)
        .where(Zone.project_id == e.project_id, Zone.status == ZoneStatus.active)
        .order_by(Zone.code)
    ):
        if z.id not in served:
            out.append(f"zone:{z.code}")
    mand = list(ref.MANDATORY) + (list(ref.AIRPORT_MANDATORY) if c.airport else [])
    sc = e.scenarios or []
    for t in mand:
        rows = [s for s in sc if s["scenario_type"] == t.value]
        if not rows:
            out.append(f"scenario:{t.value}")
            continue
        covered = {str(x) for s in rows for x in s["site_ids"]}
        if t != ScenarioType.aircraft_emergency and not {str(x) for x in in_plan} <= covered:
            out.append(f"scenario_sites:{t.value}")
    have = {
        Agency(a)
        for a in db.scalars(
            select(EmergencyContact.agency).where(
                EmergencyContact.project_id == e.project_id, EmergencyContact.active.is_(True)
            )
        )
    }
    need = [Agency.civil_defense, Agency.red_crescent]
    if c.airport:
        need += [Agency.airport_arff, Agency.airport_aocc]
    out += [f"contact:{a.value}" for a in need if a not in have]
    if Agency.police not in have and Agency.unified_911 not in have:
        out.append("contact:police")
    if Agency.site_clinic not in have and Agency.hospital not in have:
        out.append("contact:site_clinic")
    if c.client_acceptance and not (e.client_acceptance_ref and e.accepted_on):
        out.append("client_acceptance_ref")
    if c.airport and not e.airport_interface_ref:
        out.append("airport_interface_ref")
    return out


def transition_erp(db: Session, p: Principal, erp_id: uuid.UUID, body: ErpTransition) -> ErpRead:
    e = _erp(db, p, erp_id)
    pid = e.project_id
    before = {"status": e.status.value}
    if body.action == ErpAction.submit:
        p.require(pid, C.erp_prepare)
        if e.status != ErpStatus.draft:
            raise invalid_transition("Emergency response plan", e.status, ErpStatus.submitted)
        e.status = ErpStatus.submitted
        e.submitted_at = now()
        e.status_reason = None
    elif body.action == ErpAction.return_:
        p.require(pid, C.erp_approve)
        if e.status != ErpStatus.submitted:
            raise invalid_transition("Emergency response plan", e.status, ErpStatus.draft)
        e.status = ErpStatus.draft
        e.status_reason = ec.reason(body.reason, 20)
    else:
        p.require(pid, C.erp_approve)
        if e.status != ErpStatus.submitted:
            raise invalid_transition("Emergency response plan", e.status, ErpStatus.approved)
        if e.prepared_by_user_id == p.user.id:
            raise ec.err(
                422,
                ErrorCode.SOD_CONFLICT,
                "The approver must not be the preparer (§4.1).",
                "يجب ألا يكون المعتمد هو من أعد الخطة.",
            )
        check_scenarios(db, pid, [str(x) for x in e.site_ids], list(e.scenarios or []))
        missing = completeness(db, e)
        if missing:
            raise ec.err(
                422,
                ErrorCode.ERP_INCOMPLETE,
                "The plan is incomplete: " + ", ".join(missing),
                "الخطة غير مكتملة: " + "، ".join(missing),
                missing=missing,
            )
        old = ec.erp_in_force(db, pid)
        if old is not None:
            old.status = ErpStatus.superseded
            old.status_reason = f"Superseded by {e.erp_no}"
        at = now()
        d = ec.local_day(at)
        e.status = ErpStatus.approved
        e.approved_by_user_id = p.user.id
        e.approved_at = at
        e.review_due_on = add_months(d, int(ec.cfg(db, pid)["erp_review_months"])) - timedelta(
            days=1
        )
        e.review_required = False
        e.status_reason = None
    e.updated_by_user_id = p.user.id
    db.flush()
    ec.record(
        db, p, AuditAction.status_change, EntityType.erp, e, pid, before=before,
        details={"action": body.action.value},
    )  # fmt: skip
    return erp_read(db, e)


# ---- assembly points -----------------------------------------------------------------------------


def ap_read(db: Session, a: AssemblyPoint) -> ApRead:
    t = acommon.active_qr(db, a.id)
    z = db.get(Zone, a.zone_id) if a.zone_id else None
    return ApRead(
        id=a.id,
        project_id=a.project_id,
        ap_code=a.ap_code,
        site_id=a.site_id,
        site_code=ec.site_code(db, a.site_id) or "",
        zone_id=a.zone_id,
        zone_code=z.code if z else None,
        location_en=a.location_en,
        location_ar=a.location_ar,
        gps_lat=a.gps_lat,
        gps_lng=a.gps_lng,
        capacity_persons=a.capacity_persons,
        zones_served=list(a.zones_served or []),
        zones_served_codes=ec.codes(db, a.zones_served or []),
        kind=a.kind,
        sticker_payload=acommon.payload(t) if t else None,
        status=a.status,
    )


def list_aps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    page: int,
    size: int,
) -> ApPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    q = select(AssemblyPoint).where(AssemblyPoint.project_id == project_id)
    if site_id is not None:
        q = q.where(AssemblyPoint.site_id == site_id)
    rows = list(db.scalars(q.order_by(AssemblyPoint.ap_code)))
    items = [ap_read(db, a) for a in rows[(page - 1) * size : page * size]]
    return ApPage(items=items, total=len(rows), page=page, page_size=size)


def _restricted(z: Zone) -> bool:
    return bool(z.in_movement_area) or z.airside_area in RESTRICTED


def _check_ap_zones(
    db: Session, site_id: uuid.UUID, zone_id: uuid.UUID | None, served: list[uuid.UUID]
) -> None:
    if zone_id is not None:
        (z,) = ec.zones_of_site(db, site_id, [zone_id], "zone_id")
        if _restricted(z):
            raise ec.err(
                422,
                ErrorCode.ASSEMBLY_POINT_IN_RESTRICTED_AREA,
                f"An assembly point may not be in {z.code} (movement area or ILS area, ER-6).",
                f"لا يجوز وضع نقطة التجمع في {z.code} (منطقة حركة أو منطقة ILS).",
                field="zone_id",
            )
    ec.zones_of_site(db, site_id, served, "zones_served")


def _last_ap_zones(db: Session, a: AssemblyPoint, removed: set[uuid.UUID]) -> list[str]:
    """§4.3: active zones that would be left without an active AP."""
    others: set[uuid.UUID] = set()
    for x in ec.active_aps(db, a.project_id):
        if x.id != a.id:
            others |= set(x.zones_served or [])
    out = []
    for zid in removed - others:
        z = db.get(Zone, zid)
        if z is not None and z.status == ZoneStatus.active:
            out.append(z.code)
    return sorted(out)


def create_ap(db: Session, p: Principal, project_id: uuid.UUID, body: ApCreate) -> ApRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.erp_prepare)
    ec.site_or_422(db, project_id, body.site_id)
    _check_ap_zones(db, body.site_id, body.zone_id, body.zones_served)
    if db.scalar(
        select(AssemblyPoint.id).where(
            AssemblyPoint.project_id == project_id, AssemblyPoint.ap_code == body.ap_code
        )
    ):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("ap_code", "This assembly point code is already used on the project.")
    a = AssemblyPoint(
        id=uuid.uuid4(),
        project_id=project_id,
        **body.model_dump(),
        status=ActiveStatus.active,
        created_by_user_id=p.user.id,
    )
    a.zones_served = list(dict.fromkeys(body.zones_served))
    db.add(a)
    db.flush()
    acommon.issue_qr(db, QrKind.MP, project_id, a.id, a.ap_code)
    ec.record(db, p, AuditAction.create, EntityType.assembly_point, a, project_id)
    return ap_read(db, a)


def update_ap(db: Session, p: Principal, ap_id: uuid.UUID, body: ApUpdate) -> ApRead:
    a = db.get(AssemblyPoint, ap_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Assembly point")
    p.require(a.project_id, C.erp_prepare)
    from app.services.cert import common as cc  # noqa: PLC0415

    snap = cc.snap(a)
    ch = body.changes()
    served = list(dict.fromkeys(ch["zones_served"])) if ch.get("zones_served") else None
    if served is not None:
        _check_ap_zones(db, a.site_id, None, served)
    new_status = ch.get("status") or a.status
    removed: set[uuid.UUID] = set()
    if a.status == ActiveStatus.active:
        if new_status == ActiveStatus.inactive:
            removed = set(a.zones_served or [])
        elif served is not None:
            removed = set(a.zones_served or []) - set(served)
    left = _last_ap_zones(db, a, removed) if removed else []
    if left:
        raise ec.err(
            422,
            ErrorCode.ZONE_WITHOUT_ASSEMBLY_POINT,
            "These active zones would have no assembly point: " + ", ".join(left),
            "ستبقى هذه المناطق بلا نقطة تجمع: " + "، ".join(left),
            zones=left,
        )
    for k, v in ch.items():
        if k == "zones_served":
            a.zones_served = served or []
        elif v is not None:
            setattr(a, k, v)
    if new_status == ActiveStatus.inactive and snap.get("status") == "active":
        acommon.end_qr(db, a.id, QrTokenStatus.revoked)
    elif new_status == ActiveStatus.active and acommon.active_qr(db, a.id) is None:
        acommon.issue_qr(db, QrKind.MP, a.project_id, a.id, a.ap_code)
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, EntityType.assembly_point, a, a.project_id, before=snap)
    return ap_read(db, a)


# ---- contacts ------------------------------------------------------------------------------------


def contact_read(c: EmergencyContact) -> ContactRead:
    return ContactRead(
        id=c.id,
        project_id=c.project_id,
        site_ids=list(c.site_ids or []),
        agency=Agency(c.agency),
        display_name_en=c.display_name_en,
        display_name_ar=c.display_name_ar,
        phone=c.phone,
        person_name=c.person_name,
        available_24h=c.available_24h,
        priority=c.priority,
        active=c.active,
    )


def list_contacts(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int
) -> ContactPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    rows = list(
        db.scalars(
            select(EmergencyContact)
            .where(EmergencyContact.project_id == project_id)
            .order_by(EmergencyContact.agency, EmergencyContact.priority)
        )
    )
    items = [contact_read(c) for c in rows[(page - 1) * size : page * size]]
    return ContactPage(items=items, total=len(rows), page=page, page_size=size)


def create_contact(
    db: Session, p: Principal, project_id: uuid.UUID, body: ContactCreate
) -> ContactRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.erp_prepare)
    for sid in body.site_ids:
        ec.site_or_422(db, project_id, sid)
    data = body.model_dump()
    data["agency"] = body.agency.value
    c = EmergencyContact(
        id=uuid.uuid4(), project_id=project_id, **data, active=True, created_by_user_id=p.user.id
    )
    db.add(c)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.emergency_contact, c, project_id)
    return contact_read(c)


def update_contact(
    db: Session, p: Principal, contact_id: uuid.UUID, body: ContactUpdate
) -> ContactRead:
    c = db.get(EmergencyContact, contact_id)
    if c is None or not p.can_see_project(c.project_id):
        raise not_found("Emergency contact")
    p.require(c.project_id, C.erp_prepare)
    from app.services.cert import common as cc  # noqa: PLC0415

    snap = cc.snap(c)
    for k, v in body.changes().items():
        if k == "site_ids":
            for sid in v or []:
                ec.site_or_422(db, c.project_id, sid)
            c.site_ids = list(v or [])
        elif v is not None:
            setattr(c, k, v)
    c.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, EntityType.emergency_contact, c, c.project_id, before=snap)
    return contact_read(c)


# ---- zone emergency profiles ---------------------------------------------------------------------


def profile_read(db: Session, z: Zone, prof: Profile | None) -> ZoneProfileRead:
    c = ec.cfg(db, z.project_id)
    return ZoneProfileRead(
        zone_id=z.id,
        zone_code=z.code,
        site_id=z.site_id,
        eyewash_required=bool(prof and prof.eyewash_required),
        min_extinguishers=(prof.min_extinguishers if prof and prof.min_extinguishers else None)
        or int(c["min_extinguishers_per_zone"]),
        min_first_aid_kits=(prof.min_first_aid_kits if prof and prof.min_first_aid_kits else None)
        or int(c["min_first_aid_kits_per_zone"]),
        warden_required=ec.warden_required(prof),
        notes=prof.notes if prof else None,
        stored=prof is not None,
    )


def list_profiles(db: Session, p: Principal, project_id: uuid.UUID) -> ZoneProfileList:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    profs = ec.zone_profiles(db, project_id)
    zones = db.scalars(select(Zone).where(Zone.project_id == project_id).order_by(Zone.code))
    return ZoneProfileList(items=[profile_read(db, z, profs.get(z.id)) for z in zones])


def put_profile(
    db: Session, p: Principal, zone_id: uuid.UUID, body: ZoneProfileInput
) -> ZoneProfileRead:
    z = db.get(Zone, zone_id)
    if z is None or not p.can_see_project(z.project_id):
        raise not_found("Zone")
    p.require(z.project_id, C.erp_prepare)
    c = ec.cfg(db, z.project_id)
    for k, base in (
        ("min_extinguishers", c["min_extinguishers_per_zone"]),
        ("min_first_aid_kits", c["min_first_aid_kits_per_zone"]),
    ):
        v = getattr(body, k)
        if v is not None and v < int(base):
            raise ec.err(
                422,
                ErrorCode.SETTING_LOOSENING,
                f"{k} may only be raised above the project default ({base}).",
                "يسمح برفع القيمة فوق الافتراضي فقط.",
                field=k,
            )
    prof = db.get(Profile, zone_id)
    before = {"eyewash_required": prof.eyewash_required} if prof else None
    if prof is None:
        prof = Profile(zone_id=zone_id, project_id=z.project_id)
        db.add(prof)
    prof.eyewash_required = body.eyewash_required
    prof.min_extinguishers = body.min_extinguishers
    prof.min_first_aid_kits = body.min_first_aid_kits
    prof.warden_required = body.warden_required
    prof.notes = body.notes
    prof.updated_at = now()
    prof.updated_by_user_id = p.user.id
    db.flush()
    ec.audit_change(
        db, p, EntityType.zone_emergency_profile, zone_id, z.project_id, before,
        body.model_dump(mode="json"),
    )  # fmt: skip
    return profile_read(db, z, prof)
