"""Helpers shared by the Phase 3 PTW services (spec 3-ptw): settings and zone profiles with their
defaults, step-up re-authentication and signatures (PT-15), permit refs, clipped work windows
(§6.5), appointment lookups (PR-2…PR-4), error builders and notifications."""

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind, Role, ZoneType
from app.core.errors import ApiError, ErrorCode, field_error
from app.core.ptw_enums import (
    PERMIT_TYPE_LETTERS,
    AppointmentFunction,
    AppointmentStatus,
    Exposure,
    HazardousAreaClass,
    PermitBlocker,
    PermitType,
    PermitWarningCode,
    SignaturePurpose,
)
from app.models import (
    Permit,
    PermitSignature,
    Project,
    PtwAppointment,
    PtwSettings,
    User,
    Zone,
    ZonePtwProfile,
)
from app.schemas.ptw_common import (
    BlockerItem,
    PermitRef,
    PermitWindowRead,
    WarningItem,
    WindowInstance,
)
from app.services import notify
from app.services.access import common as acommon
from app.services.access import windows
from app.services.hse_common import contractor_reps
from app.services.permissions import Principal
from app.services.ptw import reference as ref
from app.services.ptw.rules import ZoneFacts

# ---- settings / profiles -------------------------------------------------------------------------

JSON_DEFAULTS: dict[str, Any] = {
    "type_max_duration_days": ref.TYPE_MAX_DAYS_DEFAULT,
    "gas_retest_interval_minutes": ref.GAS_RETEST_DEFAULT,
    "gas_limits": ref.GAS_LIMITS_DEFAULT,
    "midday_ban_period": ref.MIDDAY_PERIOD_DEFAULT,
    "midday_ban_hours": ref.MIDDAY_HOURS_DEFAULT,
}


def settings(db: Session, project_id: uuid.UUID) -> PtwSettings:
    """§3.17 row of the project (created with the defaults on first use)."""
    s = db.get(PtwSettings, project_id)
    if s is None:
        s = PtwSettings(project_id=project_id)
        for col in PtwSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                setattr(s, col.key, arg(None) if callable(arg) else arg)
        db.add(s)
    for k, v in JSON_DEFAULTS.items():
        if not getattr(s, k):
            setattr(s, k, json.loads(json.dumps(v)))
    db.flush()
    return s


def profile_defaults(zone: Zone) -> dict[str, Any]:
    """PT-3."""
    airside = zone.zone_type == ZoneType.airside
    return {
        "permit_required_all_work": bool(airside and zone.in_movement_area),
        "gas_test_zone": False,
        "hazardous_area_class": HazardousAreaClass.none,
        "default_exposure": Exposure.outdoor_direct_sun if airside else Exposure.indoor,
        "fire_protection_present": False,
    }


def profile(db: Session, zone: Zone) -> ZonePtwProfile:
    p = db.get(ZonePtwProfile, zone.id)
    if p is None:
        p = ZonePtwProfile(
            zone_id=zone.id,
            project_id=zone.project_id,
            default_area_authority_ids=[],
            **profile_defaults(zone),
        )
        db.add(p)
        db.flush()
    return p


def zone_facts(db: Session, zones: Iterable[Zone]) -> list[ZoneFacts]:
    out = []
    for z in zones:
        p = profile(db, z)
        out.append(
            ZoneFacts(
                id=z.id,
                code=z.code,
                airside=z.zone_type == ZoneType.airside,
                in_movement_area=bool(z.in_movement_area),
                gas_test_zone=p.gas_test_zone,
                hazardous=p.hazardous_area_class,
                fod_control_required=bool(z.fod_control_required),
                max_equipment_height_m=(
                    None
                    if z.max_equipment_height_m_agl is None
                    else acommon.q2(_dec(z.max_equipment_height_m_agl))
                ),
            )
        )
    return out


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


def permit_zones(db: Session, permit: Permit) -> list[Zone]:
    zs = {z.id: z for z in db.scalars(select(Zone).where(Zone.id.in_(permit.zone_ids or [])))}
    return [zs[i] for i in permit.zone_ids if i in zs]


# ---- errors --------------------------------------------------------------------------------------


def err(
    code: ErrorCode,
    en: str,
    ar: str,
    status: int = 422,
    field: str | None = None,
    meta: dict[str, Any] | None = None,
) -> ApiError:
    errors = [field_error(field, en, code.value, ar)] if field else None
    return ApiError(status, code, en, ar, errors=errors, meta=meta)


def blocker_item(code: PermitBlocker, detail: str | None = None, ref_: str | None = None) -> Any:
    en, ar = ref.BLOCKER_TEXT[code]
    if detail:
        en = f"{en}: {detail}"
        ar = f"{ar}: {detail}"
    return BlockerItem(
        code=code, detail_en=en, detail_ar=ar, ref=ref_, issue_time=code not in ref.APPROVE_TIME
    )


def blocker_json(code: PermitBlocker, detail: str | None = None, ref_: str | None = None) -> Any:
    return {"code": code.value, "detail": detail, "ref": ref_}


_WORKER_NO = re.compile(r"WKR-\d{6}")


def _mask(text: str | None, names: bool) -> str | None:
    """P3-1: without name visibility (Viewer), worker numbers in blocker/warning text are hidden."""
    if text is None or names:
        return text
    return _WORKER_NO.sub("worker", text)


def blocker_reads(rows: Sequence[dict[str, Any]], names: bool = True) -> list[BlockerItem]:
    out = [
        blocker_item(
            PermitBlocker(b["code"]), _mask(b.get("detail"), names), _mask(b.get("ref"), names)
        )
        for b in rows
    ]
    return sorted(out, key=lambda b: ref.BLOCKER_ORDER[b.code])


def warning_reads(rows: Sequence[dict[str, Any]], names: bool = True) -> list[WarningItem]:
    out = []
    for w in rows:
        code = PermitWarningCode(w["code"])
        en, ar = ref.WARNING_TEXT[code]
        detail = _mask(w.get("detail"), names)
        if detail:
            en, ar = f"{en}: {detail}", f"{ar}: {detail}"
        out.append(
            WarningItem(code=code, detail_en=en, detail_ar=ar, ref=_mask(w.get("ref"), names))
        )
    return out


def blocked_error(rows: Sequence[dict[str, Any]]) -> ApiError:
    """DECISIONS #57: 422, code = the first blocker in list B order, meta.blockers = all."""
    items = blocker_reads(rows)
    first = items[0]
    return ApiError(
        422,
        ErrorCode(first.code.value),
        first.detail_en,
        first.detail_ar,
        meta={"blockers": [b.model_dump(mode="json") for b in items]},
    )


# ---- PT-15 signatures ----------------------------------------------------------------------------


def require_reauth(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    minutes = settings(db, project_id).step_up_reauth_minutes
    last = p.session.last_authenticated_at if p.session else None
    if last is None or now() - last > timedelta(minutes=minutes):
        raise ApiError(
            401,
            ErrorCode.REAUTH_REQUIRED,
            f"Re-enter your password: signing needs authentication within {minutes} min.",
            f"أعد إدخال كلمة المرور: التوقيع يتطلب التحقق خلال {minutes} دقيقة.",
            meta={"reauth_minutes": minutes},
        )


def permit_hash(permit: Permit, extra: dict[str, Any] | None = None) -> str:
    body = {
        "permit_no": permit.permit_no,
        "status": permit.status.value,
        "work_types": list(permit.work_types or []),
        "zones": [str(z) for z in permit.zone_ids or []],
        "valid_from_at": permit.valid_from_at.isoformat(),
        "valid_to_at": permit.valid_to_at.isoformat(),
        "windows": permit.windows,
        "sections": permit.sections,
        "conditions": [permit.conditions_en, permit.conditions_ar],
        "extra": extra or {},
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def sign(
    db: Session,
    permit: Permit | None,
    purpose: SignaturePurpose,
    role_label: str,
    *,
    user_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    co_device: uuid.UUID | None = None,
    at: datetime | None = None,
    hash_: str | None = None,
) -> PermitSignature:
    s = PermitSignature(
        id=uuid.uuid4(),
        permit_id=permit.id if permit else None,
        entity_id=entity_id,
        purpose=purpose,
        user_id=user_id,
        worker_id=worker_id,
        role_label=role_label,
        appointment_id=appointment_id,
        signed_at=at or now(),
        permit_hash=hash_ or (permit_hash(permit) if permit else hashlib.sha256(b"").hexdigest()),
        co_signed_on_device_of_user_id=co_device,
    )
    db.add(s)
    db.flush()
    return s


# ---- refs ----------------------------------------------------------------------------------------


def letters(types: Iterable[str]) -> str:
    return "/".join(PERMIT_TYPE_LETTERS[PermitType(t)] for t in types)


def display_no(p: Permit) -> str:
    return f"{p.permit_no} · {letters(p.work_types)}"


def permit_ref(p: Permit) -> PermitRef:
    return PermitRef(
        id=p.id,
        permit_no=p.permit_no,
        display_no=display_no(p),
        work_types=[PermitType(t) for t in p.work_types],
        primary_type=p.primary_type,
        status=p.status,
    )


def project_code(db: Session, project_id: uuid.UUID) -> str:
    pr = db.get(Project, project_id)
    return pr.code if pr else ""


def user_name(db: Session, uid: uuid.UUID | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return u.full_name_en if u else None


# ---- windows (§6.5) ------------------------------------------------------------------------------


def window_defs(p: Permit) -> list[windows.WindowDef]:
    return windows.parse(p.windows or [])


def window_reads(p: Permit) -> list[PermitWindowRead]:
    return [
        PermitWindowRead(
            start_local=w.start,
            end_local=w.end,
            weekdays=[d for d in windows.PY_WEEKDAY if windows.PY_WEEKDAY[d] in w.weekdays],
            crosses_midnight=w.crosses_midnight,
        )
        for w in window_defs(p)
    ]


def instances_between(
    defs: list[windows.WindowDef],
    valid_from: datetime,
    valid_to: datetime,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Window instances clipped to [valid_from, valid_to] (and to [start, end] if given)."""
    lo = max(valid_from, start) if start else valid_from
    hi = min(valid_to, end) if end else valid_to
    if hi <= lo:
        return []
    d0 = acommon.local_day(lo) - timedelta(days=1)
    d1 = acommon.local_day(hi)
    out = []
    for i in windows.instances(defs, d0, d1, d0, d1):
        s, e = max(i.start_utc, lo), min(i.end_utc, hi)
        if s < e:
            out.append((s, e))
    return sorted(out)


def instances(p: Permit, start: datetime | None = None, end: datetime | None = None) -> Any:
    return instances_between(window_defs(p), p.valid_from_at, p.valid_to_at, start, end)


def current_instance(p: Permit, at: datetime) -> tuple[datetime, datetime] | None:
    for s, e in instances(p, at - timedelta(days=2), at + timedelta(days=1)):
        if s <= at < e:
            return s, e
    return None


def next_instance(p: Permit, at: datetime) -> tuple[datetime, datetime] | None:
    for s, e in instances(p, at, at + timedelta(days=15)):
        if s > at:
            return s, e
    return None


def window_instance(i: tuple[datetime, datetime] | None) -> WindowInstance | None:
    return WindowInstance(start_at=i[0], end_at=i[1]) if i else None


def overlap(
    a: Sequence[tuple[datetime, datetime]], b: Sequence[tuple[datetime, datetime]]
) -> tuple[datetime, datetime] | None:
    """First intersection of two instance lists (half-open)."""
    first: tuple[datetime, datetime] | None = None
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if s < e and (first is None or s < first[0]):
                first = (s, e)
    return first


# ---- appointments (PR-2…PR-4) --------------------------------------------------------------------


def appointment_covers(
    a: PtwAppointment,
    types: Iterable[str],
    site_id: uuid.UUID | None,
    zone_ids: Iterable[uuid.UUID],
    days: Iterable[date],
) -> bool:
    if a.status != AppointmentStatus.active:
        return False
    if any(t not in (a.permit_types or []) for t in types):
        return False
    if site_id is not None and site_id not in (a.site_ids or []):
        return False
    zs = list(zone_ids)
    if a.zone_ids and any(z not in a.zone_ids for z in zs):
        return False
    return all(a.valid_from <= d <= a.valid_to for d in days)


def appointments_of(
    db: Session,
    project_id: uuid.UUID,
    function: AppointmentFunction,
    *,
    user_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    disciplines: Iterable[str] = (),
) -> list[PtwAppointment]:
    stmt = select(PtwAppointment).where(
        PtwAppointment.project_id == project_id, PtwAppointment.function == function
    )
    if user_id is not None and worker_id is not None:
        stmt = stmt.where(
            (PtwAppointment.holder_user_id == user_id)
            | (PtwAppointment.holder_worker_id == worker_id)
        )
    elif user_id is not None:
        stmt = stmt.where(PtwAppointment.holder_user_id == user_id)
    elif worker_id is not None:
        stmt = stmt.where(PtwAppointment.holder_worker_id == worker_id)
    ds = list(disciplines)
    rows = list(db.scalars(stmt.order_by(PtwAppointment.seq)))
    if ds:
        rows = [a for a in rows if a.discipline is not None and a.discipline.value in ds]
    return rows


def find_appointment(
    db: Session,
    project_id: uuid.UUID,
    function: AppointmentFunction,
    types: Iterable[str],
    site_id: uuid.UUID | None,
    zone_ids: Iterable[uuid.UUID],
    days: Iterable[date],
    *,
    user_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    disciplines: Iterable[str] = (),
) -> PtwAppointment | None:
    ts, zs, ds = list(types), list(zone_ids), list(days)
    for a in appointments_of(
        db, project_id, function, user_id=user_id, worker_id=worker_id, disciplines=disciplines
    ):
        if appointment_covers(a, ts, site_id, zs, ds):
            return a
    return None


def permit_days(p: Permit) -> list[date]:
    from app.services.ptw.rules import permit_dates  # noqa: PLC0415

    return permit_dates(p.valid_from_at, p.valid_to_at)


# ---- notifications -------------------------------------------------------------------------------


def officers(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    return notify.users_with_role(db, Role.hse_officer, [project_id])


def permit_people(
    db: Session,
    p: Permit,
    *,
    receiver: bool = True,
    issuer: bool = True,
    reps: bool = False,
    officer: bool = False,
    manager: bool = False,
    area: bool = False,
) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    if receiver:
        out.add(p.receiver_user_id)
    if issuer and p.issuer_user_id:
        out.add(p.issuer_user_id)
    if area and p.area_authority_user_id:
        out.add(p.area_authority_user_id)
    if reps:
        out.update(contractor_reps(db, p.project_id, p.engagement_id))
    if officer:
        out.update(officers(db, p.project_id))
    if manager:
        out.update(notify.managers(db))
    return out


def tell(
    db: Session,
    p: Permit,
    users: Iterable[uuid.UUID],
    kind: NotificationKind,
    en: str,
    ar: str,
) -> None:
    ids = sorted({u for u in users if u})
    if not ids:
        return
    notify.notify(
        db,
        ids,
        kind,
        f"{display_no(p)}: {en}",
        f"{display_no(p)}: {ar}",
        None,
        None,
        EntityType.permit,
        p.id,
        p.project_id,
    )


# ---- permit visibility ---------------------------------------------------------------------------


def view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    from app.core.enums import Capability  # noqa: PLC0415
    from app.services import projects  # noqa: PLC0415
    from app.services.permissions import forbidden_error  # noqa: PLC0415

    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, Capability.permit_view)
    if g is None:
        raise forbidden_error()
    return g


def get_permit(db: Session, p: Principal, permit_id: uuid.UUID) -> Permit:
    from app.core.errors import not_found  # noqa: PLC0415
    from app.services.permissions import forbidden_error  # noqa: PLC0415

    x = db.get(Permit, permit_id)
    if x is None:
        raise not_found("Permit")
    g = view_grant(db, p, x.project_id)
    if not acommon.grant_covers(g, [x.site_id], x.engagement_id):
        raise forbidden_error("This permit is outside your scope.")
    return x
