"""Emergency equipment (spec 6c-emergency-drills §3.8, §3.9, §4.4, EA-1…EA-7): register with EA
stickers, readiness (§6.5), checks by sticker scan or manual choice (72 h backdating), failed
checks → Out of Service / Missing + one Phase 1 CA (EA-4), tag-out and retirement."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind, QrTokenStatus
from app.core.clock import now
from app.core.emergency_enums import (
    AssetAction,
    AssetStatus,
    AssetType,
    CheckAnswer,
    CheckMethod,
    CheckOutcome,
    CheckResult,
    ExtinguisherSubtype,
    NotReadyReason,
    RecordStatus,
)
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.models import AssetCheck, EmergencyAsset, QrToken, Tpi
from app.schemas.emergency import (
    AssetCreate,
    AssetPage,
    AssetRead,
    AssetReadiness,
    AssetTransition,
    AssetUpdate,
    CheckCreate,
    CheckPage,
    CheckRead,
    VoidInput,
)
from app.schemas.hse_common import ApiWarning
from app.services.access import common as acommon
from app.services.common import invalid_transition
from app.services.emergency import common as ec
from app.services.emergency import reference as ref
from app.services.heat.common import site_in_scope
from app.services.hse_common import make_ref
from app.services.permissions import Principal, forbidden_error
from app.services.train.validity import add_months

C = Capability
NR = NotReadyReason
BACKDATE = timedelta(hours=72)


# ---- readiness (§6.3, §6.5) ----------------------------------------------------------------------


@dataclass
class Ready:
    ready: bool
    reasons: list[NotReadyReason] = field(default_factory=list)
    check_due: date | None = None
    service_due: date | None = None
    hydro_due: date | None = None


def service_due(a: EmergencyAsset) -> date | None:
    months = ref.ASSET_TYPES[a.asset_type][3]
    if months is None or a.last_service_on is None:
        return None
    return add_months(a.last_service_on, months) - timedelta(days=1)


def hydro_due(a: EmergencyAsset) -> date | None:
    """§6.3: 31 Dec of (manufactured_year + test interval years) ASSUMPTION."""
    if a.asset_type != AssetType.fire_extinguisher or a.manufactured_year is None:
        return None
    years = ref.HYDROTEST_YEARS.get(a.subtype or "")
    return date(a.manufactured_year + years, 12, 31) if years else None


def last_checks(
    db: Session, asset_ids: list[uuid.UUID], d: date | None = None
) -> dict[uuid.UUID, AssetCheck]:
    """The latest valid check of each asset (on or before local date d)."""
    if not asset_ids:
        return {}
    q = select(AssetCheck).where(
        AssetCheck.asset_id.in_(asset_ids), AssetCheck.status == RecordStatus.valid
    )
    if d is not None:
        q = q.where(AssetCheck.checked_at < ec.day_start(d + timedelta(days=1)))
    out: dict[uuid.UUID, AssetCheck] = {}
    for c in db.scalars(q.order_by(AssetCheck.checked_at)):
        out[c.asset_id] = c
    return out


def status_on(a: EmergencyAsset, d: date) -> AssetStatus:
    """The status at d: a later status change counts from its date (DECISIONS)."""
    if a.status_changed_on is not None and a.status_changed_on > d:
        return AssetStatus.in_service
    return a.status


def readiness(
    db: Session,
    a: EmergencyAsset,
    d: date,
    last: AssetCheck | None = None,
    interval: int | None = None,
    use_last: bool = False,
) -> Ready:
    """§6.5 ready(a, d)."""
    if not use_last:
        last = last_checks(db, [a.id], d).get(a.id)
    iv = interval if interval is not None else ec.cfg(db, a.project_id).interval(a.asset_type)
    st = status_on(a, d)
    r = Ready(ready=True)
    if st == AssetStatus.out_of_service:
        r.reasons.append(NR.OUT_OF_SERVICE)
    if st == AssetStatus.missing:
        r.reasons.append(NR.MISSING)
    if last is not None:
        r.check_due = ec.local_day(last.checked_at) + timedelta(days=iv)
        if last.result == CheckResult.fail:
            r.reasons.append(NR.LAST_CHECK_FAILED)
    else:
        r.check_due = a.registered_on
    if last is None or (r.check_due is not None and d > r.check_due):
        r.reasons.append(NR.CHECK_OVERDUE)
    if a.used_at is not None and ec.local_day(a.used_at) <= d:
        # 6c v1.2 / 6e SPL-5: used in a spill, not ready until a later passing check
        if last is None or last.checked_at <= a.used_at or last.result == CheckResult.fail:
            r.reasons.append(NR.USED_REPLENISH)
    r.service_due = service_due(a)
    if ref.ASSET_TYPES[a.asset_type][3] is not None and (
        r.service_due is None or d > r.service_due
    ):
        r.reasons.append(NR.SERVICE_OVERDUE)
    r.hydro_due = hydro_due(a)
    if r.hydro_due is not None and d > r.hydro_due:
        r.reasons.append(NR.HYDROTEST_OVERDUE)
    if any(date.fromisoformat(str(x["expires_on"])) < d for x in a.expiries or []):
        r.reasons.append(NR.CONSUMABLE_EXPIRED)
    if st == AssetStatus.retired:
        r.reasons = r.reasons or [NR.OUT_OF_SERVICE]
    r.ready = not r.reasons
    return r


def ready_map(
    db: Session, project_id: uuid.UUID, d: date, assets: list[EmergencyAsset] | None = None
) -> dict[uuid.UUID, Ready]:
    """Readiness of every not-Retired asset of the project at d (one check query)."""
    if assets is None:
        assets = list(
            db.scalars(select(EmergencyAsset).where(EmergencyAsset.project_id == project_id))
        )
    c = ec.cfg(db, project_id)
    live = [a for a in assets if a.registered_on <= d and status_on(a, d) != AssetStatus.retired]
    last = last_checks(db, [a.id for a in live], d)
    return {
        a.id: readiness(db, a, d, last.get(a.id), c.interval(a.asset_type), use_last=True)
        for a in live
    }


# ---- reads ---------------------------------------------------------------------------------------


def asset_read(
    db: Session, a: EmergencyAsset, r: Ready | None = None, last: AssetCheck | None = None
) -> AssetRead:
    d = ec.local_day()
    if last is None:
        last = last_checks(db, [a.id]).get(a.id)
    r = r or readiness(db, a, d, last, use_last=True)
    t = acommon.active_qr(db, a.id)
    z = ec.zone_map(db, a.project_id).get(a.zone_id) if a.zone_id else None
    return AssetRead(
        id=a.id,
        project_id=a.project_id,
        asset_tag=a.asset_tag,
        asset_type=a.asset_type,
        subtype=a.subtype,
        capacity=a.capacity,
        site_id=a.site_id,
        site_code=ec.site_code(db, a.site_id) or "",
        zone_id=a.zone_id,
        zone_code=z.code if z else None,
        location_en=a.location_en,
        owner_engagement_id=a.owner_engagement_id,
        owner_code=ec.eng_code(db, a.owner_engagement_id),
        manufactured_year=a.manufactured_year,
        serial_no=a.serial_no,
        last_service_on=a.last_service_on,
        service_provider_tpi_id=a.service_provider_tpi_id,
        service_ref=a.service_ref,
        expiries=list(a.expiries or []),
        last_check_at=last.checked_at if last else None,
        last_check_result=last.result if last else None,
        flagged_without_scan=a.flagged_without_scan,
        sticker_payload=acommon.payload(t) if t else None,
        status=a.status,
        status_reason=a.status_reason,
        readiness=AssetReadiness(
            ready=r.ready,
            reasons=r.reasons,
            check_due_on=r.check_due,
            service_due_on=r.service_due,
            hydrotest_due_on=r.hydro_due,
        ),
    )


def _view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    ec.project(db, p, project_id)
    return ec.need(p, project_id, C.emergency_view, write=False)


def list_assets(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    zone_id: uuid.UUID | None,
    asset_type: list[AssetType] | None,
    status: AssetStatus | None,
    not_ready_reason: NotReadyReason | None,
    ready: bool | None,
    page: int,
    size: int,
) -> AssetPage:
    _view_grant(db, p, project_id)
    q = select(EmergencyAsset).where(EmergencyAsset.project_id == project_id)
    if site_id is not None:
        q = q.where(EmergencyAsset.site_id == site_id)
    if zone_id is not None:
        q = q.where(EmergencyAsset.zone_id == zone_id)
    if asset_type:
        q = q.where(EmergencyAsset.asset_type.in_(asset_type))
    if status is not None:
        q = q.where(EmergencyAsset.status == status)
    rows = list(db.scalars(q.order_by(EmergencyAsset.asset_tag)))
    d = ec.local_day()
    last = last_checks(db, [a.id for a in rows])
    c = ec.cfg(db, project_id)
    rd = {
        a.id: readiness(db, a, d, last.get(a.id), c.interval(a.asset_type), use_last=True)
        for a in rows
    }
    if ready is not None:
        rows = [a for a in rows if rd[a.id].ready == ready]
    if not_ready_reason is not None:
        rows = [a for a in rows if not_ready_reason in rd[a.id].reasons]
    items = [
        asset_read(db, a, rd[a.id], last.get(a.id)) for a in rows[(page - 1) * size : page * size]
    ]
    return AssetPage(items=items, total=len(rows), page=page, page_size=size)


def _asset(db: Session, p: Principal, asset_id: uuid.UUID) -> EmergencyAsset:
    a = db.get(EmergencyAsset, asset_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Emergency asset")
    ec.need(p, a.project_id, C.emergency_view, write=False)
    return a


def read_asset(db: Session, p: Principal, asset_id: uuid.UUID) -> AssetRead:
    return asset_read(db, _asset(db, p, asset_id))


# ---- register / edit (EA-1) ----------------------------------------------------------------------


def _validate(db: Session, pid: uuid.UUID, a: EmergencyAsset) -> None:
    t = a.asset_type
    if t == AssetType.fire_extinguisher:
        if a.subtype not in {s.value for s in ExtinguisherSubtype}:
            raise validation_error("subtype", "Choose the extinguisher subtype.")
        if not a.capacity:
            raise validation_error("capacity", "Give the capacity (kg or L).")
        if a.manufactured_year is None:
            raise validation_error("manufactured_year", "Give the year of manufacture.")
    if t in ref.SERVICE_REQUIRED and a.last_service_on is None:
        raise validation_error("last_service_on", "Give the date of the last service (EA-1).")
    if a.service_provider_tpi_id is not None:
        tpi = db.get(Tpi, a.service_provider_tpi_id)
        if tpi is None or "fire_protection_service" not in (tpi.kinds or []):
            raise validation_error(
                "service_provider_tpi_id",
                "Choose a fire protection service organisation (Phase 4 register).",
            )
    have = {str(x["item"]) for x in a.expiries or []}
    for item in ref.EXPIRY_REQUIRED.get(t, ()):
        if item not in have:
            raise validation_error("expiries", f"Give the {item} expiry date.")
    if a.zone_id is not None:
        ec.zones_of_site(db, a.site_id, [a.zone_id], "zone_id")


def create_asset(db: Session, p: Principal, project_id: uuid.UUID, body: AssetCreate) -> AssetRead:
    ec.project(db, p, project_id)
    g = p.require(project_id, C.emergency_asset_manage)
    ec.site_or_422(db, project_id, body.site_id)
    ec.engagement_on(db, project_id, body.owner_engagement_id, "owner_engagement_id")
    if not g.covers_site(body.site_id) or not g.covers_engagement(body.owner_engagement_id):
        raise forbidden_error()
    if db.scalar(
        select(EmergencyAsset.id).where(
            EmergencyAsset.project_id == project_id, EmergencyAsset.asset_tag == body.asset_tag
        )
    ):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("asset_tag", "This asset tag is already used on the project.")
    a = EmergencyAsset(
        id=uuid.uuid4(),
        project_id=project_id,
        **body.model_dump(exclude={"expiries"}),
        expiries=[x.model_dump(mode="json") for x in body.expiries],
        registered_on=ec.local_day(),
        status=AssetStatus.in_service,
        created_by_user_id=p.user.id,
    )
    _validate(db, project_id, a)
    db.add(a)
    db.flush()
    acommon.issue_qr(db, QrKind.EA, project_id, a.id, a.asset_tag)
    ec.record(db, p, AuditAction.create, EntityType.emergency_asset, a, project_id)
    return asset_read(db, a)


def update_asset(db: Session, p: Principal, asset_id: uuid.UUID, body: AssetUpdate) -> AssetRead:
    a = _asset(db, p, asset_id)
    g = p.require(a.project_id, C.emergency_asset_manage)
    if not g.covers_site(a.site_id) or not g.covers_engagement(a.owner_engagement_id):
        raise forbidden_error()
    if a.status == AssetStatus.retired:
        raise invalid_transition("Emergency asset", a.status, "edited")
    from app.services.cert import common as cc  # noqa: PLC0415

    snap = cc.snap(a)
    for k, v in body.changes().items():
        if k == "expiries":
            a.expiries = [dict(x, expires_on=str(x["expires_on"])) for x in v or []]
        else:
            setattr(a, k, v)
    _validate(db, a.project_id, a)
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, EntityType.emergency_asset, a, a.project_id, before=snap)
    return asset_read(db, a)


def transition_asset(
    db: Session, p: Principal, asset_id: uuid.UUID, body: AssetTransition
) -> AssetRead:
    a = _asset(db, p, asset_id)
    before = {"status": a.status.value}
    if body.action == AssetAction.tag_out:
        g = p.require(a.project_id, C.emergency_check_record)
        if not site_in_scope(db, g, a.project_id, a.site_id):
            raise forbidden_error()
        if a.status != AssetStatus.in_service:
            raise invalid_transition("Emergency asset", a.status, AssetStatus.out_of_service)
        a.status = AssetStatus.out_of_service
    else:
        g = p.require(a.project_id, C.emergency_asset_manage)
        if not g.covers_site(a.site_id) or not g.covers_engagement(a.owner_engagement_id):
            raise forbidden_error()
        if a.status == AssetStatus.retired:
            raise invalid_transition("Emergency asset", a.status, AssetStatus.retired)
        a.status = AssetStatus.retired
        acommon.end_qr(db, a.id, QrTokenStatus.revoked)
    a.status_reason = body.reason
    a.status_changed_on = ec.local_day()
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.record(
        db, p, AuditAction.status_change, EntityType.emergency_asset, a, a.project_id,
        before=before, details={"action": body.action.value, "reason": body.reason},
    )  # fmt: skip
    return asset_read(db, a)


# ---- checks (EA-2…EA-4) --------------------------------------------------------------------------


def check_read(db: Session, c: AssetCheck, warnings: list[ApiWarning] | None = None) -> CheckRead:
    a = db.get(EmergencyAsset, c.asset_id)
    return CheckRead(
        id=c.id,
        check_no=c.check_no,
        asset_id=c.asset_id,
        asset_tag=a.asset_tag if a else "",
        checked_at=c.checked_at,
        checked_by=ec.user_ref(db, c.checked_by_user_id),
        method=c.method,
        outcome=c.outcome,
        items=list(c.items or []),
        fixed_on_spot=c.fixed_on_spot,
        result=c.result,
        ca_ref=ec.ca_ref(db, c.ca_id),
        status=c.status,
        void_reason=c.void_reason,
        warnings=warnings
        if warnings is not None
        else [
            ApiWarning(
                code=w, message="Recorded without a sticker scan.", message_ar="سُجل دون مسح الملصق."
            )
            for w in c.warnings or []
        ],
    )


def list_checks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    asset_id: uuid.UUID | None,
    page: int,
    size: int,
) -> CheckPage:
    _view_grant(db, p, project_id)
    q = select(AssetCheck).where(AssetCheck.project_id == project_id)
    if asset_id is not None:
        q = q.where(AssetCheck.asset_id == asset_id)
    from app.services.common import paginate  # noqa: PLC0415

    rows, total = paginate(db, q.order_by(AssetCheck.checked_at.desc()), page, size)
    return CheckPage(
        items=[check_read(db, c) for c in rows], total=total, page=page, page_size=size
    )


def _by_sticker(db: Session, project_id: uuid.UUID, payload: str) -> EmergencyAsset:
    m = acommon.QR_RE.match(payload.strip())
    if m is None or m.group(1) != QrKind.EA.value:
        raise validation_error("sticker_payload", "Scan an emergency asset sticker (HSE2:EA:…).")
    t = db.scalar(select(QrToken).where(QrToken.token == m.group(2), QrToken.kind == QrKind.EA))
    if t is None or t.status != QrTokenStatus.active or t.project_id != project_id:
        raise validation_error("sticker_payload", "This sticker is not active on the project.")
    a = db.get(EmergencyAsset, t.subject_id)
    if a is None:
        raise not_found("Emergency asset")
    return a


def result_of(
    asset_type: AssetType, outcome: CheckOutcome, items: list[dict[str, Any]]
) -> CheckResult:
    """EA-3 / §3.9: fail when a critical item fails or the outcome is missing."""
    if outcome == CheckOutcome.missing:
        return CheckResult.fail
    for x in items:
        if x["answer"] == CheckAnswer.fail.value and ref.EC(x["item"]) in ref.CRITICAL_ITEMS:
            return CheckResult.fail
    return CheckResult.pass_


def apply_result(
    db: Session, a: EmergencyAsset, c: AssetCheck, by: uuid.UUID | None, alerts: bool = True
) -> None:
    """EA-4: a failed check → Out of Service / Missing, one CA (high, due + 24 h, owner) and
    alerts; a passing check returns an Out of Service / Missing asset to In Service (§4.4)."""
    d = ec.local_day(c.checked_at)
    if c.result == CheckResult.pass_:
        if a.status in (AssetStatus.out_of_service, AssetStatus.missing):
            a.status = AssetStatus.in_service
            a.status_reason = f"Passed check {c.check_no}"
            a.status_changed_on = d
        return
    missing = c.outcome == CheckOutcome.missing
    if a.status != AssetStatus.retired:
        a.status = AssetStatus.missing if missing else AssetStatus.out_of_service
        a.status_reason = f"Check {c.check_no} failed"
        a.status_changed_on = d
    failed = [x["item"] for x in c.items or [] if x["answer"] == CheckAnswer.fail.value]
    what = "missing" if missing else "failed " + ", ".join(failed)
    ca = ec.make_ca(
        db, a.project_id, c.id, a.site_id, a.zone_id, a.owner_engagement_id,
        f"{a.asset_tag}: emergency equipment {what}",
        f"Check {c.check_no} on {a.asset_tag} ({a.asset_type.value}) {what}. Restore or replace "
        "the equipment and record a passing check.",
        ec.local_day(c.checked_at + timedelta(hours=24)), by,
    )  # fmt: skip
    c.ca_id = ca.id
    if alerts:
        users = (
            ec.site_engineers(db, a.project_id, a.site_id)
            | ec.reps(db, a.project_id, a.owner_engagement_id)
            | ec.officers(db, a.project_id)
        )
        ec.send(
            db, users, NotificationKind.emergency_asset_failed,
            f"{a.asset_tag} {what} — Out of Service ({ca.ref})",
            f"{a.asset_tag}: فشل فحص معدة الطوارئ — خارج الخدمة ({ca.ref})",
            a.project_id, EntityType.emergency_asset, a.id, email=True,
        )  # fmt: skip


def create_check(db: Session, p: Principal, project_id: uuid.UUID, body: CheckCreate) -> CheckRead:
    pr = ec.project(db, p, project_id)
    g = p.require(project_id, C.emergency_check_record)
    if body.sticker_payload:
        a = _by_sticker(db, project_id, body.sticker_payload)
        method = CheckMethod.qr_scan
    elif body.asset_id is not None:
        got = db.get(EmergencyAsset, body.asset_id)
        if got is None or got.project_id != project_id:
            raise validation_error("asset_id", "Choose an asset of the project.")
        a = got
        method = CheckMethod.manual
    else:
        raise validation_error("asset_id", "Scan the sticker or choose the asset.")
    if not site_in_scope(db, g, project_id, a.site_id):
        raise forbidden_error()
    if a.status == AssetStatus.retired:
        raise invalid_transition("Emergency asset", a.status, "checked")
    at = now()
    checked_at = body.checked_at or at
    if checked_at > at + timedelta(minutes=2):
        raise validation_error("checked_at", "The check time cannot be in the future.")
    if checked_at < at - BACKDATE:
        raise ec.err(
            422,
            ErrorCode.CHECK_BACKDATED,
            "A check may be back-dated by at most 72 hours (EA-2).",
            "لا يجوز تسجيل فحص بتاريخ أقدم من 72 ساعة.",
            field="checked_at",
        )
    items = [{"item": x.item.value, "answer": x.answer.value} for x in body.items]
    if body.outcome == CheckOutcome.checked:
        want = {i.value for i in ref.ASSET_TYPES[a.asset_type][4]}
        answered = {x["item"] for x in items}
        if not want <= answered:
            raise validation_error(
                "items",
                "Answer every check item of the type: " + ", ".join(sorted(want - answered)),
            )
        items = [x for x in items if x["item"] in want]
    fixed = body.fixed_on_spot and not any(
        x["answer"] == "fail" and ref.EC(x["item"]) in ref.CRITICAL_ITEMS for x in items
    )
    warnings: list[ApiWarning] = []
    if method == CheckMethod.manual and not ec.is_hse(p, project_id):
        warnings.append(
            ApiWarning(
                code=ErrorCode.CHECK_WITHOUT_SCAN.value,
                message="Recorded without a sticker scan (EA-2); the asset is flagged.",
                message_ar="سُجل الفحص دون مسح الملصق وتم تمييز المعدة.",
            )
        )
        a.flagged_without_scan = True
    year = ec.local_day(checked_at).year
    seq = ec.next_seq(db, AssetCheck, project_id, year)
    c = AssetCheck(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        check_no=make_ref("EAC", pr.code, year, seq, 6),
        project_id=project_id,
        asset_id=a.id,
        checked_at=checked_at,
        checked_by_user_id=p.user.id,
        method=method,
        outcome=body.outcome,
        items=items,
        fixed_on_spot=fixed,
        result=result_of(a.asset_type, body.outcome, items),
        photo_ids=list(body.photo_ids),
        warnings=[w.code for w in warnings],
        status=RecordStatus.valid,
        created_by_user_id=p.user.id,
    )
    db.add(c)
    db.flush()
    apply_result(db, a, c, p.user.id)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.emergency_asset_check, c, project_id)
    return check_read(db, c, warnings)


def void_check(db: Session, p: Principal, check_id: uuid.UUID, body: VoidInput) -> CheckRead:
    c = db.get(AssetCheck, check_id)
    if c is None or not p.can_see_project(c.project_id):
        raise not_found("Asset check")
    p.require(c.project_id, C.emergency_void)
    if c.status == RecordStatus.voided:
        raise invalid_transition("Asset check", c.status, RecordStatus.voided)
    c.status = RecordStatus.voided
    c.void_reason = ec.reason(body.reason, 20)
    c.updated_by_user_id = p.user.id
    db.flush()
    ec.record(
        db, p, AuditAction.status_change, EntityType.emergency_asset_check, c, c.project_id,
        before={"status": "valid"},
    )  # fmt: skip
    return check_read(db, c)


# ---- provision gaps (EA-6) -----------------------------------------------------------------------


def provision_gaps(
    db: Session, project_id: uuid.UUID, d: date, zones_work: dict[uuid.UUID, list[uuid.UUID]]
) -> dict[uuid.UUID, list[str]]:
    """site → gap texts: zones with work today short of ready extinguishers / first-aid kits /
    eyewash, sites short of ready AEDs. Informational only (never blocks)."""
    c = ec.cfg(db, project_id)
    rd = ready_map(db, project_id, d)
    assets = {
        a.id: a
        for a in db.scalars(select(EmergencyAsset).where(EmergencyAsset.project_id == project_id))
    }
    profs = ec.zone_profiles(db, project_id)
    zmap = ec.zone_map(db, project_id)
    per_zone: dict[uuid.UUID, dict[AssetType, int]] = defaultdict(lambda: defaultdict(int))
    per_site: dict[uuid.UUID, int] = defaultdict(int)
    for aid, r in rd.items():
        a = assets[aid]
        if not r.ready:
            continue
        if a.zone_id is not None:
            per_zone[a.zone_id][a.asset_type] += 1
        if a.asset_type == AssetType.aed:
            per_site[a.site_id] += 1
    out: dict[uuid.UUID, list[str]] = defaultdict(list)
    for site, zs in zones_work.items():
        for z in zs:
            zone = zmap.get(z)
            if zone is None:
                continue
            pf = profs.get(z)
            mn_e = (pf.min_extinguishers if pf and pf.min_extinguishers else None) or int(
                c["min_extinguishers_per_zone"]
            )
            mn_k = (pf.min_first_aid_kits if pf and pf.min_first_aid_kits else None) or int(
                c["min_first_aid_kits_per_zone"]
            )
            n_e = per_zone[z][AssetType.fire_extinguisher]
            n_k = per_zone[z][AssetType.first_aid_kit]
            if n_e < mn_e:
                out[site].append(f"{zone.code}: ready extinguishers {n_e} < {mn_e}")
            if n_k < mn_k:
                out[site].append(f"{zone.code}: ready first-aid kits {n_k} < {mn_k}")
            if (
                pf is not None
                and pf.eyewash_required
                and not any(per_zone[z][t] for t in ref.EYEWASH)
            ):
                out[site].append(f"{zone.code}: no ready eyewash")
        if per_site[site] < int(c["min_aed_per_site"]):
            out[site].append(f"ready AEDs {per_site[site]} < {c['min_aed_per_site']}")
    return out


def ready_extinguisher_in(
    db: Session, project_id: uuid.UUID, zone_id: uuid.UUID, at: datetime
) -> bool:
    d = ec.local_day(at)
    rows = list(
        db.scalars(
            select(EmergencyAsset).where(
                EmergencyAsset.project_id == project_id,
                EmergencyAsset.zone_id == zone_id,
                EmergencyAsset.asset_type == AssetType.fire_extinguisher,
            )
        )
    )
    return any(r.ready for r in ready_map(db, project_id, d, rows).values())
