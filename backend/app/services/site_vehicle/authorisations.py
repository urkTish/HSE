"""7b.2 Driver / operator authorisations (spec 7b-fleet-driver §3.2, §4.2, §6.1, DA-1…DA-3).

Hooks are the existing providers only (DA-2): Phase 5 `training_course` (DEF-DRV for road groups,
BUS-DRV for bus), 6a `medical_fitness` DRIVER-FIT (bus, heavy, plant) and the Phase 4
`personnel_certificate` with the EQC operator code of linked plant. Policy `driver_hook_policy`
follows Phase 2 HK-4: warn → result `warn` + HOOK_NOT_MET_WARN; block → 422 HOOK_NOT_MET."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    HookKind,
    HookProviderStatus,
    HookSubjectType,
    LicenceClass,
    VehicleStatus,
)
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.site_vehicle_enums import (
    LIVE_AUTH,
    ROAD_GROUPS,
    SiteVehAuthStatus,
    SiteVehDriverGroup,
    SiteVehHookResult,
    SiteVehLimitingFactor,
    SiteVehPolicy,
    SiteVehWarning,
)
from app.kpi.periods import add_months
from app.models import Deployment, DriverAuthorisation, Vehicle, Worker
from app.schemas.hse_common import ApiWarning
from app.schemas.site_vehicle import (
    SiteVehAuthCreate,
    SiteVehAuthPage,
    SiteVehAuthPrefill,
    SiteVehAuthRead,
    SiteVehAuthTransition,
    SiteVehAuthUpdate,
    SiteVehHookResultRead,
)
from app.services.access.hooks import HookCheck, HookContext
from app.services.common import duplicate, invalid_transition
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.site_vehicle import common as c
from app.services.site_vehicle.vehicles import operator_code, warn

C = Capability
S = SiteVehAuthStatus
G = SiteVehDriverGroup
L = SiteVehLimitingFactor
ASSESSMENT_MAX_MONTHS = 12
# LCV (7a list, Phase 2 classes) → road groups covered (DA-1)
LCV_GROUPS: dict[LicenceClass, frozenset[SiteVehDriverGroup]] = {
    LicenceClass.private: frozenset({G.light}),
    LicenceClass.public_transport: frozenset({G.light, G.bus}),
    LicenceClass.heavy_transport: frozenset({G.light, G.bus, G.heavy}),
    LicenceClass.heavy_equipment: frozenset(),
    LicenceClass.motorcycle: frozenset(),
}
OK = (HookProviderStatus.met, HookProviderStatus.expiring)
SNAP = ("groups", "licence_issuer", "licence_class", "licence_expiry", "assessment_date",
        "assessor", "issued_on", "own_valid_until", "effective_valid_until", "limiting_factor",
        "status", "status_reason", "plant_vehicle_ids")  # fmt: skip


def snap(a: DriverAuthorisation) -> dict[str, Any]:
    return {k: getattr(a, k) for k in SNAP}


# ---- reading -------------------------------------------------------------------------------------


def auth_read(
    db: Session,
    p: Principal | None,
    a: DriverAuthorisation,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> SiteVehAuthRead:
    refs = refs or Refs(db)
    red = p is not None and c.status_only(p, a.project_id)
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    names = p is None or c.names_visible(p, a.project_id)
    return SiteVehAuthRead(
        id=a.id,
        auth_no=a.auth_no,
        project_id=a.project_id,
        worker=c.worker_ref(w, names),
        engagement=refs.eng(a.engagement_id),
        groups=[G(g) for g in a.groups or []],
        status=a.status,
        redacted=red,
        licence_issuer=None if red else a.licence_issuer,
        licence_class=None if red else a.licence_class,
        licence_expiry=None if red else a.licence_expiry,
        licence_prefilled_from_adp=False if red else a.licence_prefilled_from_adp,
        assessment_date=None if red else a.assessment_date,
        assessor=None if red else a.assessor,
        issued_on=a.issued_on,
        own_valid_until=None if red else a.own_valid_until,
        effective_valid_until=a.effective_valid_until,
        limiting_factor=None if red else a.limiting_factor,
        hook_results=[] if red else [SiteVehHookResultRead(**h) for h in a.hook_results or []],
        hooks_evaluated_at=None if red else a.hooks_evaluated_at,
        plant_vehicle_ids=list(a.plant_vehicle_ids or []),
        status_reason=None if red else a.status_reason,
        status_changed_at=a.status_changed_at,
        activated_at=a.activated_at,
        warnings=warnings or [],
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _get(db: Session, p: Principal, auth_id: uuid.UUID) -> DriverAuthorisation:
    a = db.get(DriverAuthorisation, auth_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Authorisation")
    c.require_live(db, a.project_id)
    g = c.view_grant(p, a.project_id)
    if not c.covers_eng(db, g, a.engagement_id):
        raise not_found("Authorisation")
    return a


def read_auth(db: Session, p: Principal, auth_id: uuid.UUID) -> SiteVehAuthRead:
    return auth_read(db, p, _get(db, p, auth_id))


def list_auths(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[SiteVehAuthStatus] | None,
    groups: list[SiteVehDriverGroup] | None,
    engagement_ids: list[uuid.UUID] | None,
    worker_id: uuid.UUID | None,
    expiring_within_days: int | None,
    page: int,
    page_size: int,
) -> SiteVehAuthPage:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    g = c.view_grant(p, project_id)
    A = DriverAuthorisation  # noqa: N806
    stmt = select(A).where(A.project_id == project_id)
    if statuses:
        stmt = stmt.where(A.status.in_(statuses))
    if worker_id:
        stmt = stmt.where(A.worker_id == worker_id)
    if engagement_ids:
        stmt = stmt.where(A.engagement_id.in_(engagement_ids))
    rows = [a for a in db.scalars(stmt.order_by(A.seq)) if c.covers_eng(db, g, a.engagement_id)]
    if groups:
        rows = [a for a in rows if set(a.groups or []) & {x.value for x in groups}]
    if expiring_within_days is not None:
        lim = c.local_day() + timedelta(days=expiring_within_days)
        rows = [
            a
            for a in rows
            if a.effective_valid_until is not None and a.effective_valid_until <= lim
        ]
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    refs = Refs(db).load(engs=[a.engagement_id for a in rows])
    return SiteVehAuthPage(
        items=[auth_read(db, p, a, refs) for a in rows], total=total, page=page, page_size=page_size
    )


def prefill(
    db: Session, p: Principal, project_id: uuid.UUID, worker_id: uuid.UUID
) -> SiteVehAuthPrefill:
    from app.services.incident_vehicles import adp_of  # noqa: PLC0415

    c.project(db, p, project_id)
    c.require_live(db, project_id)
    g = p.grant(project_id, C.driver_auth_manage)
    if g is None:
        raise forbidden_error()
    dep = c.mobilised_deployment(db, project_id, worker_id)
    if not c.covers_eng(db, g, dep.engagement_id):
        raise forbidden_error("This worker is outside your scope.")
    adp = adp_of(db, project_id, worker_id)
    live = _live(db, project_id, worker_id)
    return SiteVehAuthPrefill(
        worker_id=worker_id,
        adp_no=adp.adp_no if adp else None,
        licence_issuer=adp.licence_issuer if adp else None,
        licence_class=adp.licence_class if adp else None,
        licence_expiry=adp.licence_expiry_date if adp else None,
        live_authorisation_no=live.auth_no if live else None,
    )


# ---- hooks and effective validity (DA-2, §6.1) ---------------------------------------------------


@dataclass
class Need:
    kind: HookKind
    code: str
    factor: SiteVehLimitingFactor
    vehicle_id: uuid.UUID | None = None


def needs(db: Session, a: DriverAuthorisation, cf: c.Cfg) -> list[Need]:
    groups = {G(g) for g in a.groups or []}
    out: list[Need] = []
    if groups & ROAD_GROUPS:
        out.append(Need(HookKind.training_course, cf["defensive_driving_code"], L.training))
    if G.bus in groups:
        out.append(Need(HookKind.training_course, cf["bus_driving_code"], L.training))
    if groups & {G.bus, G.heavy, G.plant}:
        out.append(Need(HookKind.medical_fitness, c.MEDICAL_CODE, L.medical))
    if G.plant in groups:
        items = c.phase4_items(db, a.plant_vehicle_ids or [])
        seen: set[str] = set()
        for vid in a.plant_vehicle_ids or []:
            code = operator_code(items.get(vid))
            if code and code not in seen:
                seen.add(code)
                out.append(Need(HookKind.personnel_certificate, code, L.operator_certificate, vid))
    return out


def _provider(
    db: Session, n: Need, worker_id: uuid.UUID, at: datetime, project_id: uuid.UUID
) -> HookCheck:
    ctx = HookContext(project_id=project_id, vehicle_id=n.vehicle_id)
    W = HookSubjectType.worker  # noqa: N806
    if n.kind == HookKind.training_course:
        from app.services.train import hook as thook  # noqa: PLC0415

        return thook.check(db, W, worker_id, n.code, at, ctx, project_id)
    if n.kind == HookKind.medical_fitness:
        from app.services.med import hook as mhook  # noqa: PLC0415

        return mhook.check(db, W, worker_id, n.code, at, ctx, project_id)
    from app.services.cert import providers  # noqa: PLC0415

    return providers.check(db, W, worker_id, n.kind, n.code, at, ctx, project_id)


def evaluate(
    db: Session, a: DriverAuthorisation, at: datetime | None = None
) -> tuple[list[dict[str, Any]], bool]:
    """Store hook_results and the effective validity; returns (results, any_not_met)."""
    cf = c.cfg(db, a.project_id)
    at = at or now()
    results: list[dict[str, Any]] = []
    bad = False
    terms: list[tuple[date, SiteVehLimitingFactor]] = [(a.own_valid_until, L.own_validity)]
    groups = {G(g) for g in a.groups or []}
    if groups & ROAD_GROUPS and a.licence_expiry:
        terms.append((a.licence_expiry, L.licence))
    w = db.get(Worker, a.worker_id)
    if w is not None and w.id_expiry_date:
        terms.append((w.id_expiry_date, L.worker_id))
    dep = db.get(Deployment, a.deployment_id)
    if dep is not None:
        end = dep.demobilised_on or dep.planned_demob_on
        if end:
            terms.append((end, L.deployment_end))
    for n in needs(db, a, cf):
        hc = _provider(db, n, a.worker_id, at, a.project_id)
        if hc.status in OK:
            res = SiteVehHookResult.met
            if hc.valid_until:
                terms.append((hc.valid_until, n.factor))
        else:
            bad = True
            res = (
                SiteVehHookResult.warn
                if cf.hook_policy == SiteVehPolicy.warn
                else SiteVehHookResult.not_met
            )
        results.append(
            {
                "kind": n.kind.value,
                "code": n.code,
                "result": res.value,
                "provider_status": hc.status.value,
                "valid_until": hc.valid_until.isoformat() if hc.valid_until else None,
                "ref": hc.ref,
                "reason_code": hc.reason_code,
                "vehicle_id": str(n.vehicle_id) if n.vehicle_id else None,
            }
        )
    eff, factor = min(terms, key=lambda t: t[0])
    a.hook_results = results
    a.hooks_evaluated_at = at
    a.effective_valid_until = eff
    a.limiting_factor = factor
    return results, bad


# ---- validation (DA-1) ---------------------------------------------------------------------------


def _live(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID) -> DriverAuthorisation | None:
    return db.scalar(
        select(DriverAuthorisation).where(
            DriverAuthorisation.project_id == project_id,
            DriverAuthorisation.worker_id == worker_id,
            DriverAuthorisation.status.in_(list(LIVE_AUTH)),
        )
    )


def validate(db: Session, a: DriverAuthorisation, today: date) -> None:
    cf = c.cfg(db, a.project_id)
    groups = {G(g) for g in a.groups or []}
    road = groups & ROAD_GROUPS
    if road:
        if a.licence_class is None or a.licence_expiry is None or a.licence_issuer is None:
            raise validation_error(
                "licence_class", "Licence issuer, class and expiry are required for road groups."
            )
        if not road <= LCV_GROUPS[a.licence_class]:
            raise c.err(
                422,
                ErrorCode.LICENCE_CLASS_NOT_COVERING,
                f"Licence class {a.licence_class.value} does not cover "
                f"{', '.join(sorted(g.value for g in road - LCV_GROUPS[a.licence_class]))}.",
                "فئة الرخصة لا تغطي جميع فئات القيادة المطلوبة.",
                "licence_class",
            )
        if a.licence_expiry <= today:
            raise validation_error("licence_expiry", "The licence must expire after today.")
    if a.assessment_date > a.issued_on:
        raise validation_error("assessment_date", "The assessment cannot be after the issue date.")
    if add_months(a.assessment_date, ASSESSMENT_MAX_MONTHS) < a.issued_on:
        raise c.err(
            422,
            ErrorCode.ASSESSMENT_TOO_OLD,
            "The practical assessment must be at most 12 months before the issue date.",
            "يجب ألا يتجاوز عمر التقييم العملي 12 شهراً قبل تاريخ الإصدار.",
            "assessment_date",
        )
    months = int(cf["driver_auth_validity_months"])
    cap = add_months(a.issued_on, months) - timedelta(days=1)
    if a.own_valid_until is None:
        a.own_valid_until = cap
    if a.own_valid_until > cap:
        raise validation_error(
            "own_valid_until", f"At most issued_on + {months} months ({cap.isoformat()})."
        )
    if a.own_valid_until < a.issued_on:
        raise validation_error("own_valid_until", "Must be on or after issued_on.")
    pv = list(dict.fromkeys(a.plant_vehicle_ids or []))
    if pv and G.plant not in groups:
        raise validation_error("plant_vehicle_ids", "Only with group plant.")
    for i, vid in enumerate(pv):
        v = db.get(Vehicle, vid)
        if (
            v is None
            or v.project_id != a.project_id
            or not c.is_site(v)
            or v.driver_group != G.plant
            or v.status == VehicleStatus.withdrawn
        ):
            raise validation_error(f"plant_vehicle_ids[{i}]", "Not site plant of this project.")
    a.plant_vehicle_ids = pv


def _prefill_licence(db: Session, a: DriverAuthorisation) -> None:
    from app.services.incident_vehicles import adp_of  # noqa: PLC0415

    if a.licence_class is not None or a.licence_expiry is not None:
        return
    adp = adp_of(db, a.project_id, a.worker_id)
    if adp is None:
        return
    a.licence_issuer = adp.licence_issuer
    a.licence_class = adp.licence_class
    a.licence_expiry = adp.licence_expiry_date
    a.licence_prefilled_from_adp = True


def hook_warnings(results: list[dict[str, Any]]) -> list[ApiWarning]:
    bad = [f"{h['code']}" for h in results if h["result"] != SiteVehHookResult.met.value]
    if not bad:
        return []
    w = warn(SiteVehWarning.HOOK_NOT_MET_WARN)
    w.message = f"{w.message} ({', '.join(bad)})"
    return [w]


# ---- writing -------------------------------------------------------------------------------------


def create_auth(
    db: Session, p: Principal, project_id: uuid.UUID, body: SiteVehAuthCreate
) -> SiteVehAuthRead:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    g = p.require(project_id, C.driver_auth_manage)
    dep = c.mobilised_deployment(db, project_id, body.worker_id)
    if not c.covers_eng(db, g, dep.engagement_id):
        raise forbidden_error("This worker is outside your scope.")
    if _live(db, project_id, body.worker_id) is not None:
        raise duplicate("worker_id", "The worker already holds a live authorisation.")
    seq, no = c.next_auth_no(db, project_id)
    data = body.model_dump()
    data.pop("worker_id")
    data["groups"] = [G(x).value for x in dict.fromkeys(data["groups"])]
    a = DriverAuthorisation(
        id=uuid.uuid4(),
        project_id=project_id,
        seq=seq,
        auth_no=no,
        worker_id=body.worker_id,
        deployment_id=dep.id,
        engagement_id=dep.engagement_id,
        status=S.draft,
        proposed_by_user_id=p.user.id,
        created_by_user_id=p.user.id,
        hook_results=[],
        **data,
    )
    _prefill_licence(db, a)
    today = c.local_day()
    validate(db, a, today)
    results, _ = evaluate(db, a)
    db.add(a)
    db.flush()
    c.record(db, p, AuditAction.create, EntityType.driver_authorisation, a, project_id)
    return auth_read(db, p, a, warnings=hook_warnings(results))


def update_auth(
    db: Session, p: Principal, auth_id: uuid.UUID, body: SiteVehAuthUpdate
) -> SiteVehAuthRead:
    a = _get(db, p, auth_id)
    g = p.require(a.project_id, C.driver_auth_manage)
    if not c.covers_eng(db, g, a.engagement_id):
        raise forbidden_error()
    if a.status != S.draft:
        raise invalid_transition("Authorisation", a.status, "edited")
    before = snap(a)
    ch = body.changes()
    if "groups" in ch:
        ch["groups"] = [G(x).value for x in dict.fromkeys(ch["groups"])]
    if {"licence_class", "licence_expiry", "licence_issuer"} & set(ch):
        a.licence_prefilled_from_adp = False
    for k, v in ch.items():
        setattr(a, k, v)
    validate(db, a, c.local_day())
    results, _ = evaluate(db, a)
    a.updated_by_user_id = p.user.id
    a.updated_at = now()
    db.flush()
    c.record(
        db, p, AuditAction.update, EntityType.driver_authorisation, a, a.project_id, before=before
    )
    return auth_read(db, p, a, warnings=hook_warnings(results))


MOVES = {
    (S.draft, S.active),
    (S.suspended, S.active),
    (S.active, S.suspended),
    (S.draft, S.revoked),
    (S.active, S.revoked),
    (S.suspended, S.revoked),
    (S.expired, S.revoked),
}


def transition(
    db: Session, p: Principal, auth_id: uuid.UUID, body: SiteVehAuthTransition
) -> SiteVehAuthRead:
    a = _get(db, p, auth_id)
    g = p.require(a.project_id, C.driver_auth_manage)
    if not c.covers_eng(db, g, a.engagement_id):
        raise forbidden_error()
    if c.is_rep_only(p, a.project_id):
        raise forbidden_error("Contractor HSE Reps propose authorisations only (§5.7 235 C).")
    to = body.to_status
    if (a.status, to) not in MOVES:
        raise invalid_transition("Authorisation", a.status, to)
    reason = (body.reason or "").strip()
    if to == S.suspended and len(reason) < 20:
        raise validation_error("reason", "A reason of at least 20 characters is required.")
    if a.status == S.suspended and to == S.active and len(reason) < 5:
        raise validation_error("reason", "A reason is required to reinstate.")
    before = snap(a)
    warnings: list[ApiWarning] = []
    if to == S.active:
        today = c.local_day()
        validate(db, a, today)
        results, bad = evaluate(db, a)
        cf = c.cfg(db, a.project_id)
        if bad and cf.hook_policy == SiteVehPolicy.block:
            failed = [h["code"] for h in results if h["result"] != "met"]
            raise c.err(
                422,
                ErrorCode.HOOK_NOT_MET,
                f"Requirements not met: {', '.join(failed)} (driver_hook_policy block).",
                "متطلبات غير مستوفاة (سياسة المنع).",
                None,
                codes=failed,
            )
        warnings = hook_warnings(results)
        if a.effective_valid_until is not None and a.effective_valid_until < today:
            raise validation_error(
                "effective_valid_until",
                f"The authorisation would already be expired ({a.limiting_factor}).",
            )
        a.activated_at = a.activated_at or now()
        a.activated_by_user_id = p.user.id
    a.status = to
    a.status_reason = reason or None
    a.status_changed_at = now()
    a.updated_by_user_id = p.user.id
    a.updated_at = now()
    db.flush()
    c.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.driver_authorisation,
        a,
        a.project_id,
        before=before,
        details={"reason": reason} if reason else None,
    )
    return auth_read(db, p, a, warnings=warnings)
