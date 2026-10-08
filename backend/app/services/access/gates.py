"""Gates, gate devices, QR gate checks, escort / driver / escort-vehicle pairing and the gate log
(spec 2-access-permits §3.19, §3.20, §5.10 GC-1…GC-16, §6.6)."""

import re
import secrets
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    AreaCategory,
    CrewMemberStatus,
    DeploymentStatus,
    EligibilityContext,
    GateCallerKind,
    GateDirection,
    GateReasonCode,
    GateResult,
    GateStatus,
    GateSubjectKind,
    GateType,
    HookKind,
    HookSubjectType,
    PairingState,
    PairingWaitingFor,
    QrKind,
    QrTokenStatus,
    RequirementKind,
    RequirementStatus,
    ValidityStatus,
    VehicleStatus,
    WapBlocker,
    WapStatus,
    WorkerStatus,
)
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.security import encode_gate_jwt, token_digest
from app.kpi.periods import add_months
from app.models import (
    AccessSettings,
    Avp,
    Deployment,
    Gate,
    GateCheck,
    GateDevice,
    GatePairing,
    ObstacleClearance,
    ProjectEngagement,
    QrToken,
    Site,
    Vehicle,
    Wap,
    WapCrew,
    WapVehicle,
    Worker,
    Zone,
)
from app.models import GateDeviceSession as DeviceSession
from app.schemas.gates import (
    AdmittedDespiteDenialRequest,
    GateCallerContext,
    GateCheckRequest,
    GateCheckResponse,
    GateCreate,
    GateCredentialLine,
    GateDeviceCreate,
    GateDeviceLogin,
    GateDeviceRead,
    GateDeviceRegistered,
    GateDeviceSession,
    GateList,
    GateLogEntry,
    GateLogPage,
    GatePairedResult,
    GatePermitCard,
    GatePersonCard,
    GateRead,
    GateReason,
    GateRef,
    GateUpdate,
    GateVehicleCard,
    GateWapCard,
    GateWapCrewLine,
    PairingRead,
)
from app.schemas.gates import GatePairing as GatePairingRead
from app.services import attachments, audit, notify, projects
from app.services.access import (
    common,
    eligibility,
    hooks,
    lifecycle,
    profiles,
    waps,
    windows,
    workers,
)
from app.services.access.reasons import gate_reason
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability
G = GateReasonCode
R = GateResult
RS = RequirementStatus
GATE_COOKIE = "hse_gate_session"
IDLE = timedelta(hours=12)
RATE_LIMIT = 120
CLEAR_AFTER = 30
PHOTO_TTL = 60
OBS_OK = ("approved", "approved_with_conditions")


@dataclass(frozen=True)
class Caller:
    kind: GateCallerKind
    principal: Principal | None
    device_pk: uuid.UUID | None
    gate_id: uuid.UUID | None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.principal.user.id if self.principal else None

    @property
    def key(self) -> str:
        return f"d:{self.device_pk}" if self.device_pk else f"u:{self.user_id}"


# ---- rate limit (GC-3) ---------------------------------------------------------------------------

_RATE: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _RATE.clear()


def _rate(caller: Caller) -> None:
    t = now().timestamp()
    q = _RATE[caller.key]
    while q and q[0] <= t - 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise ApiError(
            429,
            ErrorCode.GATE_RATE_LIMITED,
            "Too many gate checks; wait a moment.",
            "عدد كبير من عمليات التحقق؛ انتظر قليلًا.",
            meta={"retry_after_seconds": 60},
        )
    q.append(t)


# ---- gates and devices ---------------------------------------------------------------------------


def device_read(db: Session, d: GateDevice, refs: Refs | None = None) -> GateDeviceRead:
    refs = refs or Refs(db)
    return GateDeviceRead(
        id=d.id,
        device_id=d.device_id,
        label=d.label,
        registered_at=d.registered_at,
        registered_by=refs.user(d.registered_by_user_id),
        last_seen_at=d.last_seen_at,
        revoked_at=d.revoked_at,
    )


def gate_read(db: Session, g: Gate, refs: Refs | None = None) -> GateRead:
    refs = refs or Refs(db)
    devices = db.scalars(
        select(GateDevice).where(GateDevice.gate_id == g.id).order_by(GateDevice.registered_at)
    )
    return GateRead(
        id=g.id,
        project_id=g.project_id,
        gate_code=g.gate_code,
        name_en=g.name_en,
        name_ar=g.name_ar,
        site=refs.site(g.site_id),
        protected_zones=[z for z in (refs.zone(x) for x in g.protected_zone_ids or []) if z],
        gate_type=g.gate_type,
        status=g.status,
        devices=[device_read(db, d, refs) for d in devices],
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


def _gate_ref(g: Gate) -> GateRef:
    return GateRef(
        id=g.id, gate_code=g.gate_code, name_en=g.name_en, name_ar=g.name_ar, gate_type=g.gate_type
    )


GATE_CAPS = (C.gate_manage, C.gate_check, C.gate_log_view)


def _gate_view(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    projects.get_visible(db, p, project_id)
    if not any(p.grant(project_id, c) is not None for c in GATE_CAPS):
        raise forbidden_error()


def list_gates(db: Session, p: Principal, project_id: uuid.UUID) -> GateList:
    _gate_view(db, p, project_id)
    rows = list(
        db.scalars(select(Gate).where(Gate.project_id == project_id).order_by(Gate.gate_code))
    )
    refs = Refs(db).load(
        sites=[g.site_id for g in rows], zones=[z for g in rows for z in g.protected_zone_ids or []]
    )
    return GateList(items=[gate_read(db, g, refs) for g in rows])


def get_gate_row(db: Session, p: Principal, gate_id: uuid.UUID) -> Gate:
    g = db.get(Gate, gate_id)
    if g is None:
        raise not_found("Gate")
    _gate_view(db, p, g.project_id)
    return g


def read_gate(db: Session, p: Principal, gate_id: uuid.UUID) -> GateRead:
    return gate_read(db, get_gate_row(db, p, gate_id))


def _check_gate_zones(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    for zid in ids:
        z = db.get(Zone, zid)
        if z is None or z.project_id != project_id or z.site_id != site_id:
            raise validation_error("protected_zone_ids", "Choose zones of the gate's site.")
    return list(dict.fromkeys(ids))


def _snapshot(g: Gate) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(g, k)
            for k in (
                "gate_code",
                "name_en",
                "name_ar",
                "site_id",
                "protected_zone_ids",
                "gate_type",
                "status",
            )
        }
    )


def create_gate(db: Session, p: Principal, project_id: uuid.UUID, body: GateCreate) -> GateRead:
    project = projects.get_visible(db, p, project_id)
    common.require_cap(p, project.id, C.gate_manage, [body.site_id], None)
    site = db.get(Site, body.site_id)
    if site is None or site.project_id != project.id:
        raise validation_error("site_id", "Choose a site of this project.")
    zones = _check_gate_zones(db, project.id, body.site_id, body.protected_zone_ids)
    code = body.gate_code.strip().upper()
    if db.scalar(select(Gate.id).where(Gate.project_id == project.id, Gate.gate_code == code)):
        raise duplicate("gate_code", "This gate code is already used in the project.")
    g = Gate(
        id=uuid.uuid4(),
        project_id=project.id,
        gate_code=code,
        name_en=body.name_en,
        name_ar=body.name_ar,
        site_id=body.site_id,
        protected_zone_ids=zones,
        gate_type=body.gate_type,
        status=GateStatus.active,
        created_by_user_id=p.user.id,
    )
    db.add(g)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.gate,
        entity_id=g.id,
        project_id=project.id,
        after=_snapshot(g),
    )
    return gate_read(db, g)


def update_gate(db: Session, p: Principal, gate_id: uuid.UUID, body: GateUpdate) -> GateRead:
    g = get_gate_row(db, p, gate_id)
    common.require_cap(p, g.project_id, C.gate_manage, [g.site_id], None)
    before = _snapshot(g)
    ch = body.changes()
    if "protected_zone_ids" in ch:
        g.protected_zone_ids = _check_gate_zones(
            db, g.project_id, g.site_id, ch.pop("protected_zone_ids")
        )
    for k, v in ch.items():
        setattr(g, k, v)
    g.updated_at = now()
    g.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _snapshot(g))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(g.project_id),
            entity_type=EntityType.gate,
            entity_id=g.id,
            project_id=g.project_id,
            before=bf,
            after=af,
        )
    return gate_read(db, g)


def register_device(
    db: Session, p: Principal, gate_id: uuid.UUID, body: GateDeviceCreate
) -> GateDeviceRegistered:
    g = get_gate_row(db, p, gate_id)
    common.require_cap(p, g.project_id, C.gate_manage, [g.site_id], None)
    clash = db.scalar(
        select(GateDevice.id)
        .join(Gate, Gate.id == GateDevice.gate_id)
        .where(
            Gate.project_id == g.project_id,
            GateDevice.device_id == body.device_id,
            GateDevice.revoked_at.is_(None),
        )
    )
    if clash:
        raise duplicate("device_id", "This device is already registered; revoke it first.")
    token = secrets.token_urlsafe(32)
    d = GateDevice(
        id=uuid.uuid4(),
        gate_id=g.id,
        device_id=body.device_id,
        label=body.label,
        token_hash=token_digest(token),
        registered_at=now(),
        registered_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(g.project_id),
        entity_type=EntityType.gate,
        entity_id=g.id,
        project_id=g.project_id,
        after={"device_registered": body.device_id},
    )
    return GateDeviceRegistered(device=device_read(db, d), device_token=token)


def revoke_device(
    db: Session, p: Principal, gate_id: uuid.UUID, device_pk: uuid.UUID
) -> GateDeviceRead:
    g = get_gate_row(db, p, gate_id)
    common.require_cap(p, g.project_id, C.gate_manage, [g.site_id], None)
    d = db.get(GateDevice, device_pk)
    if d is None or d.gate_id != g.id:
        raise not_found("Gate device")
    if d.revoked_at is not None:
        raise invalid_transition("Gate device", "revoked", "revoked")
    at = now()
    d.revoked_at = at
    for s in db.scalars(
        select(DeviceSession).where(
            DeviceSession.device_pk == d.id, DeviceSession.revoked_at.is_(None)
        )
    ):
        s.revoked_at = at
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(g.project_id),
        entity_type=EntityType.gate,
        entity_id=g.id,
        project_id=g.project_id,
        after={"device_revoked": d.device_id},
    )
    return device_read(db, d)


def _revoked() -> ApiError:
    return ApiError(
        401,
        ErrorCode.GATE_DEVICE_REVOKED,
        "This gate device is not registered or was revoked.",
        "جهاز البوابة غير مسجل أو تم إلغاؤه.",
    )


def device_login(db: Session, body: GateDeviceLogin, response: Response) -> GateDeviceSession:
    d = db.scalar(
        select(GateDevice).where(GateDevice.token_hash == token_digest(body.device_token))
    )
    if d is None or d.revoked_at is not None:
        raise _revoked()
    g = db.get(Gate, d.gate_id)
    if g is None or g.status != GateStatus.active:
        raise _revoked()
    at = now()
    s = DeviceSession(id=uuid.uuid4(), device_pk=d.id, created_at=at, last_seen_at=at)
    db.add(s)
    d.last_seen_at = at
    db.flush()
    token = encode_gate_jwt(d.id, s.id, at + timedelta(days=30))
    response.set_cookie(
        GATE_COOKIE,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        path="/",
    )
    return GateDeviceSession(
        access_token=token,
        gate=gate_read(db, g),
        device=device_read(db, d),
        idle_timeout_minutes=int(IDLE.total_seconds() // 60),
    )


def device_logout(db: Session, caller: Caller, response: Response) -> None:
    response.delete_cookie(GATE_COOKIE, path="/")
    if caller.device_pk is None:
        return
    for s in db.scalars(
        select(DeviceSession).where(
            DeviceSession.device_pk == caller.device_pk, DeviceSession.revoked_at.is_(None)
        )
    ):
        s.revoked_at = now()
    db.flush()


def device_caller(db: Session, claims: dict[str, Any]) -> Caller:
    """GC-1: validate a gate-device session token."""
    try:
        sid = uuid.UUID(str(claims.get("sid")))
        dpk = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise _revoked() from exc
    s = db.get(DeviceSession, sid)
    at = now()
    if s is None or s.device_pk != dpk or s.revoked_at is not None or s.last_seen_at + IDLE <= at:
        raise _revoked()
    d = db.get(GateDevice, dpk)
    if d is None or d.revoked_at is not None:
        raise _revoked()
    g = db.get(Gate, d.gate_id)
    if g is None or g.status != GateStatus.active:
        raise _revoked()
    s.last_seen_at = at
    d.last_seen_at = at
    return Caller(GateCallerKind.device, None, d.id, g.id)


def context(db: Session, caller: Caller, project_id: uuid.UUID | None) -> GateCallerContext:
    if caller.gate_id is not None:
        g = db.get(Gate, caller.gate_id)
        assert g is not None  # noqa: S101
        gates = [g]
    else:
        p = caller.principal
        assert p is not None  # noqa: S101
        stmt = select(Gate).where(Gate.status == GateStatus.active)
        if project_id:
            stmt = stmt.where(Gate.project_id == project_id)
        gates = [
            g
            for g in db.scalars(stmt.order_by(Gate.gate_code))
            if common.grant_covers(p.grant(g.project_id, C.gate_check), [g.site_id], None)
        ]
        if project_id and not gates and p.grant(project_id, C.gate_check) is None:
            raise forbidden_error()
    seconds = common.settings(db, gates[0].project_id).escort_pairing_seconds if gates else 120
    return GateCallerContext(
        caller_kind=caller.kind,
        gates=[gate_read(db, g) for g in gates],
        escort_pairing_seconds=seconds,
        clear_after_seconds=CLEAR_AFTER,
    )


# ---- check machinery -----------------------------------------------------------------------------


@dataclass
class Verdict:
    deny: list[GateReasonCode] = field(default_factory=list)
    warn: list[GateReasonCode] = field(default_factory=list)
    # 6a HK6-7 / §11.3 GC-7: medical results show only the generic HSE-check texts
    texts: dict[GateReasonCode, tuple[str, str]] = field(default_factory=dict)

    def add(self, code: GateReasonCode, warn: bool = False) -> None:
        target = self.warn if warn else self.deny
        if code not in target:
            target.append(code)

    def merge_items(self, items: list[eligibility.Item]) -> None:
        for i in items:
            if i.status in (RS.not_met, RS.not_evaluated):
                self.add(i.reason or G.HOOK_NOT_MET)
            elif i.status in (RS.warn, RS.expiring) and i.reason:
                self.add(i.reason, warn=True)
            else:
                continue
            if i.hook_kind == HookKind.medical_fitness and i.message and i.reason:
                self.texts.setdefault(i.reason, i.message)

    def result(self) -> GateResult:
        if self.deny:
            return R.DENIED
        return R.GRANTED_WITH_WARNING if self.warn else R.GRANTED

    def reasons(self) -> list[GateReason]:
        out = [gate_reason(c, False) for c in self.deny] + [gate_reason(c, True) for c in self.warn]
        for r in out:
            if r.code in self.texts:
                r.message_en, r.message_ar = self.texts[r.code]
        return out

    def codes(self) -> list[str]:
        return [c.value for c in self.deny + self.warn]


def _authorise(db: Session, caller: Caller, gate_id: uuid.UUID) -> Gate:
    g = db.get(Gate, gate_id)
    if g is None:
        raise not_found("Gate")
    if caller.gate_id is not None:
        if caller.gate_id != g.id:
            raise forbidden_error("This device is registered to another gate.")
    else:
        p = caller.principal
        assert p is not None  # noqa: S101
        grant = p.grant(g.project_id, C.gate_check)
        if grant is None or (grant.site_ids is not None and g.site_id not in grant.site_ids):
            raise forbidden_error()  # subject scope (GC-13) is checked per scan
    if g.status != GateStatus.active:
        raise validation_error("gate_id", "This gate is inactive.")
    return g


def _target_zone(db: Session, g: Gate, zone_id: uuid.UUID | None) -> Zone | None:
    zones = list(g.protected_zone_ids or [])
    if g.gate_type == GateType.site_gate or not zones:
        return None
    if zone_id is None:
        if len(zones) > 1:
            raise validation_error("zone_id", "Choose the zone: this gate protects several.")
        zone_id = zones[0]
    if zone_id not in zones:
        raise validation_error("zone_id", "This gate does not protect that zone.")
    return db.get(Zone, zone_id)


def _stand_in(g: Gate) -> Zone:
    """Unsaved zone carrying the gate's site for site-gate evaluation (GC-4)."""
    return Zone(
        id=uuid.UUID(int=0),
        project_id=g.project_id,
        site_id=g.site_id,
        code="SITE",
        name_en="Site",
        name_ar="الموقع",
    )


def _resolve(db: Session, g: Gate, body: GateCheckRequest) -> QrToken | None:
    if body.payload:
        m = common.QR_RE.match(body.payload.strip())
        if not m:
            return None
        if m.group(1) == QrKind.TR.value:
            return None  # 2-access-permits v1.3 GC-3: TR is not a gate token kind (CK5-1)
        t = db.scalar(select(QrToken).where(QrToken.token == m.group(2)))
        if t is None or t.kind.value != m.group(1):
            return None
        return t
    if body.printed_ref:
        ref = " ".join(body.printed_ref.split()).upper()
        cands = list(
            db.scalars(
                select(QrToken)
                .where(QrToken.project_id == g.project_id, func.upper(QrToken.printed_ref) == ref)
                .order_by(QrToken.created_at.desc())
            )
        )
        if not cands and "/" in ref:
            head = ref.split("/")[0].strip()
            cands = list(
                db.scalars(
                    select(QrToken)
                    .where(
                        QrToken.project_id == g.project_id,
                        func.upper(QrToken.printed_ref).like(f"{head}%"),
                    )
                    .order_by(QrToken.created_at.desc())
                )
            )
        cands = [t for t in cands if t.kind != QrKind.TR]
        active = [t for t in cands if t.status == QrTokenStatus.active]
        return (active or cands)[0] if (active or cands) else None
    raise validation_error("payload", "Send the QR payload or the printed reference.")


def _log(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    direction: GateDirection,
    kind: GateSubjectKind,
    result: GateResult,
    codes: list[str],
    at: datetime,
    *,
    qr_kind: QrKind | None = None,
    dep: Deployment | None = None,
    vehicle: Vehicle | None = None,
    wap: Wap | None = None,
    ref: str | None = None,
    final: bool = True,
    pairing_id: uuid.UUID | None = None,
    late_exit: bool = False,
    deny_first: str | None = None,
) -> GateCheck:
    row = GateCheck(
        id=uuid.uuid4(),
        occurred_at=at,
        local_date=common.local_day(at),
        project_id=g.project_id,
        site_id=g.site_id,
        gate_id=g.id,
        device_pk=caller.device_pk,
        user_id=caller.user_id,
        direction=direction,
        qr_kind=qr_kind,
        subject_kind=kind,
        worker_id=dep.worker_id if dep else None,
        deployment_id=dep.id if dep else None,
        vehicle_id=vehicle.id if vehicle else None,
        wap_id=wap.id if wap else None,
        engagement_id=(
            dep.engagement_id
            if dep
            else (vehicle.engagement_id if vehicle else (wap.engagement_id if wap else None))
        ),
        subject_ref=ref,
        zone_id=zone.id if zone is not None and zone.id.int != 0 else None,
        result=result,
        reason_codes=codes,
        first_deny_reason=first_deny(codes) if result == R.DENIED else None,
        final=final,
        pairing_id=pairing_id,
        late_exit=late_exit,
    )
    db.add(row)
    db.flush()
    if dep is not None:
        from app.services.med import holds as med_holds  # noqa: PLC0415

        med_holds.detect_gate(db, row)  # 6a FH-8a
    return row


VEHICLE_NO_RE = re.compile(r"^VEH-\d{4,}$")
GC6_ORDER = {c.value: i for i, c in enumerate(GateReasonCode)}
WARN_ONLY = {G.EXPIRING_7D.value, G.HOOK_NOT_AVAILABLE.value, G.LANGUAGE_MISMATCH.value}


def first_deny(codes: list[str]) -> str | None:
    """K-53: a denied check counts once, under its first DENY reason in GC-6 order."""
    deny = [c for c in codes if c not in WARN_ONLY]
    return min(deny, key=lambda c: GC6_ORDER.get(c, 999)) if deny else None


def _zone_ref(db: Session, zone: Zone | None) -> Any:
    if zone is None or zone.id.int == 0:
        return None
    return Refs(db).zone(zone.id)


def _response(
    db: Session,
    row: GateCheck,
    g: Gate,
    zone: Zone | None,
    verdict: Verdict | None,
    **kw: Any,
) -> GateCheckResponse:
    return GateCheckResponse(
        check_id=row.id,
        occurred_at=row.occurred_at,
        gate=_gate_ref(g),
        zone=_zone_ref(db, zone),
        direction=row.direction,
        qr_kind=row.qr_kind,
        subject_kind=row.subject_kind,
        result=row.result,
        reasons=verdict.reasons() if verdict else [gate_reason(G(c)) for c in row.reason_codes],
        late_exit=row.late_exit,
        clear_after_seconds=CLEAR_AFTER,
        **kw,
    )


def _photo_url(db: Session, worker_id: uuid.UUID) -> str | None:
    aid = workers.photo_id(db, worker_id)
    if aid is None:
        return None
    return attachments.raw_signed_url(aid, PHOTO_TTL)


def _person_card(
    db: Session, w: Worker, dep: Deployment | None, ev: eligibility.Evaluation | None, at: datetime
) -> GatePersonCard:
    con = eligibility.contractor_of(db, dep.engagement_id) if dep else None
    lines: list[GateCredentialLine] = []
    if ev is not None:
        for i in ev.items:
            ok = i.status in (RS.met, RS.expiring, RS.warn)
            if i.kind == RequirementKind.induction:
                lines.append(
                    GateCredentialLine(
                        kind="induction",
                        label_en=f"{i.code} induction",
                        label_ar=f"تعريف {i.code}",
                        valid_until=i.valid_until,
                        ok=ok,
                    )
                )
            elif i.kind == RequirementKind.airport_pass:
                ps = ev.pass_
                lines.append(
                    GateCredentialLine(
                        kind="airport_pass",
                        label_en=f"{ps.pass_category} pass {ps.pass_no}"
                        if ps
                        else f"Pass area {i.code}",
                        label_ar=f"تصريح {ps.pass_category}" if ps else f"منطقة التصريح {i.code}",
                        valid_until=i.valid_until,
                        ok=ok,
                        card_colour=ps.card_colour if ps else None,
                        area_codes=list(ps.area_codes or []) if ps else None,
                    )
                )
            elif i.kind == RequirementKind.adp:
                lines.append(
                    GateCredentialLine(
                        kind="adp",
                        label_en=f"ADP {i.ref or ''}".strip(),
                        label_ar="تصريح القيادة",
                        valid_until=i.valid_until,
                        ok=ok,
                        adp_category=AreaCategory(i.code)
                        if i.code and i.code in AreaCategory.__members__
                        else None,
                    )
                )
            elif i.kind == RequirementKind.work_area_permit:
                wap = ev.wap
                label = (
                    windows.today_label(
                        windows.parse(wap.windows),
                        wap.valid_from,
                        wap.valid_to,
                        common.local_day(at),
                    )
                    if wap
                    else None
                )
                lines.append(
                    GateCredentialLine(
                        kind="wap",
                        label_en=i.ref or "WAP",
                        label_ar=i.ref or "تصريح منطقة العمل",
                        valid_until=i.valid_until,
                        ok=ok,
                        window_today=label,
                    )
                )
    return GatePersonCard(
        worker_no=w.worker_no,
        full_name_en=w.full_name_en,
        full_name_ar=w.full_name_ar,
        photo_url=_photo_url(db, w.id),
        employer_short_code=con.short_code if con else None,
        trade=dep.trade if dep else None,
        escort_required=bool(ev and ev.escort_required),
        credentials=lines,
    )


def _avp_live(db: Session, v: Vehicle, d: date) -> list[Avp]:
    return [
        a
        for a in db.scalars(
            select(Avp).where(
                Avp.vehicle_id == v.id,
                Avp.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
            )
        )
        if lifecycle.live_valid(a, d)
    ]


def _vehicle_card(db: Session, v: Vehicle, avp: Avp | None, d: date) -> GateVehicleCard:
    lines = []
    if avp is not None:
        lines.append(
            GateCredentialLine(
                kind="avp",
                label_en=f"AVP {avp.avp_no or ''} ({', '.join(avp.areas or [])})",
                label_ar="تصريح المركبة",
                valid_until=avp.effective_valid_until,
                ok=lifecycle.live_valid(avp, d),
            )
        )
    return GateVehicleCard(
        vehicle_no=v.vehicle_no,
        fleet_no=v.fleet_no,
        category=v.category.value,
        plate_display=common.plate_display(v),
        max_working_height_m_agl=str(common.q2(Decimal(v.max_working_height_m_agl))),
        credentials=lines,
    )


def _ratio(db: Session, zone: Zone | None, project_id: uuid.UUID) -> int:
    s = common.settings(db, project_id)
    if zone is None or zone.id.int == 0:
        return s.escort_ratio_max_other
    prof = profiles.ensure(db, zone)
    return prof.escort_ratio_max or profiles.setting_ratio(s, profiles.area_category(zone))


def active_escorted(db: Session, escort_dep_id: uuid.UUID, day: date) -> int:
    """§6.6: the escort's `in` pairings today − matching `out` scans today."""
    ids = list(
        db.scalars(
            select(GatePairing.id).where(
                GatePairing.escort_deployment_id == escort_dep_id,
                GatePairing.escort_day == day,
                GatePairing.state == PairingState.completed,
                GatePairing.waiting_for == PairingWaitingFor.escort,
            )
        )
    )
    if not ids:
        return 0
    outs = db.scalar(
        select(func.count(GateCheck.id)).where(
            GateCheck.pairing_id.in_(ids),
            GateCheck.direction == GateDirection.out,
            GateCheck.local_date == day,
        )
    )
    return len(ids) - int(outs or 0)


def _late_exit(db: Session, dep: Deployment, zone: Zone | None, at: datetime) -> bool:
    if zone is None or zone.id.int == 0:
        return False
    s = common.settings(db, zone.project_id)
    rows = db.scalars(
        select(Wap)
        .join(WapCrew, WapCrew.wap_id == Wap.id)
        .where(
            WapCrew.worker_id == dep.worker_id,
            Wap.revision_of_id.is_(None),
            Wap.zone_ids.contains([zone.id]),
            Wap.status.in_([WapStatus.active, WapStatus.suspended, WapStatus.closed]),
        )
    ).all()
    if not rows:
        return False
    last: datetime | None = None
    for w in rows:
        defs = windows.parse(w.windows)
        if windows.current(defs, w.valid_from, w.valid_to, at) is not None:
            return False
        e = windows.last_ended(defs, w.valid_from, w.valid_to, at)
        if e is not None and (last is None or e.end_utc > last):
            last = e.end_utc
    return last is not None and at > last + timedelta(minutes=s.wap_exit_grace_minutes)


def _scope_ok(caller: Caller, project_id: uuid.UUID, engagement_id: uuid.UUID | None) -> bool:
    """GC-13: a Contractor HSE Rep only sees subjects in their C scope."""
    if caller.principal is None:
        return True
    g = caller.principal.grant(project_id, C.gate_check)
    return g is not None and (
        g.engagement_ids is None
        or (engagement_id is not None and engagement_id in g.engagement_ids)
    )


def _lost_alert(db: Session, t: QrToken, g: Gate) -> None:
    users = notify.users_with_role(db, Role.hse_officer, [g.project_id])
    notify.notify(
        db,
        users,
        NotificationKind.revoked_token_scanned,
        f"{t.printed_ref}: {'lost' if t.lost else 'revoked'} credential scanned at {g.gate_code}",
        f"{t.printed_ref}: تم مسح بطاقة {'مفقودة' if t.lost else 'ملغاة'} عند {g.gate_code}",
        None,
        None,
        EntityType.gate,
        g.id,
        g.project_id,
    )


# ---- the check (GC-2…GC-13) ----------------------------------------------------------------------


def gate_check(db: Session, caller: Caller, body: GateCheckRequest) -> GateCheckResponse:
    g = _authorise(db, caller, body.gate_id)
    _rate(caller)
    zone = _target_zone(db, g, body.zone_id)
    at = now()
    d = common.local_day(at)
    t = _resolve(db, g, body)
    if t is None and body.printed_ref and body.pairing_id is None:
        v_typed = _typed_vehicle(db, g, body.printed_ref)
        if v_typed is not None:
            live = _avp_live(db, v_typed, d)
            return _vehicle_check(
                db, caller, g, zone, None, body, at, d, v=v_typed, avp=live[0] if live else None
            )
    if t is None:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.unknown,
            R.DENIED,
            [G.TOKEN_UNKNOWN.value],
            at,
        )
        return _response(db, row, g, zone, Verdict(deny=[G.TOKEN_UNKNOWN]))
    if t.kind == QrKind.EQ:
        # v1.2 (4-third-party-cert GE-1…GE-7): Phase 4 native checks in every hook stage
        from app.services.cert import checks as cert_checks  # noqa: PLC0415

        return cert_checks.gate_check(db, caller, g, zone, t, body, at)  # type: ignore[no-any-return]
    if t.project_id != g.project_id:
        # GC-13: a credential of another project is outside this gate's scope; no card.
        kind = GateSubjectKind.vehicle if t.kind == QrKind.VS else GateSubjectKind.person
        if t.kind == QrKind.WP:
            kind = GateSubjectKind.wap
        elif t.kind == QrKind.PT:
            kind = GateSubjectKind.permit
        return _out_of_scope(db, caller, g, zone, body, kind, t, at)
    if body.pairing_id is not None:
        pr = _pairing_for(db, caller, body.pairing_id)
        _expire_if_due(db, pr, at)
        if pr.state == PairingState.waiting:
            return _continue_pairing(db, caller, g, zone, pr, t, body, at)
    if t.status != QrTokenStatus.active:
        dep, veh, wap = _subject(db, t)
        code = G.CREDENTIAL_LOST if t.lost else G.CREDENTIAL_REVOKED
        banned = (
            dep is not None
            and (wk := db.get(Worker, dep.worker_id)) is not None
            and (wk.status == WorkerStatus.banned)
        )
        if not t.lost and banned:
            code = G.WORKER_BANNED  # LC-9 revoked the card; name the cause (GC-6 order)
        elif not t.lost and dep is not None and dep.status != DeploymentStatus.mobilised:
            code = G.WORKER_NOT_DEPLOYED  # AC59: the card died with the deployment
        else:
            _lost_alert(db, t, g)
        kind = (
            GateSubjectKind.person
            if t.kind == QrKind.AC
            else GateSubjectKind.vehicle
            if t.kind == QrKind.VS
            else GateSubjectKind.permit
            if t.kind == QrKind.PT
            else GateSubjectKind.wap
        )
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            kind,
            R.DENIED,
            [code.value],
            at,
            qr_kind=t.kind,
            dep=dep,
            vehicle=veh,
            wap=wap,
            ref=t.printed_ref,
        )
        return _response(db, row, g, zone, Verdict(deny=[code]))
    if t.kind == QrKind.WP:
        return _wap_view(db, caller, g, zone, t, body, at)
    if t.kind == QrKind.PT:
        return _permit_view(db, caller, g, zone, t, body, at)
    if t.kind == QrKind.VS:
        return _vehicle_check(db, caller, g, zone, t, body, at, d)
    return _person_check(db, caller, g, zone, t, body, at)


def _subject(db: Session, t: QrToken) -> tuple[Deployment | None, Vehicle | None, Wap | None]:
    if t.kind == QrKind.PT:
        return None, None, None
    if t.kind == QrKind.AC:
        return db.get(Deployment, t.subject_id), None, None
    if t.kind == QrKind.VS:
        a = db.get(Avp, t.subject_id)
        return None, (db.get(Vehicle, a.vehicle_id) if a else None), None
    return None, None, db.get(Wap, t.subject_id)


def _out_of_scope(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    body: GateCheckRequest,
    kind: GateSubjectKind,
    t: QrToken | None,
    at: datetime,
) -> GateCheckResponse:
    row = _log(
        db,
        caller,
        g,
        zone,
        body.direction,
        kind,
        R.DENIED,
        [G.OUT_OF_SCOPE.value],
        at,
        qr_kind=t.kind if t is not None else None,
    )
    return _response(db, row, g, zone, Verdict(deny=[G.OUT_OF_SCOPE]))


def _evaluate_person(
    db: Session, g: Gate, zone: Zone | None, w: Worker, at: datetime
) -> eligibility.Evaluation:
    if zone is None:
        return eligibility.evaluate(
            db, w, _stand_in(g), at, EligibilityContext.gate, site_only=True
        )
    return eligibility.evaluate(db, w, zone, at, EligibilityContext.gate)


def _person_check(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    t: QrToken,
    body: GateCheckRequest,
    at: datetime,
) -> GateCheckResponse:
    dep = db.get(Deployment, t.subject_id)
    w = db.get(Worker, dep.worker_id) if dep else None
    if dep is None or w is None:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.unknown,
            R.DENIED,
            [G.TOKEN_UNKNOWN.value],
            at,
            qr_kind=t.kind,
        )
        return _response(db, row, g, zone, Verdict(deny=[G.TOKEN_UNKNOWN]))
    if not _scope_ok(caller, g.project_id, dep.engagement_id):
        return _out_of_scope(db, caller, g, zone, body, GateSubjectKind.person, t, at)
    if body.direction == GateDirection.out:
        late = _late_exit(db, dep, zone, at)
        pid = db.scalar(
            select(GateCheck.pairing_id)
            .join(GatePairing, GatePairing.id == GateCheck.pairing_id)
            .where(
                GateCheck.deployment_id == dep.id,
                GateCheck.direction == GateDirection.in_,
                GateCheck.local_date == common.local_day(at),
                GateCheck.final.is_(True),
                GatePairing.waiting_for == PairingWaitingFor.escort,
                GatePairing.state == PairingState.completed,
                GatePairing.escort_deployment_id != dep.id,
            )
            .order_by(GateCheck.occurred_at.desc())
            .limit(1)
        )
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.person,
            R.EXIT_RECORDED,
            [],
            at,
            qr_kind=t.kind,
            dep=dep,
            ref=w.worker_no,
            late_exit=late,
            pairing_id=pid,
        )
        return _response(db, row, g, zone, Verdict(), person=_person_card(db, w, dep, None, at))
    ev = _evaluate_person(db, g, zone, w, at)
    v = Verdict()
    v.merge_items(ev.items)
    if ev.escort_required and not ev.deny_except_escort():
        s = common.settings(db, g.project_id)
        pr = _start_pairing(
            db, caller, g, zone, PairingWaitingFor.escort, at, s.escort_pairing_seconds
        )
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.person,
            R.PENDING_ESCORT,
            [c for c in v.codes() if c != G.ESCORT_REQUIRED.value],
            at,
            qr_kind=t.kind,
            dep=dep,
            ref=w.worker_no,
            final=False,
            pairing_id=pr.id,
        )
        pr.started_check_id = row.id
        pr.subjects = [
            {
                "kind": "person",
                "id": str(dep.id),
                "role": "escorted",
                "check_id": str(row.id),
                "warn": [c.value for c in v.warn],
            }
        ]
        db.flush()
        return _response(
            db,
            row,
            g,
            zone,
            Verdict(warn=v.warn),
            person=_person_card(db, w, dep, ev, at),
            pairing=_pairing_read(pr),
        )
    row = _log(
        db,
        caller,
        g,
        zone,
        body.direction,
        GateSubjectKind.person,
        v.result(),
        v.codes(),
        at,
        qr_kind=t.kind,
        dep=dep,
        ref=w.worker_no,
    )
    return _response(db, row, g, zone, v, person=_person_card(db, w, dep, ev, at))


def _vehicle_verdict(
    db: Session, g: Gate, zone: Zone | None, v: Vehicle, avp: Avp | None, at: datetime, d: date
) -> tuple[Verdict, bool]:
    """GC-9 checks; returns (verdict, needs_escort_vehicle)."""
    verdict = Verdict()
    s = common.settings(db, g.project_id)
    if avp is not None and avp.validity_status == ValidityStatus.suspended:
        verdict.add(G.AVP_SUSPENDED)
    no_avp = avp is None or not lifecycle.live_valid(avp, d)
    if no_avp and (zone is None or profiles.ensure(db, zone).avp_area_required is None):
        verdict.add(G.AVP_MISSING)
    docs = [x for x in (v.istimara_expiry, v.insurance_expiry, v.mvpi_expiry) if x is not None]
    if any(x < d for x in docs) or v.status == VehicleStatus.withdrawn:
        verdict.add(G.VEHICLE_DOC_EXPIRED)
    needs_escort = False
    if zone is not None:
        prof = profiles.ensure(db, zone)
        need = prof.avp_area_required
        if need is not None and (
            no_avp or avp is None or not any(profiles.covers(x, need) for x in avp.areas or [])
        ):
            needs_escort = True  # VP-8
        # VP-7 height
        zmax = zone.max_equipment_height_m_agl
        if zmax is not None:
            wv = _wap_vehicle(db, v.id, zone, at)
            h = (
                wv.height_limited_to_m
                if wv and wv.height_limited_to_m is not None
                else v.max_working_height_m_agl
            )
            if Decimal(h) > Decimal(str(zmax)) and not _height_cleared(db, v, zone, d, wv, h):
                verdict.add(G.HEIGHT_CLEARANCE_REQUIRED)
        # WAP listing
        if prof.access_permit_required:
            rows = db.execute(
                select(Wap, WapVehicle)
                .join(WapVehicle, WapVehicle.wap_id == Wap.id)
                .where(
                    WapVehicle.vehicle_id == v.id,
                    WapVehicle.removed_at.is_(None),
                    Wap.revision_of_id.is_(None),
                    Wap.zone_ids.contains([zone.id]),
                )
            ).all()
            item, _w, _i = eligibility.best_wap(
                rows, at, lambda c: c.status == CrewMemberStatus.excluded
            )
            if item.status == RS.not_met and item.reason:
                verdict.add(G.CREW_EXCLUDED if item.reason == G.CREW_EXCLUDED else item.reason)
    # hooks by vehicle category
    for h in (s.hook_requirements_by_vehicle_category or {}).get(v.category.value, []):
        hctx = hooks.HookContext(
            project_id=s.project_id, zone_id=zone.id if zone else None, vehicle_id=v.id
        )
        it = eligibility.hook_item(
            db, HookSubjectType.vehicle, v.id, HookKind(h["kind"]), h["code"], at, s, hctx
        )
        verdict.merge_items([it])
    return verdict, needs_escort


def _wap_vehicle(db: Session, vehicle_id: uuid.UUID, zone: Zone, at: datetime) -> WapVehicle | None:
    return db.scalar(
        select(WapVehicle)
        .join(Wap, Wap.id == WapVehicle.wap_id)
        .where(
            WapVehicle.vehicle_id == vehicle_id,
            WapVehicle.removed_at.is_(None),
            Wap.status == WapStatus.active,
            Wap.zone_ids.contains([zone.id]),
            Wap.revision_of_id.is_(None),
        )
        .limit(1)
    )


def _height_cleared(
    db: Session, v: Vehicle, zone: Zone, d: date, wv: WapVehicle | None, h: Any
) -> bool:
    if wv is None:
        return False
    w = db.get(Wap, wv.wap_id)
    if w is None:
        return False
    for oid in w.linked_obs_ids or []:
        o = db.get(ObstacleClearance, oid)
        if (
            o is not None
            and o.vehicle_id == v.id
            and o.zone_id == zone.id
            and o.status.value in OBS_OK
            and o.valid_from is not None
            and o.valid_to is not None
            and o.valid_from <= d <= o.valid_to
            and o.approved_max_height_m_agl is not None
            and Decimal(h) <= o.approved_max_height_m_agl
        ):
            return True
    return False


def _typed_vehicle(db: Session, g: Gate, ref: str) -> Vehicle | None:
    """GC-9 / VP-8: a vehicle without an AVP has no sticker; the guard types its vehicle_no."""
    key = " ".join(ref.split()).upper()
    if not VEHICLE_NO_RE.match(key):
        return None
    v = db.scalar(select(Vehicle).where(func.upper(Vehicle.vehicle_no) == key))
    if v is None:
        return None
    on_project = db.scalar(
        select(func.count(ProjectEngagement.id)).where(
            ProjectEngagement.id == v.engagement_id,
            ProjectEngagement.project_id == g.project_id,
        )
    )
    return v if on_project else None


def _vehicle_check(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    t: QrToken | None,
    body: GateCheckRequest,
    at: datetime,
    d: date,
    *,
    v: Vehicle | None = None,
    avp: Avp | None = None,
) -> GateCheckResponse:
    """A sticker scan (t) or a typed vehicle_no (t is None, v given; avp may be None)."""
    if t is not None:
        avp = db.get(Avp, t.subject_id)
        v = db.get(Vehicle, avp.vehicle_id) if avp else None
    qk = t.kind if t is not None else None
    if v is None or (t is not None and avp is None):
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.unknown,
            R.DENIED,
            [G.TOKEN_UNKNOWN.value],
            at,
            qr_kind=qk,
        )
        return _response(db, row, g, zone, Verdict(deny=[G.TOKEN_UNKNOWN]))
    if not _scope_ok(caller, g.project_id, v.engagement_id):
        return _out_of_scope(db, caller, g, zone, body, GateSubjectKind.vehicle, t, at)
    card = _vehicle_card(db, v, avp, d)
    if body.direction == GateDirection.out:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.vehicle,
            R.EXIT_RECORDED,
            [],
            at,
            qr_kind=qk,
            vehicle=v,
            ref=v.vehicle_no,
        )
        return _response(db, row, g, zone, Verdict(), vehicle=card)
    verdict, needs_escort = _vehicle_verdict(db, g, zone, v, avp, at, d)
    if verdict.deny or zone is None:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.vehicle,
            verdict.result() if not (needs_escort and not verdict.deny) else R.DENIED,
            verdict.codes() or [G.AVP_AREA.value],
            at,
            qr_kind=qk,
            vehicle=v,
            ref=v.vehicle_no,
        )
        if not verdict.deny and needs_escort:
            verdict.add(G.AVP_AREA)
        return _response(db, row, g, zone, verdict, vehicle=card)
    s = common.settings(db, g.project_id)
    waiting = PairingWaitingFor.escort_vehicle if needs_escort else PairingWaitingFor.driver
    result = R.PENDING_ESCORT_VEHICLE if needs_escort else R.PENDING_DRIVER
    pr = _start_pairing(db, caller, g, zone, waiting, at, s.escort_pairing_seconds)
    row = _log(
        db,
        caller,
        g,
        zone,
        body.direction,
        GateSubjectKind.vehicle,
        result,
        verdict.codes(),
        at,
        qr_kind=qk,
        vehicle=v,
        ref=v.vehicle_no,
        final=False,
        pairing_id=pr.id,
    )
    pr.started_check_id = row.id
    pr.subjects = [
        {
            "kind": "vehicle",
            "id": str(v.id),
            "role": "vehicle",
            "check_id": str(row.id),
            "warn": [c.value for c in verdict.warn],
        }
    ]
    db.flush()
    return _response(db, row, g, zone, verdict, vehicle=card, pairing=_pairing_read(pr))


def _wap_view(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    t: QrToken,
    body: GateCheckRequest,
    at: datetime,
) -> GateCheckResponse:
    w = db.get(Wap, t.subject_id)
    if w is None:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.unknown,
            R.DENIED,
            [G.TOKEN_UNKNOWN.value],
            at,
            qr_kind=t.kind,
        )
        return _response(db, row, g, zone, Verdict(deny=[G.TOKEN_UNKNOWN]))
    if not _scope_ok(caller, g.project_id, w.engagement_id):
        return _out_of_scope(db, caller, g, zone, body, GateSubjectKind.wap, t, at)
    defs = windows.parse(w.windows)
    crew = []
    for c in waps.crew_rows(db, w):
        wk = db.get(Worker, c.worker_id)
        if wk is None:
            continue
        crew.append(
            GateWapCrewLine(
                worker_no=wk.worker_no,
                full_name_en=wk.full_name_en,
                full_name_ar=wk.full_name_ar,
                crew_role=c.crew_role.value,
                eligible_now=bool(c.eligible_now) and c.status == CrewMemberStatus.included,
                reasons=[G(x) for x in c.exclusion_reasons or []],
            )
        )
    vehicles = [
        vv.vehicle_no
        for vv in (db.get(Vehicle, r.vehicle_id) for r in waps.vehicle_rows(db, w))
        if vv
    ]
    card = GateWapCard(
        wap_no=w.wap_no,
        status=w.status,
        in_window_now=windows.current(defs, w.valid_from, w.valid_to, at) is not None,
        window_today=windows.today_label(defs, w.valid_from, w.valid_to, common.local_day(at)),
        blockers=[WapBlocker(b["code"]) for b in waps.compute_blockers(db, w, at)],
        crew=crew,
        vehicles=vehicles,
    )
    row = _log(
        db,
        caller,
        g,
        zone,
        body.direction,
        GateSubjectKind.wap,
        R.WAP_VIEW,
        [],
        at,
        qr_kind=t.kind,
        wap=w,
        ref=w.wap_no,
        final=False,
    )
    return _response(db, row, g, zone, Verdict(), wap=card)


def _permit_view(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    t: QrToken,
    body: GateCheckRequest,
    at: datetime,
) -> GateCheckResponse:
    """v1.1 GC-10 for `PT` tokens: read-only permit summary; logs `ptw_view`, records no
    individual's entry. Crew names need capability 46 (a signed-in caller without it sees an
    empty crew list; gate devices see the crew as on the WAP card)."""
    from app.core.ptw_enums import CrewLineStatus, PermitBlocker, PermitType  # noqa: PLC0415
    from app.models import Permit  # noqa: PLC0415
    from app.services.ptw import common as ptw_common  # noqa: PLC0415
    from app.services.ptw import evaluation as ptw_eval  # noqa: PLC0415
    from app.services.ptw import facts as ptw_facts  # noqa: PLC0415
    from app.services.ptw import views as ptw_views  # noqa: PLC0415
    from app.services.ptw.board import _window_today  # noqa: PLC0415

    permit = db.get(Permit, t.subject_id)
    if permit is None:
        row = _log(
            db,
            caller,
            g,
            zone,
            body.direction,
            GateSubjectKind.unknown,
            R.DENIED,
            [G.TOKEN_UNKNOWN.value],
            at,
            qr_kind=t.kind,
        )
        return _response(db, row, g, zone, Verdict(deny=[G.TOKEN_UNKNOWN]))
    if not _scope_ok(caller, g.project_id, permit.engagement_id):
        return _out_of_scope(db, caller, g, zone, body, GateSubjectKind.permit, t, at)
    names = caller.principal is None or (
        caller.principal.grant(permit.project_id, C.worker_view) is not None
    )
    crew = []
    if names:
        for line in ptw_eval.crew_lines(db, permit.id):
            wk = db.get(Worker, line.worker_id)
            if wk is None:
                continue
            crew.append(
                GateWapCrewLine(
                    worker_no=wk.worker_no,
                    full_name_en=wk.full_name_en,
                    full_name_ar=wk.full_name_ar,
                    crew_role=line.crew_role.value,
                    eligible_now=line.status == CrewLineStatus.listed,
                    reasons=[],
                )
            )
    shift = ptw_eval.current_shift(db, permit)
    f = ptw_facts.compute(db, permit)
    card = GatePermitCard(
        permit_no=permit.permit_no,
        display_no=ptw_common.display_no(permit),
        status=permit.status,
        work_types=[PermitType(x) for x in permit.work_types],
        in_window_now=ptw_common.current_instance(permit, at) is not None,
        window_today=_window_today(permit, at),
        valid_to_at=permit.valid_to_at,
        current_shift_no=shift.shift_no if shift else None,
        blockers=[PermitBlocker(b["code"]) for b in permit.blockers or []],
        crew=crew,
        gas_status=ptw_views.gas_state(db, permit, f, at).status,
    )
    row = _log(
        db,
        caller,
        g,
        zone,
        body.direction,
        GateSubjectKind.permit,
        R.PTW_VIEW,
        [],
        at,
        qr_kind=t.kind,
        ref=permit.permit_no,
        final=False,
    )
    return _response(db, row, g, zone, Verdict(), permit=card)


# ---- pairing (GC-8, GC-9) ------------------------------------------------------------------------


def _start_pairing(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    waiting: PairingWaitingFor,
    at: datetime,
    seconds: int,
) -> GatePairing:
    pr = GatePairing(
        id=uuid.uuid4(),
        project_id=g.project_id,
        gate_id=g.id,
        zone_id=zone.id if zone is not None and zone.id.int != 0 else None,
        device_pk=caller.device_pk,
        user_id=caller.user_id,
        waiting_for=waiting,
        state=PairingState.waiting,
        started_check_id=uuid.UUID(int=0),
        subjects=[],
        started_at=at,
        expires_at=at + timedelta(seconds=seconds),
    )
    db.add(pr)
    db.flush()
    return pr


def _pairing_read(pr: GatePairing) -> GatePairingRead:
    return GatePairingRead(
        pairing_id=pr.id,
        waiting_for=pr.waiting_for,
        state=pr.state,
        expires_at=pr.expires_at,
        started_check_id=pr.started_check_id,
    )


def _pairing_for(db: Session, caller: Caller, pairing_id: uuid.UUID) -> GatePairing:
    pr = db.get(GatePairing, pairing_id)
    if pr is None:
        raise not_found("Pairing")
    same = pr.device_pk == caller.device_pk if caller.device_pk else pr.user_id == caller.user_id
    if not same:
        raise forbidden_error("Pairings continue only on the device that started them.")
    return pr


TIMEOUT_REASON = {
    PairingWaitingFor.escort: G.ESCORT_REQUIRED,
    PairingWaitingFor.driver: G.ADP_MISSING,
    PairingWaitingFor.escort_vehicle: G.AVP_AREA,
}


def _final_rows(
    db: Session,
    pr: GatePairing,
    result: GateResult,
    extra: dict[str, list[GateReasonCode]],
    at: datetime,
    roles: set[str] | None = None,
) -> list[GateCheck]:
    """Write the final log row for each collected subject of the pairing."""
    g = db.get(Gate, pr.gate_id)
    assert g is not None  # noqa: S101
    zone = db.get(Zone, pr.zone_id) if pr.zone_id else None
    caller = Caller(
        GateCallerKind.device if pr.device_pk else GateCallerKind.user, None, pr.device_pk, None
    )
    out = []
    started = db.get(GateCheck, pr.started_check_id)
    # copy first: mutating the loaded JSONB dicts in place hides the change from the ORM
    subjects = [dict(x) for x in pr.subjects or []]
    for sub in subjects:
        if roles is not None and sub["role"] not in roles:
            continue
        if sub.get("final_check_id"):
            continue
        warn = [G(x) for x in sub.get("warn", [])]
        deny = extra.get(sub["role"], [])
        res = result
        if res != R.DENIED and warn:
            res = R.GRANTED_WITH_WARNING
        codes = (
            [c.value for c in deny] + [c.value for c in warn]
            if res == R.DENIED
            else [c.value for c in warn]
        )
        dep = db.get(Deployment, uuid.UUID(sub["id"])) if sub["kind"] == "person" else None
        veh = db.get(Vehicle, uuid.UUID(sub["id"])) if sub["kind"] == "vehicle" else None
        wk = db.get(Worker, dep.worker_id) if dep else None
        row = _log(
            db,
            caller,
            g,
            zone,
            GateDirection.in_,
            GateSubjectKind.person if dep else GateSubjectKind.vehicle,
            res,
            codes,
            at,
            qr_kind=QrKind.AC if dep else QrKind.VS,
            dep=dep,
            vehicle=veh,
            ref=wk.worker_no if wk else (veh.vehicle_no if veh else None),
            pairing_id=pr.id,
            deny_first=codes[0] if res == R.DENIED and codes else None,
        )
        row.user_id = started.user_id if started else pr.user_id
        sub["final_check_id"] = str(row.id)
        out.append(row)
    pr.subjects = subjects
    db.flush()
    return out


def _close_pairing(db: Session, pr: GatePairing, state: PairingState, at: datetime) -> None:
    reason = TIMEOUT_REASON[pr.waiting_for]
    pr.state = state
    pr.ended_at = at
    _final_rows(
        db,
        pr,
        R.DENIED,
        {"escorted": [reason], "vehicle": [reason], "escort_vehicle": [reason]},
        at,
    )


def _expire_if_due(db: Session, pr: GatePairing, at: datetime) -> None:
    if pr.state == PairingState.waiting and pr.expires_at <= at:
        _close_pairing(db, pr, PairingState.timed_out, pr.expires_at)


def pairing_timeout_job(db: Session, at: datetime | None = None) -> int:
    """Coordinator decision: close timed-out pairings and write the started subject's DENIED
    row at timeout (GC-8)."""
    at = at or now()
    n = 0
    for pr in db.scalars(
        select(GatePairing).where(
            GatePairing.state == PairingState.waiting, GatePairing.expires_at <= at
        )
    ):
        _close_pairing(db, pr, PairingState.timed_out, pr.expires_at)
        n += 1
    return n


def _paired_results(db: Session, pr: GatePairing) -> list[GatePairedResult]:
    out = []
    for sub in pr.subjects or []:
        cid = sub.get("final_check_id")
        if not cid:
            continue
        row = db.get(GateCheck, uuid.UUID(cid))
        if row is None:
            continue
        out.append(
            GatePairedResult(
                check_id=row.id,
                subject_kind=row.subject_kind,
                display_ref=row.subject_ref or "",
                result=row.result,
                reasons=[gate_reason(G(c), G(c) not in _deny_set(row)) for c in row.reason_codes],
            )
        )
    return out


def _deny_set(row: GateCheck) -> set[GateReasonCode]:
    if row.result != R.DENIED:
        return set()
    return {
        G(c)
        for c in row.reason_codes
        if G(c) not in (G.EXPIRING_7D, G.HOOK_NOT_AVAILABLE, G.LANGUAGE_MISMATCH)
    }


def read_pairing(db: Session, caller: Caller, pairing_id: uuid.UUID) -> PairingRead:
    pr = _pairing_for(db, caller, pairing_id)
    _expire_if_due(db, pr, now())
    return PairingRead(pairing=_pairing_read(pr), results=_paired_results(db, pr))


def cancel_pairing(db: Session, caller: Caller, pairing_id: uuid.UUID) -> PairingRead:
    pr = _pairing_for(db, caller, pairing_id)
    at = now()
    _expire_if_due(db, pr, at)
    if pr.state != PairingState.waiting:
        raise invalid_transition("Pairing", pr.state, PairingState.cancelled)
    _close_pairing(db, pr, PairingState.cancelled, at)
    return PairingRead(pairing=_pairing_read(pr), results=_paired_results(db, pr))


def _continue_pairing(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    pr: GatePairing,
    t: QrToken,
    body: GateCheckRequest,
    at: datetime,
) -> GateCheckResponse:
    if pr.gate_id != g.id:
        raise validation_error("pairing_id", "The pairing was started at another gate.")
    d = common.local_day(at)
    if t.status != QrTokenStatus.active:
        code = G.CREDENTIAL_LOST if t.lost else G.CREDENTIAL_REVOKED
        _lost_alert(db, t, g)
        return _pair_fail(
            db,
            caller,
            g,
            zone,
            pr,
            t,
            at,
            [code],
            G.ESCORT_INVALID
            if pr.waiting_for == PairingWaitingFor.escort
            else TIMEOUT_REASON[pr.waiting_for],
        )
    if pr.waiting_for == PairingWaitingFor.escort:
        if t.kind != QrKind.AC:
            raise validation_error("payload", "Scan the escort's access card.")
        dep = db.get(Deployment, t.subject_id)
        w = db.get(Worker, dep.worker_id) if dep else None
        if dep is None or w is None:
            return _pair_fail(db, caller, g, zone, pr, t, at, [G.TOKEN_UNKNOWN], G.ESCORT_INVALID)
        if any(s["id"] == str(dep.id) for s in pr.subjects or []):
            raise validation_error("payload", "The escort must be another person.")
        ev = _evaluate_person(db, g, zone, w, at)
        v = Verdict()
        v.merge_items(ev.items)
        own = list(v.deny)
        pair_reason: GateReasonCode | None = None
        if ev.escort_required or (ev.pass_ is not None and ev.pass_.escorted):
            pair_reason = G.ESCORT_INVALID
        if zone is not None and profiles.area_category(zone) == AreaCategory.manoeuvring:
            it, adp = eligibility.adp_item(
                db, w.id, g.project_id, AreaCategory.manoeuvring.value, d
            )
            if adp is None:
                pair_reason = G.ESCORT_INVALID
        if own:
            pair_reason = pair_reason or G.ESCORT_INVALID
        if pair_reason is None and active_escorted(db, dep.id, d) >= _ratio(db, zone, g.project_id):
            pair_reason = G.ESCORT_RATIO_EXCEEDED
        card = _person_card(db, w, dep, ev, at)
        if pair_reason is not None:
            return _pair_fail(
                db,
                caller,
                g,
                zone,
                pr,
                t,
                at,
                [*own, pair_reason],
                pair_reason,
                dep=dep,
                person=card,
                ref=w.worker_no,
            )
        row = _log(
            db,
            caller,
            g,
            zone,
            GateDirection.in_,
            GateSubjectKind.person,
            v.result(),
            v.codes(),
            at,
            qr_kind=t.kind,
            dep=dep,
            ref=w.worker_no,
            pairing_id=pr.id,
        )
        pr.subjects = [
            *(pr.subjects or []),
            {
                "kind": "person",
                "id": str(dep.id),
                "role": "escort",
                "check_id": str(row.id),
                "final_check_id": str(row.id),
            },
        ]
        pr.escort_deployment_id = dep.id
        pr.escort_day = d
        pr.state = PairingState.completed
        pr.ended_at = at
        _final_rows(db, pr, R.GRANTED, {}, at)
        return _response(
            db,
            row,
            g,
            zone,
            v,
            person=card,
            pairing=_pairing_read(pr),
            paired_results=_paired_results(db, pr),
        )
    if pr.waiting_for == PairingWaitingFor.escort_vehicle:
        if t.kind != QrKind.VS:
            raise validation_error("payload", "Scan the escort vehicle's sticker.")
        avp = db.get(Avp, t.subject_id)
        ev_v = db.get(Vehicle, avp.vehicle_id) if avp else None
        if avp is None or ev_v is None or zone is None:
            return _pair_fail(db, caller, g, zone, pr, t, at, [G.TOKEN_UNKNOWN], G.AVP_AREA)
        verdict, needs = _vehicle_verdict(db, g, zone, ev_v, avp, at, d)
        if needs:
            verdict.add(G.AVP_AREA)
        s = common.settings(db, g.project_id)
        ratio = (
            s.vehicle_escort_ratio_max_manoeuvring
            if profiles.area_category(zone) == AreaCategory.manoeuvring
            else s.vehicle_escort_ratio_max_apron
        )
        count = db.scalar(
            select(func.count(GatePairing.id)).where(
                GatePairing.escort_vehicle_id == ev_v.id,
                GatePairing.escort_day == d,
                GatePairing.state.in_([PairingState.completed, PairingState.waiting]),
            )
        )
        if not verdict.deny and int(count or 0) >= ratio:
            verdict.add(G.ESCORT_RATIO_EXCEEDED)
        vcard_ = _vehicle_card(db, ev_v, avp, d)
        if verdict.deny:
            return _pair_fail(
                db,
                caller,
                g,
                zone,
                pr,
                t,
                at,
                verdict.deny,
                G.AVP_AREA,
                vehicle=ev_v,
                vcard=vcard_,
                ref=ev_v.vehicle_no,
            )
        row = _log(
            db,
            caller,
            g,
            zone,
            GateDirection.in_,
            GateSubjectKind.vehicle,
            R.PENDING_DRIVER,
            verdict.codes(),
            at,
            qr_kind=t.kind,
            vehicle=ev_v,
            ref=ev_v.vehicle_no,
            final=False,
            pairing_id=pr.id,
        )
        pr.subjects = [
            *(pr.subjects or []),
            {
                "kind": "vehicle",
                "id": str(ev_v.id),
                "role": "escort_vehicle",
                "check_id": str(row.id),
                "warn": [c.value for c in verdict.warn],
            },
        ]
        pr.escort_vehicle_id = ev_v.id
        pr.escort_day = d
        pr.waiting_for = PairingWaitingFor.driver
        pr.expires_at = at + timedelta(seconds=s.escort_pairing_seconds)
        db.flush()
        return _response(db, row, g, zone, verdict, vehicle=vcard_, pairing=_pairing_read(pr))
    # driver
    if t.kind != QrKind.AC:
        raise validation_error("payload", "Scan the driver's access card.")
    dep = db.get(Deployment, t.subject_id)
    w = db.get(Worker, dep.worker_id) if dep else None
    if dep is None or w is None or zone is None:
        return _pair_fail(db, caller, g, zone, pr, t, at, [G.TOKEN_UNKNOWN], G.ADP_MISSING)
    ev = _evaluate_person(db, g, zone, w, at)
    v = Verdict()
    v.merge_items(ev.items)
    need = profiles.ensure(db, zone).adp_category_required
    if need is not None:
        it, _adp = eligibility.adp_item(db, w.id, g.project_id, need.value, d)
        if it.status == RS.not_met and it.reason:
            v.add(it.reason)
    card = _person_card(db, w, dep, ev, at)
    if v.deny:
        reason = next(
            (c for c in v.deny if c in (G.ADP_MISSING, G.ADP_CATEGORY, G.ADP_SUSPENDED)), v.deny[0]
        )
        return _pair_fail(
            db, caller, g, zone, pr, t, at, v.deny, reason, dep=dep, person=card, ref=w.worker_no
        )
    row = _log(
        db,
        caller,
        g,
        zone,
        GateDirection.in_,
        GateSubjectKind.person,
        v.result(),
        v.codes(),
        at,
        qr_kind=t.kind,
        dep=dep,
        ref=w.worker_no,
        pairing_id=pr.id,
    )
    pr.subjects = [
        *(pr.subjects or []),
        {
            "kind": "person",
            "id": str(dep.id),
            "role": "driver",
            "check_id": str(row.id),
            "final_check_id": str(row.id),
        },
    ]
    pr.state = PairingState.completed
    pr.ended_at = at
    _final_rows(db, pr, R.GRANTED, {}, at)
    return _response(
        db,
        row,
        g,
        zone,
        v,
        person=card,
        pairing=_pairing_read(pr),
        paired_results=_paired_results(db, pr),
    )


def _pair_fail(
    db: Session,
    caller: Caller,
    g: Gate,
    zone: Zone | None,
    pr: GatePairing,
    t: QrToken,
    at: datetime,
    own: list[GateReasonCode],
    pair_reason: GateReasonCode,
    *,
    dep: Deployment | None = None,
    vehicle: Vehicle | None = None,
    person: GatePersonCard | None = None,
    vcard: GateVehicleCard | None = None,
    ref: str | None = None,
) -> GateCheckResponse:
    """Both DENIED (GC-8): the scanned subject with its own reasons, the started subjects with
    the pairing reason."""
    v = Verdict(deny=list(dict.fromkeys(own)))
    kind = (
        GateSubjectKind.person
        if dep
        else GateSubjectKind.vehicle
        if vehicle
        else GateSubjectKind.unknown
    )
    row = _log(
        db,
        caller,
        g,
        zone,
        GateDirection.in_,
        kind,
        R.DENIED,
        [c.value for c in v.deny],
        at,
        qr_kind=t.kind,
        dep=dep,
        vehicle=vehicle,
        ref=ref,
        pairing_id=pr.id,
    )
    pr.state = PairingState.completed
    pr.ended_at = at
    _final_rows(
        db,
        pr,
        R.DENIED,
        {"escorted": [pair_reason], "vehicle": [pair_reason], "escort_vehicle": [pair_reason]},
        at,
    )
    return _response(
        db,
        row,
        g,
        zone,
        v,
        person=person,
        vehicle=vcard,
        pairing=_pairing_read(pr),
        paired_results=_paired_results(db, pr),
    )


# ---- admitted despite denial (GC-14) and the log -------------------------------------------------


def log_entry(
    db: Session,
    p: Principal | None,
    row: GateCheck,
    refs: Refs | None = None,
    names: bool | None = None,
) -> GateLogEntry:
    refs = refs or Refs(db)
    g = db.get(Gate, row.gate_id)
    dev = db.get(GateDevice, row.device_pk) if row.device_pk else None
    show = names if names is not None else common.can_see_names(p, row.project_id)
    wk = db.get(Worker, row.worker_id) if (row.worker_id and show) else None
    return GateLogEntry(
        id=row.id,
        occurred_at=row.occurred_at,
        gate_id=row.gate_id,
        gate_code=g.gate_code if g else "",
        device_id=dev.device_id if dev else None,
        user=refs.user(row.user_id),
        direction=row.direction,
        subject_kind=row.subject_kind,
        subject_ref=row.subject_ref,
        subject_name_en=wk.full_name_en if wk else None,
        subject_name_ar=wk.full_name_ar if wk else None,
        zone=refs.zone(row.zone_id),
        result=row.result,
        reason_codes=[G(c) for c in row.reason_codes or []],
        pairing_id=row.pairing_id,
        late_exit=row.late_exit,
        admitted_despite_denial=row.admitted_despite_denial,
        admitted_reason=row.admitted_reason,
        admitted_by=refs.user(row.admitted_by_user_id),
    )


def admitted_despite_denial(
    db: Session, caller: Caller, check_id: uuid.UUID, body: AdmittedDespiteDenialRequest
) -> GateLogEntry:
    row = db.get(GateCheck, check_id)
    if row is None:
        raise not_found("Gate check")
    _authorise(db, caller, row.gate_id)
    if row.result != R.DENIED or not row.final:
        raise invalid_transition("Gate check", row.result, "admitted_despite_denial")
    if row.admitted_despite_denial:
        raise invalid_transition("Gate check", "admitted_despite_denial", "admitted_despite_denial")
    at = now()
    row.admitted_despite_denial = True
    row.admitted_reason = common.reason_text(body.reason)
    row.admitted_by_user_id = caller.user_id
    row.admitted_at = at
    db.flush()
    from app.services.med import holds as med_holds  # noqa: PLC0415

    med_holds.detect_gate(db, row)  # 6a FH-8a
    actor = caller.principal.actor(row.project_id) if caller.principal else None
    audit.record(
        db,
        AuditAction.update,
        *([actor] if actor else []),
        entity_type=EntityType.gate,
        entity_id=row.gate_id,
        project_id=row.project_id,
        after={
            "check_id": str(row.id),
            "admitted_despite_denial": True,
            "reason": row.admitted_reason,
        },
    )
    users = set(notify.users_with_role(db, Role.hse_officer, [row.project_id])) | set(
        notify.managers(db)
    )
    g = db.get(Gate, row.gate_id)
    notify.notify(
        db,
        users,
        NotificationKind.admitted_despite_denial,
        f"{row.subject_ref or 'Subject'} admitted despite denial at {g.gate_code if g else ''}",
        f"تم إدخال {row.subject_ref or ''} رغم الرفض",
        row.admitted_reason,
        row.admitted_reason,
        EntityType.gate,
        row.gate_id,
        row.project_id,
    )
    return log_entry(db, caller.principal, row, names=False)


def list_log(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    gate_ids: list[uuid.UUID] | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    direction: GateDirection | None = None,
    results: list[GateResult] | None = None,
    reason_codes: list[GateReasonCode] | None = None,
    subject_kind: GateSubjectKind | None = None,
    worker_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    admitted: bool | None = None,
    late_exit: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> GateLogPage:
    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, C.gate_log_view)
    if g is None:
        raise forbidden_error()
    stmt = select(GateCheck).where(GateCheck.project_id == project_id)
    if g.engagement_ids is not None:
        stmt = stmt.where(GateCheck.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        stmt = stmt.where(GateCheck.site_id.in_(list(g.site_ids)))
    if gate_ids:
        stmt = stmt.where(GateCheck.gate_id.in_(gate_ids))
    if zone_ids:
        stmt = stmt.where(GateCheck.zone_id.in_(zone_ids))
    if direction:
        stmt = stmt.where(GateCheck.direction == direction)
    if results:
        stmt = stmt.where(GateCheck.result.in_(results))
    if reason_codes:
        stmt = stmt.where(GateCheck.reason_codes.overlap([c.value for c in reason_codes]))
    if subject_kind:
        stmt = stmt.where(GateCheck.subject_kind == subject_kind)
    if worker_id:
        stmt = stmt.where(GateCheck.worker_id == worker_id)
    if vehicle_id:
        stmt = stmt.where(GateCheck.vehicle_id == vehicle_id)
    if engagement_ids:
        stmt = stmt.where(GateCheck.engagement_id.in_(engagement_ids))
    if admitted is not None:
        stmt = stmt.where(GateCheck.admitted_despite_denial.is_(admitted))
    if late_exit is not None:
        stmt = stmt.where(GateCheck.late_exit.is_(late_exit))
    if since:
        stmt = stmt.where(GateCheck.occurred_at >= since)
    if until:
        stmt = stmt.where(GateCheck.occurred_at < until)
    rows, total = paginate(db, stmt.order_by(GateCheck.occurred_at.desc()), page, page_size)
    refs = Refs(db).load(
        zones=[r.zone_id for r in rows if r.zone_id],
        users=[u for r in rows for u in (r.user_id, r.admitted_by_user_id) if u],
    )
    names = common.can_see_names(p, project_id)
    return GateLogPage(
        items=[log_entry(db, p, r, refs, names) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def purge_log(db: Session, at: datetime | None = None) -> int:
    """P2-6: delete gate-log rows older than gate_log_retention_months (per project), except
    rows linked to a Phase 1 incident (they follow the incident's retention)."""
    at = at or now()
    n = 0
    for s in db.scalars(select(AccessSettings)):
        cutoff = common.local_midnight_utc(
            add_months(common.local_day(at), -int(s.gate_log_retention_months))
        )
        rows = list(
            db.scalars(
                select(GateCheck).where(
                    GateCheck.project_id == s.project_id,
                    GateCheck.occurred_at < cutoff,
                    GateCheck.incident_id.is_(None),  # P2-6: incident-linked rows kept
                )
            )
        )
        for r in rows:
            db.delete(r)
        n += len(rows)
    db.flush()
    return n
