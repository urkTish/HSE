"""Heat welfare checks at rest stations (spec 6b-heat-stress §3.8, RS-1…RS-4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.heat_enums import CheckAnswer, Cooling, RecordStatus, Regime, WelfareItem
from app.models import CorrectiveAction, HeatWelfareCheck, RestStation
from app.schemas.heat import (
    VoidInput,
    WelfareAnswerRead,
    WelfareCheckCreate,
    WelfareCheckPage,
    WelfareCheckRead,
)
from app.services.common import invalid_transition, paginate
from app.services.heat import common as hc
from app.services.heat import reference as ref
from app.services.heat import state
from app.services.permissions import Principal

C = Capability
A = CheckAnswer
HW = WelfareItem


def critical_fail(items: list[dict[str, Any]]) -> bool:
    return any(x["answer"] == A.fail.value and HW(x["item"]) in ref.CRITICAL for x in items or [])


def check_read(
    db: Session, x: HeatWelfareCheck, warnings: list[Any] | None = None
) -> WelfareCheckRead:
    st = db.get(RestStation, x.station_id)
    cas = (
        list(
            db.scalars(select(CorrectiveAction.ref).where(CorrectiveAction.id.in_(list(x.ca_ids))))
        )
        if x.ca_ids
        else []
    )
    return WelfareCheckRead(
        id=x.id,
        check_no=x.check_no,
        project_id=x.project_id,
        station_id=x.station_id,
        station_code=st.station_code if st else "?",
        checked_at=x.checked_at,
        checked_by=hc.user_ref(db, x.checked_by_user_id),
        engagement_id=x.engagement_id,
        items=[WelfareAnswerRead(**i) for i in x.items or []],
        water_temp_c=hc.dstr(x.water_temp_c),
        persons_present=x.persons_present,
        critical_fail=critical_fail(x.items),
        ca_refs=cas,
        status=x.status,
        void_reason=x.void_reason,
        warnings=warnings or [],
    )


def _zones_quiet(db: Session, st: RestStation, at: datetime) -> bool:
    """RS-2: HW10 may be n.a. only when every zone served is at R0 or unknown."""
    cfg = hc.cfg(db, st.project_id)
    for z in st.zone_ids or []:
        h = state.headline(state.zone_state(db, st.project_id, z, at), cfg)
        if h not in (Regime.R0, Regime.unknown):
            return False
    return True


def _na_error(item: WelfareItem) -> Any:
    return hc.err(
        422,
        ErrorCode.NA_NOT_ALLOWED,
        f"{item.value} cannot be answered n.a. here.",
        "لا يمكن الإجابة بـ لا ينطبق على هذا البند.",
        field="items",
        item=item.value,
    )


def create_check(
    db: Session, p: Principal, project_id: uuid.UUID, body: WelfareCheckCreate
) -> WelfareCheckRead:
    hc.project(db, p, project_id)
    g = p.require(project_id, C.heat_welfare_record)
    st = db.get(RestStation, body.station_id)
    if st is None or st.project_id != project_id:
        raise not_found("Rest station")
    if not hc.site_in_scope(db, g, project_id, st.site_id):
        raise not_found("Rest station")
    if not st.active:
        raise hc.err(
            422,
            ErrorCode.STATION_INACTIVE,
            "The rest station is not active.",
            "محطة الراحة غير فعالة.",
            field="station_id",
        )
    at = now()
    if body.checked_at > at + timedelta(minutes=2) or body.checked_at < at - timedelta(hours=24):
        raise validation_error("checked_at", "Within the last 24 hours.")
    cfg = hc.cfg(db, project_id)
    answers: dict[WelfareItem, dict[str, Any]] = {}
    for ans in body.items:
        if ans.item in answers:
            raise validation_error("items", f"{ans.item.value} is answered twice.")
        answers[ans.item] = {"item": ans.item.value, "answer": ans.answer.value, "note": ans.note}
    missing = [i.value for i in HW if i not in answers]
    if missing:
        raise validation_error("items", "Answer every item: " + ", ".join(missing))
    for item, a in answers.items():
        if a["answer"] != A.na.value:
            continue
        if item not in ref.NA_ALLOWED:
            raise _na_error(item)
        if item == HW.HW02 and body.water_temp_c is not None:
            raise _na_error(item)
        if item == HW.HW06 and st.cooling != Cooling.none:
            raise _na_error(item)
        if item == HW.HW10 and not _zones_quiet(db, st, body.checked_at):
            raise _na_error(item)
    if body.water_temp_c is not None and Decimal(body.water_temp_c) > cfg.dec("cool_water_max_c"):
        answers[HW.HW02]["answer"] = A.fail.value  # RS-2
    items = [answers[i] for i in HW]
    y = hc.local_day(body.checked_at).year
    seq = hc.next_seq(db, HeatWelfareCheck, project_id, y)
    x = HeatWelfareCheck(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        check_no=f"HWC-{hc.pcode(db, project_id)}-{y}-{seq:05d}",
        project_id=project_id,
        station_id=st.id,
        engagement_id=body.engagement_id,
        checked_at=body.checked_at,
        checked_by_user_id=p.user.id,
        items=items,
        water_temp_c=body.water_temp_c,
        persons_present=body.persons_present,
        ca_ids=[],
        status=RecordStatus.valid,
        created_by_user_id=p.user.id,
    )
    db.add(x)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.heat_welfare_check, x, project_id)
    if critical_fail(items):
        fails = [
            i["item"]
            for i in items
            if i["answer"] == A.fail.value and HW(i["item"]) in ref.CRITICAL
        ]
        eng = body.engagement_id or hc.tier1_on_site(db, project_id, st.site_id)
        users = hc.site_engineers(db, project_id, st.site_id) | hc.officers(db, project_id)
        if eng is not None:
            ca = hc.make_ca(
                db,
                project_id,
                x.id,
                st.site_id,
                st.zone_ids[0] if st.zone_ids else None,
                eng,
                f"Heat welfare: {', '.join(fails)} failed at {st.station_code}",
                f"Welfare check {x.check_no} failed critical item(s) {', '.join(fails)} at "
                f"{st.station_code}. Restore water, shade, first aid or the rest regime now.",
                hc.local_day(body.checked_at + timedelta(hours=24)),
                p.user.id,
            )
            x.ca_ids = [ca.id]
            users.add(ca.owner_id)
            db.flush()
        hc.send(
            db,
            users,
            NotificationKind.heat_welfare_fail,
            f"Critical heat welfare failure at {st.station_code}: "
            f"{', '.join(fails)} ({x.check_no})",
            f"فشل بند حرج في فحص الراحة {st.station_code}: {', '.join(fails)}",
            project_id,
            EntityType.heat_welfare_check,
            x.id,
            email=True,
        )
    return check_read(db, x)


def list_checks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    station_id: uuid.UUID | None,
    day: date | None,
) -> WelfareCheckPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = select(HeatWelfareCheck).where(HeatWelfareCheck.project_id == project_id)
    if station_id:
        stmt = stmt.where(HeatWelfareCheck.station_id == station_id)
    if day:
        stmt = stmt.where(
            HeatWelfareCheck.checked_at >= hc.day_start(day),
            HeatWelfareCheck.checked_at < hc.day_start(day + timedelta(days=1)),
        )
    stmt = stmt.order_by(HeatWelfareCheck.checked_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return WelfareCheckPage(
        items=[check_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def void(db: Session, p: Principal, check_id: uuid.UUID, body: VoidInput) -> WelfareCheckRead:
    x = db.get(HeatWelfareCheck, check_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Welfare check")
    p.require(x.project_id, C.heat_void)
    why = hc.reason(body.reason, 20)
    if x.status != RecordStatus.valid:
        raise invalid_transition("Welfare check", x.status, RecordStatus.voided)
    before = {"status": x.status.value}
    x.status, x.void_reason = RecordStatus.voided, why
    db.flush()
    hc.record(
        db, p, AuditAction.status_change, EntityType.heat_welfare_check, x, x.project_id, before
    )
    return check_read(db, x)


def missing_yesterday(db: Session, project_id: uuid.UUID, d: date) -> int:
    """§7: welfare checks missing on day d (controls period, days with work)."""
    cfg = hc.cfg(db, project_id)
    if not (cfg.active_on(d) and cfg.in_controls(d)):
        return 0
    work = hc.days_with_work(db, project_id, d, d)
    need = int(cfg["welfare_checks_per_station_day"])
    n = 0
    for st in db.scalars(
        select(RestStation).where(
            RestStation.project_id == project_id, RestStation.active.is_(True)
        )
    ):
        if d not in work.get(st.site_id, set()):
            continue
        cnt = len(
            list(
                db.scalars(
                    select(HeatWelfareCheck.id).where(
                        HeatWelfareCheck.station_id == st.id,
                        HeatWelfareCheck.status == RecordStatus.valid,
                        HeatWelfareCheck.checked_at >= hc.day_start(d),
                        HeatWelfareCheck.checked_at < hc.day_start(d + timedelta(days=1)),
                    )
                )
            )
        )
        if cnt < need and hc.once(db, f"heat:welfare_missing:{st.id}:{d.isoformat()}"):
            n += hc.send(
                db,
                hc.officers(db, project_id) | hc.site_engineers(db, project_id, st.site_id),
                NotificationKind.heat_welfare_missing,
                f"Welfare checks missing at {st.station_code} on {d.isoformat()}",
                f"فحوص الراحة ناقصة في {st.station_code} بتاريخ {d.isoformat()}",
                project_id,
            )
    return n
