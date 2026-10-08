# ruff: noqa: E501
"""Save-time and Request-time permit validations (spec 3-ptw PT-4, PT-5, PT-10, PT-11, HT-2,
AW-4, PR-3, PR-5, PR-10). Each check raises an ApiError with the stable code of the rule."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import Role, ZoneStatus, ZoneType
from app.core.errors import ErrorCode, validation_error
from app.core.ptw_enums import (
    CrewLineStatus,
    ExemptionKind,
    PermitStatus,
    PermitType,
    PtwCrewRole,
)
from app.models import Permit, PermitCrew, RoleAssignment, User, Wap, Zone
from app.services.access import common as acommon
from app.services.hse_common import user_roles
from app.services.ptw import common, evaluation
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

T = PermitType
R = PtwCrewRole
S = PermitStatus
AREA_ROLES = {Role.hse_officer, Role.site_engineer, Role.permit_issuer}
BACKDATE_TOLERANCE = timedelta(minutes=15)
LIVE_BUSY = (S.issued, S.active)


def sod(en: str, ar: str = "تعارض في فصل المهام.") -> Any:
    return common.err(ErrorCode.SOD_CONFLICT, en, ar)


# ---- zones (PT-4) --------------------------------------------------------------------------------


def zones_ok(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, zone_ids: list[uuid.UUID]
) -> list[Zone]:
    if len(set(zone_ids)) != len(zone_ids):
        raise validation_error("zone_ids", "A zone is listed twice.")
    rows = {z.id: z for z in db.scalars(select(Zone).where(Zone.id.in_(zone_ids)))}
    zones: list[Zone] = []
    for i, zid in enumerate(zone_ids):
        z = rows.get(zid)
        if z is None or z.project_id != project_id:
            raise validation_error(f"zone_ids.{i}", "Zone not found on this project.")
        zones.append(z)
    if any(z.site_id != zones[0].site_id for z in zones) or zones[0].site_id != site_id:
        raise common.err(
            ErrorCode.ZONES_NOT_SAME_SITE,
            "All zones of a permit must belong to the permit's site (PT-4).",
            "يجب أن تتبع جميع مناطق التصريح موقع التصريح نفسه.",
            field="zone_ids",
        )
    sides = {z.zone_type == ZoneType.airside for z in zones}
    if len(sides) > 1:
        raise common.err(
            ErrorCode.MIXED_SIDE_ZONES,
            "Airside and landside zones cannot be mixed on one permit (PT-4).",
            "لا يمكن الجمع بين مناطق الجانب الجوي والأرضي في تصريح واحد.",
            field="zone_ids",
        )
    for i, z in enumerate(zones):
        if z.status != ZoneStatus.active:
            raise common.err(
                ErrorCode.ZONE_ARCHIVED,
                f"Zone {z.code} is {z.status.value.replace('_', ' ')} (PT-4).",
                f"المنطقة {z.code} غير نشطة.",
                field=f"zone_ids.{i}",
            )
    return zones


# ---- validity (PT-10, PT-11) ---------------------------------------------------------------------


def duration_limit(
    db: Session, permit: Permit, f: facts_mod.Facts | None = None
) -> tuple[str, timedelta, datetime | None]:
    """The smallest type maximum (lifting: 1 day when critical) and, for airside works, the
    linked WAP's validity end. Returns (limiting type, max duration, absolute end or None)."""
    f = f or facts_mod.compute(db, permit)
    days = f.settings.type_max_duration_days or ref.TYPE_MAX_DAYS_DEFAULT
    best: tuple[str, timedelta] | None = None
    for t in f.types:
        d = int(days.get(t, ref.TYPE_MAX_DAYS_DEFAULT.get(t, 7)))
        if t == T.lifting.value and f.critical:
            d = 1
        cand = (t, timedelta(days=d))
        if best is None or cand[1] < best[1]:
            best = cand
    assert best is not None  # noqa: S101
    end = None
    if f.airside:
        w = evaluation.linked_wap(db, permit, f, permit.valid_from_at)
        if w is not None:
            end = acommon.local_midnight_utc(w.valid_to + timedelta(days=1))
    return best[0], best[1], end


def validity_ok(db: Session, permit: Permit, f: facts_mod.Facts | None = None) -> None:
    if permit.valid_to_at <= permit.valid_from_at:
        raise validation_error("valid_to_at", "valid_to_at must be after valid_from_at (PT-10).")
    t, limit, end = duration_limit(db, permit, f)
    hours = int(limit.total_seconds() // 3600)
    if permit.valid_to_at - permit.valid_from_at > limit:
        raise common.err(
            ErrorCode.DURATION_EXCEEDS_LIMIT,
            f"The validity exceeds the {hours} h maximum of {t} (PT-11).",
            f"مدة التصريح تتجاوز الحد الأقصى ({hours} ساعة) لنوع {ref.TYPE_LABEL_AR[T(t)]}.",
            field="valid_to_at",
            meta={"limiting_type": t, "max_hours": hours},
        )
    if end is not None and permit.valid_to_at > end:
        raise common.err(
            ErrorCode.DURATION_EXCEEDS_LIMIT,
            "Airside works cannot run past the linked WAP's validity (PT-11).",
            "لا يمكن أن تتجاوز أعمال الجانب الجوي صلاحية تصريح دخول المنطقة.",
            field="valid_to_at",
            meta={"limiting_type": T.airside_works.value, "wap_valid_to": end.isoformat()},
        )


def not_backdated(permit: Permit, at: datetime) -> None:
    if permit.valid_from_at < at - BACKDATE_TOLERANCE:
        raise common.err(
            ErrorCode.BACKDATED_PERMIT,
            "valid_from_at may not be more than 15 min in the past at Request (PT-10).",
            "لا يجوز أن يبدأ التصريح قبل أكثر من 15 دقيقة من وقت الطلب.",
            field="valid_from_at",
        )


# ---- windows (HT-2, AW-4) ------------------------------------------------------------------------


def midday_window_ok(db: Session, permit: Permit, f: facts_mod.Facts | None = None) -> None:
    """HT-2: a window overlapping the ban hours on a ban date is rejected unless exempted."""
    f = f or facts_mod.compute(db, permit)
    bad = [
        d
        for d in evaluation.ban_dates(f)
        if evaluation.exemption(db, permit, ExemptionKind.midday_ban, d) is None
    ]
    if bad:
        hrs = f.settings.midday_ban_hours
        raise common.err(
            ErrorCode.MIDDAY_BAN_WINDOW,
            f"A window overlaps the midday ban {hrs['start_local']}–{hrs['end_local']} on {bad[0].isoformat()}: split it (HT-2).",
            f"فترة عمل تتداخل مع حظر الظهيرة {hrs['start_local']}–{hrs['end_local']} بتاريخ {bad[0].isoformat()}: قسّمها.",
            field="windows",
            meta={"date": bad[0].isoformat()},
        )


def wap_window_ok(db: Session, permit: Permit, f: facts_mod.Facts | None = None) -> None:
    """AW-4 at save: every permit window instance lies inside the linked WAP's windows."""
    f = f or facts_mod.compute(db, permit)
    if not f.airside:
        return
    w = evaluation.linked_wap(db, permit, f, permit.valid_from_at)
    if w is None:
        return
    bad = evaluation.outside_wap_windows(permit, w)
    if bad:
        raise common.err(
            ErrorCode.OUTSIDE_WAP_WINDOW,
            f"The permit window on {bad} is outside the windows of {w.wap_no} (AW-4).",
            f"فترة عمل التصريح ({bad}) خارج فترات تصريح دخول المنطقة {w.wap_no}.",
            field="windows",
            meta={"wap_no": w.wap_no},
        )


def wap_link_ok(db: Session, permit: Permit, wap_ids: list[uuid.UUID]) -> None:
    for i, wid in enumerate(wap_ids):
        w = db.get(Wap, wid)
        if w is None or w.project_id != permit.project_id:
            raise validation_error(f"linked_wap_ids.{i}", "WAP not found on this project.")


# ---- people (PT-5, PR-3, PR-5) -------------------------------------------------------------------


def receiver_ok(
    db: Session, permit: Permit, user_id: uuid.UUID, field: str = "receiver_user_id"
) -> None:
    """PT-5: an Active permit_receiver assignment on the permit's engagement or an ancestor."""
    day = today()
    tree = set(acommon.engagement_ancestors(db, permit.engagement_id))
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.role == Role.permit_receiver,
            RoleAssignment.project_id == permit.project_id,
        )
    ):
        if a.is_active_on(day) and a.contractor_engagement_id in tree:
            if a.site_ids and permit.site_id not in a.site_ids:
                continue
            return
    raise validation_error(
        field, "The receiver needs an Active permit receiver role on this contractor (PT-5)."
    )


def people_sod(db: Session, permit: Permit) -> None:
    """PR-5 (a) (c) (d) on the named people of the permit."""
    rid = permit.receiver_user_id
    aa = permit.area_authority_user_id
    iss = permit.issuer_user_id
    hse = permit.hse_reviewer_user_id
    if aa and aa == rid:
        raise sod(
            "The area authority cannot be the receiver (PR-5 c).",
            "لا يمكن أن يكون مسؤول المنطقة هو المستلم.",
        )
    if iss and iss == rid:
        raise sod(
            "The issuer cannot be the receiver (PR-5 a).", "لا يمكن أن يكون المُصدِر هو المستلم."
        )
    if iss and aa and iss == aa:
        raise sod(
            "The issuer cannot be the area authority (PR-5 c).",
            "لا يمكن أن يكون المُصدِر مسؤول المنطقة.",
        )
    if hse and hse in (rid, iss):
        raise sod(
            "The HSE reviewer cannot be the receiver or the issuer (PR-5 d).",
            "لا يمكن أن يكون مراجع السلامة هو المستلم أو المُصدِر.",
        )
    if iss:
        from app.services.ptw.lifecycle import employer_in_tree  # noqa: PLC0415

        if employer_in_tree(db, db.get(User, iss), permit):
            raise sod(
                "The issuer cannot be employed by the permit's contractor or its parent (PR-5 b).",
                "لا يمكن أن يكون المُصدِر من موظفي المقاول المنفذ أو المقاول الرئيسي.",
            )


def area_authority_ok(db: Session, permit: Permit, user_id: uuid.UUID, at: datetime) -> None:
    """PR-3: Active area_authority appointment covering every zone, held by a user whose role
    on the project is hse_officer, site_engineer or permit_issuer."""
    day = evaluation.appointment_day(permit, at)
    roles = user_roles(db, user_id, permit.project_id)
    ok = bool(roles & AREA_ROLES) and evaluation._covers_zone_sites(db, permit, user_id, day)
    if not ok:
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "The area authority needs an Active area authority appointment covering every zone (PR-3).",
            "يلزم تعيين مسؤول منطقة ساري يغطي كل مناطق التصريح.",
            field="area_authority_user_id",
        )


# ---- crew (PT-7, PR-5 f/g, PR-10) ----------------------------------------------------------------


def busy_elsewhere(
    db: Session, permit: Permit, worker_id: uuid.UUID, role: PtwCrewRole
) -> str | None:
    """PR-10: the permit number where the worker already holds a key role on an Issued/Active
    permit (supervisor: the 3rd such permit of the same engagement and site)."""
    rows = db.execute(
        select(PermitCrew, Permit)
        .join(Permit, Permit.id == PermitCrew.permit_id)
        .where(
            PermitCrew.worker_id == worker_id,
            PermitCrew.status != CrewLineStatus.removed,
            Permit.status.in_(LIVE_BUSY),
            Permit.id != permit.id,
        )
    ).all()
    if role in ref.BUSY_ROLES:
        for line, other in rows:
            if line.crew_role in ref.BUSY_ROLES:
                return other.permit_no
    if role == R.supervisor:
        sup = {
            other.id: other.permit_no
            for line, other in rows
            if line.crew_role == R.supervisor
            and other.engagement_id == permit.engagement_id
            and other.site_id == permit.site_id
        }
        for other in db.scalars(
            select(Permit).where(
                Permit.supervisor_worker_id == worker_id,
                Permit.status.in_(LIVE_BUSY),
                Permit.id != permit.id,
                Permit.engagement_id == permit.engagement_id,
                Permit.site_id == permit.site_id,
            )
        ):
            sup[other.id] = other.permit_no
        if len(sup) >= ref.SUPERVISOR_MAX_PERMITS:
            return sorted(sup.values())[0]
    return None


def busy_error(db: Session, worker_id: uuid.UUID, role: PtwCrewRole, other: str) -> Any:
    wno = evaluation.worker_no(db, worker_id)
    return common.err(
        ErrorCode.KEY_ROLE_BUSY,
        f"{wno} already holds a key role ({role.value}) on {other} (PR-10).",
        f"العامل {wno} يشغل دوراً رئيسياً على التصريح {other}.",
        meta={"worker_no": wno, "permit_no": other},
    )


def key_roles_busy(db: Session, permit: Permit) -> None:
    for line in evaluation.crew_lines(db, permit.id):
        if line.status != CrewLineStatus.listed:
            continue
        other = busy_elsewhere(db, permit, line.worker_id, line.crew_role)
        if other:
            raise busy_error(db, line.worker_id, line.crew_role, other)


def crew_sod(
    db: Session,
    permit: Permit,
    worker_id: uuid.UUID,
    role: PtwCrewRole,
    skip_line: uuid.UUID | None = None,
) -> None:
    """PR-5 (f) fire watch has no other role; (g) standby is not an entrant."""
    others = [
        x.crew_role
        for x in evaluation.crew_lines(db, permit.id)
        if x.worker_id == worker_id and x.id != skip_line
    ]
    if role in others:
        raise validation_error("crew_role", "This worker already holds this role on the permit.")
    if others and (role == R.fire_watch or R.fire_watch in others):
        raise sod(
            "A fire watch has no other crew role on the permit and is not the hot-work operative (PR-5 f).",
            "مراقب الحريق لا يشغل أي دور آخر في التصريح.",
        )
    if (role == R.standby_person and R.entrant in others) or (
        role == R.entrant and R.standby_person in others
    ):
        raise sod(
            "The standby person cannot be an entrant on the same permit (PR-5 g).",
            "لا يجوز أن يكون الشخص المناوب من الداخلين في نفس التصريح.",
        )


def in_tree(db: Session, permit: Permit, worker_id: uuid.UUID) -> bool:
    """PT-7: the worker's employer engagement is the permit's engagement or an ancestor."""
    from app.models import Deployment, Worker  # noqa: PLC0415

    w = db.get(Worker, worker_id)
    if w is None:
        return False
    tree = set(acommon.engagement_ancestors(db, permit.engagement_id))
    deps = list(
        db.scalars(
            select(Deployment).where(
                Deployment.worker_id == worker_id, Deployment.project_id == permit.project_id
            )
        )
    )
    return any(d.engagement_id in tree and d.status.value != "demobilised" for d in deps)


# ---- Request (§4.1 Draft → Requested) ------------------------------------------------------------


def for_request(db: Session, permit: Permit, at: datetime) -> None:
    f = facts_mod.compute(db, permit)
    zones_ok(db, permit.project_id, permit.site_id, list(permit.zone_ids or []))
    missing = [t for t in f.types if t != T.general.value and not f.sections.get(t)]
    if missing:
        raise validation_error(
            "sections", "Complete the section of every work type: " + ", ".join(missing)
        )
    if not permit.area_authority_user_id:
        raise validation_error(
            "area_authority_user_id", "Name the area authority before Request (PR-3)."
        )
    receiver_ok(db, permit, permit.receiver_user_id)
    people_sod(db, permit)
    area_authority_ok(db, permit, permit.area_authority_user_id, at)
    listed = [x for x in evaluation.crew_lines(db, permit.id) if x.status != CrewLineStatus.removed]
    if not listed:
        raise validation_error("crew", "List at least one crew member before Request.")
    not_backdated(permit, at)
    validity_ok(db, permit, f)
    midday_window_ok(db, permit, f)
    wap_window_ok(db, permit, f)
