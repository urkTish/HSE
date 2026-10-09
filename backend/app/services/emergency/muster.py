"""Musters (spec 6c-emergency-drills §3.12, §4.7, MU-1…MU-9, P6c-4, P6c-5): the roll from the
gate log (MU-2) or engagement counts (MU-3), accounting by access-card scan at the assembly point
(a user with 185 or a `muster_reader` device bound to the AP, §11.3), ticks, resolutions,
reconciliation (MU-7), the headcount-target alert (MU-8) and the printable sheet (MU-9).

A scan never creates a gate-log row and never runs the access eligibility check (MU-4)."""

from __future__ import annotations

import secrets
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import GateDirection, QrKind, QrTokenStatus
from app.core.clock import now
from app.core.config import get_settings
from app.core.emergency_enums import (
    ActiveStatus,
    EntryMethod,
    EntryState,
    FindingCategory,
    FindingSeverity,
    MusterMode,
    MusterSource,
    MusterStatus,
    ResolutionReason,
)
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.security import decode_jwt, token_digest
from app.models import (
    AssemblyPoint,
    Deployment,
    Drill,
    EmergencyEvent,
    Gate,
    GateCheck,
    Muster,
    MusterDevice,
    MusterEntry,
    QrToken,
)
from app.schemas.emergency import (
    CountsInput,
    MusterCountRow,
    MusterDeviceCreate,
    MusterDeviceRead,
    MusterDeviceRegistered,
    MusterEntryRead,
    MusterRead,
    MusterSessionInput,
    MusterSessionRead,
    MusterSheet,
    ResolveInput,
    ScanInput,
    VoidInput,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.common import invalid_transition
from app.services.emergency import common as ec
from app.services.hse_common import make_ref
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
ES = EntryState
LIVE = (MusterStatus.open, MusterStatus.reconciled)
OPEN_STATES = (ES.expected, ES.unaccounted)


# ---- opening (MU-1, MU-2) ------------------------------------------------------------------------


def roll(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    at: datetime,
    zone_ids: list[uuid.UUID] | None,
) -> list[GateCheck]:
    """MU-2: deployments whose latest gate row at a gate of the site within the window is `in`
    and GRANTED / GRANTED_WITH_WARNING or admitted despite denial (zone evacuation: rows whose
    target zone is evacuated)."""
    hours = int(ec.cfg(db, project_id)["muster_roll_window_hours"])
    rows = db.scalars(
        select(GateCheck)
        .join(Gate, Gate.id == GateCheck.gate_id)
        .where(
            Gate.site_id == site_id,
            GateCheck.project_id == project_id,
            GateCheck.deployment_id.is_not(None),
            GateCheck.final.is_(True),
            GateCheck.occurred_at >= at - timedelta(hours=hours),
            GateCheck.occurred_at <= at,
        )
        .order_by(GateCheck.occurred_at)
    )
    latest: dict[uuid.UUID, GateCheck] = {}
    for r in rows:
        assert r.deployment_id is not None  # noqa: S101
        latest[r.deployment_id] = r
    out = []
    for r in latest.values():
        if r.direction != GateDirection.in_:
            continue
        if not (r.result in ec.LIVE_GATE or r.admitted_despite_denial):
            continue
        if zone_ids and r.zone_id not in zone_ids:
            continue
        out.append(r)
    return out


def open_muster(
    db: Session,
    project_id: uuid.UUID,
    source_type: MusterSource,
    source_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_ids: list[uuid.UUID] | None,
    opened_at: datetime,
    count_only: bool,
    by: uuid.UUID | None,
) -> Muster:
    """MU-1: roll mode when the site has an active gate (not for late entries), else count."""
    mode = (
        MusterMode.roll
        if not count_only and ec.has_gates(db, project_id, site_id)
        else MusterMode.count_
    )
    year = ec.local_day(opened_at).year
    seq = ec.next_seq(db, Muster, project_id, year)
    m = Muster(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        muster_no=make_ref("MUS", ec.pcode(db, project_id), year, seq, 3),
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        site_id=site_id,
        ap_ids=[a.id for a in ec.active_aps(db, project_id, site_id)],
        zone_ids=list(zone_ids or []),
        mode=mode,
        opened_at=opened_at,
        counts=[],
        extras=0,
        status=MusterStatus.open,
        alerts_sent=[],
        created_by_user_id=by,
    )
    db.add(m)
    db.flush()
    if mode == MusterMode.roll:
        for r in roll(db, project_id, site_id, opened_at, zone_ids):
            assert r.deployment_id is not None  # noqa: S101
            db.add(
                MusterEntry(
                    id=uuid.uuid4(),
                    muster_id=m.id,
                    deployment_id=r.deployment_id,
                    engagement_id=r.engagement_id,
                    source_gate_check_id=r.id,
                    state=ES.expected,
                )
            )
        db.flush()
    audit.record(
        db, AuditAction.create, audit.SYSTEM, entity_type=EntityType.emergency_muster,
        entity_id=m.id, project_id=project_id,
        after={"muster_no": m.muster_no, "mode": mode.value, "source": source_type.value},
    )  # fmt: skip
    return m


def entries(db: Session, m: Muster) -> list[MusterEntry]:
    return list(
        db.scalars(
            select(MusterEntry)
            .where(MusterEntry.muster_id == m.id)
            .order_by(MusterEntry.engagement_id, MusterEntry.deployment_id)
        )
    )


def sync_exits(db: Session, m: Muster, at: datetime | None = None) -> int:
    """MU-2: an exit at a gate of the site after opened_at accounts the entry (exit_scan)."""
    if m.mode != MusterMode.roll or m.status not in LIVE:
        return 0
    open_ = {e.deployment_id: e for e in entries(db, m) if e.state in OPEN_STATES}
    if not open_:
        return 0
    n = 0
    for r in db.scalars(
        select(GateCheck)
        .join(Gate, Gate.id == GateCheck.gate_id)
        .where(
            Gate.site_id == m.site_id,
            GateCheck.direction == GateDirection.out,
            GateCheck.occurred_at > m.opened_at,
            GateCheck.occurred_at <= (at or now()),
            GateCheck.deployment_id.in_(list(open_)),
        )
    ):
        e = open_.get(r.deployment_id)  # type: ignore[arg-type]
        if e is None or e.state not in OPEN_STATES:
            continue
        e.state, e.at, e.method = ES.accounted, r.occurred_at, EntryMethod.exit_scan
        n += 1
    if n:
        db.flush()
        reconcile(db, m)
    return n


# ---- counts helpers ------------------------------------------------------------------------------


def _row_resolved(r: dict[str, Any]) -> int:
    return sum(int(x["count"]) for x in r.get("resolved") or [])


def _row_outstanding(r: dict[str, Any]) -> int:
    return max(int(r.get("expected") or 0) - int(r.get("accounted") or 0) - _row_resolved(r), 0)


def found_on_site(db: Session, m: Muster) -> bool:
    if any(e.resolution_reason == ResolutionReason.found_on_site for e in entries(db, m)):
        return True
    return any(
        x["reason"] == ResolutionReason.found_on_site.value
        for r in m.counts or []
        for x in r.get("resolved") or []
    )


def reconcile(db: Session, m: Muster) -> bool:
    """MU-7: every expected entry and count row accounted or resolved → Reconciled with
    headcount_complete_at = the time of the last accounting / resolution."""
    if m.status != MusterStatus.open:
        return False
    times: list[datetime] = []
    if m.mode == MusterMode.roll:
        es = entries(db, m)
        if any(e.state in OPEN_STATES for e in es):
            return False
        times = [e.at for e in es if e.at is not None and not e.extra]
    else:
        rows = m.counts or []
        if not rows or any(_row_outstanding(r) > 0 for r in rows):
            return False
        for r in rows:
            for x in [r, *(r.get("resolved") or [])]:
                at = ec.dt(x.get("at"))
                if at is not None:
                    times.append(at)
    m.headcount_complete_at = max(times) if times else now()
    m.status = MusterStatus.reconciled
    db.flush()
    _to_source(db, m)
    return True


def _to_source(db: Session, m: Muster) -> None:
    if m.source_type == MusterSource.drill:
        d = db.get(Drill, m.source_id)
        if d is not None:
            tl = dict(d.timeline or {})
            tl["headcount_complete_at"] = (
                m.headcount_complete_at.isoformat() if m.headcount_complete_at else None
            )
            d.timeline = tl


def close(db: Session, m: Muster, at: datetime) -> None:
    """§4.7: closed at all clear; open entries are left `unaccounted` (MU-8 finding)."""
    if m.status not in LIVE:
        return
    for e in entries(db, m):
        if e.state == ES.expected:
            e.state = ES.unaccounted
    m.status = MusterStatus.closed
    m.closed_at = at
    db.flush()


# ---- reads (P6c-4) -------------------------------------------------------------------------------


def _muster(db: Session, p: Principal, muster_id: uuid.UUID) -> Muster:
    m = db.get(Muster, muster_id)
    if m is None or not p.can_see_project(m.project_id):
        raise not_found("Muster")
    ec.need(p, m.project_id, C.emergency_view, write=False)
    return m


def name_scope(p: Principal, m: Muster) -> tuple[bool, Grant | None]:
    """P6c-4: who sees named entries — (visible, engagement-filter grant)."""
    pid = m.project_id
    if ec.is_hse(p, pid):
        return True, None
    sc = p.projects.get(pid)
    if sc is None or sc.read_only:
        return False, None
    g = p.grant(pid, C.drill_run)
    if g is None:
        return False, None
    if g.engagement_ids is not None:
        return True, g  # Contractor HSE Reps / receivers: their C / C1 scope
    if m.status in LIVE and g.covers_site(m.site_id):
        return True, None
    return False, None


def entry_read(db: Session, e: MusterEntry) -> MusterEntryRead:
    w = ec.worker_of(db, e.deployment_id)
    return MusterEntryRead(
        id=e.id,
        deployment_id=e.deployment_id,
        worker=acommon.worker_ref(w, True) if w else None,
        engagement_code=ec.eng_code(db, e.engagement_id),
        state=e.state,
        at=e.at,
        method=e.method,
        ap_id=e.ap_id,
        resolution_reason=e.resolution_reason,
        note=e.note,
        extra=e.extra,
    )


def muster_read(db: Session, m: Muster, p: Principal | None = None) -> MusterRead:
    es = entries(db, m) if m.purged_at is None else []
    by_state: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    rows: list[MusterCountRow] = []
    if m.purged_at is not None and m.summary:
        by_state.update(m.summary.get("by_state") or {})
        by_reason.update(m.summary.get("by_reason") or {})
    elif m.mode == MusterMode.roll:
        for e in es:
            by_state[e.state.value] += 1
            if e.resolution_reason is not None:
                by_reason[e.resolution_reason.value] += 1
    for r in m.counts or []:
        eid = uuid.UUID(str(r["engagement_id"]))
        res = list(r.get("resolved") or [])
        rows.append(
            MusterCountRow(
                engagement_id=eid,
                engagement_code=ec.eng_code(db, eid),
                expected=int(r.get("expected") or 0),
                accounted=int(r.get("accounted") or 0),
                resolved=res,
                outstanding=_row_outstanding(r),
            )
        )
        if m.purged_at is None and m.mode == MusterMode.count_:
            by_state["accounted"] += int(r.get("accounted") or 0)
            by_state["resolved"] += _row_resolved(r)
            by_state["unaccounted"] += _row_outstanding(r)
            for x in res:
                by_reason[x["reason"]] += int(x["count"])
    expected = (
        sum(int(r.get("expected") or 0) for r in m.counts or [])
        if m.mode == MusterMode.count_
        else (sum(v for k, v in by_state.items()) - m.extras)
    )
    visible_entries: list[MusterEntryRead] | None = None
    if p is not None and m.mode == MusterMode.roll and m.purged_at is None:
        ok, g = name_scope(p, m)
        if ok:
            keep = [e for e in es if g is None or g.covers_engagement(e.engagement_id)]
            visible_entries = [entry_read(db, e) for e in keep]
            if m.status == MusterStatus.closed and keep:
                audit.record(
                    db, AuditAction.sensitive_field_read, p.actor(m.project_id),
                    entity_type=EntityType.emergency_muster, entity_id=m.id,
                    project_id=m.project_id, details={"entries": len(keep)},
                )  # fmt: skip
    return MusterRead(
        id=m.id,
        muster_no=m.muster_no,
        project_id=m.project_id,
        source_type=m.source_type,
        source_id=m.source_id,
        site_id=m.site_id,
        ap_ids=list(m.ap_ids or []),
        mode=m.mode,
        opened_at=m.opened_at,
        expected=expected,
        accounted=by_state["accounted"],
        resolved=by_state["resolved"],
        unaccounted=by_state["unaccounted"] + by_state["expected"],
        extras=m.extras,
        by_state=dict(by_state),
        by_reason=dict(by_reason),
        visitors_expected=m.visitors_expected,
        visitors_accounted=m.visitors_accounted,
        headcount_complete_at=m.headcount_complete_at,
        headcount_min=ec.mstr(ec.minutes(m.opened_at, m.headcount_complete_at)),
        status=m.status,
        entries=visible_entries,
        count_rows=rows,
    )


def read_muster(db: Session, p: Principal, muster_id: uuid.UUID) -> MusterRead:
    m = _muster(db, p, muster_id)
    sync_exits(db, m)
    return muster_read(db, m, p)


# ---- accounting (MU-4…MU-6) ----------------------------------------------------------------------


def _runner(db: Session, p: Principal, m: Muster) -> Grant:
    g = p.require(m.project_id, C.drill_run)
    if not ec.site_in_scope(db, g, m.project_id, m.site_id):
        raise forbidden_error()
    if m.status not in LIVE:
        raise invalid_transition("Muster", m.status, "updated")
    return g


def _deployment_of(db: Session, m: Muster, payload: str) -> Deployment:
    mt = acommon.QR_RE.match(payload.strip())
    if mt is None or mt.group(1) != QrKind.AC.value:
        raise validation_error("payload", "Scan the worker's access card (HSE2:AC:…).")
    t = db.scalar(select(QrToken).where(QrToken.token == mt.group(2), QrToken.kind == QrKind.AC))
    if t is None or t.project_id != m.project_id or t.status != QrTokenStatus.active:
        raise validation_error("payload", "This access card is not active on the project.")
    dep = db.get(Deployment, t.subject_id)
    if dep is None:
        raise not_found("Worker deployment")
    return dep


def account(
    db: Session, m: Muster, dep: Deployment, ap_id: uuid.UUID | None, by: uuid.UUID | None
) -> MusterEntry:
    if m.mode != MusterMode.roll:
        raise invalid_transition("Muster", "count mode", "scanned")
    e = db.scalar(
        select(MusterEntry).where(
            MusterEntry.muster_id == m.id, MusterEntry.deployment_id == dep.id
        )
    )
    at = now()
    if e is None:  # MU-5: not on the roll → accounted extra
        e = MusterEntry(
            id=uuid.uuid4(),
            muster_id=m.id,
            deployment_id=dep.id,
            engagement_id=dep.engagement_id,
            state=ES.accounted,
            at=at,
            by_user_id=by,
            ap_id=ap_id,
            method=EntryMethod.scan,
            extra=True,
        )
        db.add(e)
        m.extras = (m.extras or 0) + 1
    elif e.state in OPEN_STATES:
        e.state, e.at, e.by_user_id, e.ap_id, e.method = (
            ES.accounted,
            at,
            by,
            ap_id,
            EntryMethod.scan,
        )
    db.flush()
    reconcile(db, m)
    return e


def scan(db: Session, p: Principal, muster_id: uuid.UUID, body: ScanInput) -> MusterEntryRead:
    m = _muster(db, p, muster_id)
    _runner(db, p, m)
    if body.ap_id is not None and body.ap_id not in (m.ap_ids or []):
        raise validation_error("ap_id", "Choose an assembly point of the muster.")
    dep = _deployment_of(db, m, body.payload)
    return entry_read(db, account(db, m, dep, body.ap_id, p.user.id))


def _entry(db: Session, m: Muster, entry_id: uuid.UUID) -> MusterEntry:
    e = db.get(MusterEntry, entry_id)
    if e is None or e.muster_id != m.id:
        raise not_found("Muster entry")
    return e


def tick(db: Session, p: Principal, muster_id: uuid.UUID, entry_id: uuid.UUID) -> MusterEntryRead:
    m = _muster(db, p, muster_id)
    _runner(db, p, m)
    e = _entry(db, m, entry_id)
    if e.state not in OPEN_STATES:
        raise invalid_transition("Muster entry", e.state, ES.accounted)
    e.state, e.at, e.by_user_id, e.method = ES.accounted, now(), p.user.id, EntryMethod.tick
    db.flush()
    reconcile(db, m)
    return entry_read(db, e)


def on_found(db: Session, m: Muster, ref_: str) -> None:
    """MU-6: `found_on_site` → a critical drill finding, or an immediate alert in an event."""
    if m.source_type == MusterSource.drill:
        d = db.get(Drill, m.source_id)
        if d is not None:
            add_auto_finding(
                d, FindingCategory.behaviour, FindingSeverity.critical,
                "Person remained in the evacuated area (found on site)",
                "بقي شخص في المنطقة التي تم إخلاؤها", ref_,
            )  # fmt: skip
        return
    ev = db.get(EmergencyEvent, m.source_id)
    ec.send(
        db, ec.managers(db), NotificationKind.emergency_unaccounted,
        f"{ev.event_no if ev else m.muster_no}: a person was found on site in the evacuated area",
        "تم العثور على شخص داخل المنطقة التي تم إخلاؤها",
        m.project_id, EntityType.emergency_event, m.source_id, email=True,
    )  # fmt: skip


def add_auto_finding(
    d: Drill, cat: FindingCategory, sev: FindingSeverity, en: str, ar: str, ref_: str | None
) -> None:
    ev = dict(d.evaluation or {})
    auto = list(ev.get("auto_findings") or [])
    key = f"{cat.value}:{en}:{ref_}"
    if any(x.get("key") == key for x in auto):
        return
    auto.append(
        {"key": key, "category": cat.value, "severity": sev.value, "description_en": en,
         "description_ar": ar, "ref": ref_, "auto": True}
    )  # fmt: skip
    ev["auto_findings"] = auto
    d.evaluation = ev


def resolve(
    db: Session, p: Principal, muster_id: uuid.UUID, entry_id: uuid.UUID, body: ResolveInput
) -> MusterEntryRead:
    m = _muster(db, p, muster_id)
    _runner(db, p, m)
    e = _entry(db, m, entry_id)
    if e.state not in OPEN_STATES:
        raise invalid_transition("Muster entry", e.state, ES.resolved)
    if body.reason == ResolutionReason.record_error and len((body.note or "").strip()) < 10:
        raise validation_error("note", "Explain the record error (at least 10 characters).")
    e.state, e.at, e.by_user_id = ES.resolved, now(), p.user.id
    e.resolution_reason, e.note = body.reason, body.note
    db.flush()
    if body.reason == ResolutionReason.found_on_site:
        w = ec.worker_of(db, e.deployment_id)
        on_found(db, m, w.worker_no if w else m.muster_no)
    reconcile(db, m)
    return entry_read(db, e)


def put_counts(db: Session, p: Principal, muster_id: uuid.UUID, body: CountsInput) -> MusterRead:
    """MU-3: Contractor HSE Rep / receiver (their engagements) or HSE staff (any)."""
    m = _muster(db, p, muster_id)
    g = _runner(db, p, m)
    if m.mode != MusterMode.count_:
        raise invalid_transition("Muster", "roll mode", "counted")
    rows = {str(r["engagement_id"]): dict(r) for r in m.counts or []}
    at = now().isoformat()
    for x in body.rows:
        if not g.covers_engagement(x.engagement_id):
            raise forbidden_error()
        ec.engagement_on(db, m.project_id, x.engagement_id, "rows")
        r = rows.setdefault(
            str(x.engagement_id), {"engagement_id": str(x.engagement_id), "resolved": []}
        )
        if x.accounted > x.expected:
            raise validation_error("rows", "Accounted cannot exceed expected.")
        r.update(expected=x.expected, accounted=x.accounted, by=str(p.user.id), at=at)
    found = False
    for res in body.resolutions:
        if not g.covers_engagement(res.engagement_id):
            raise forbidden_error()
        r = rows.get(str(res.engagement_id))
        if r is None or res.count > _row_outstanding(r):
            raise validation_error("resolutions", "Resolve at most the outstanding count.")
        if res.reason == ResolutionReason.record_error and len((res.note or "").strip()) < 10:
            raise validation_error("resolutions", "Explain the record error (≥ 10 characters).")
        r["resolved"] = [
            *(r.get("resolved") or []),
            {"reason": res.reason.value, "count": res.count, "note": res.note, "at": at},
        ]
        found = found or res.reason == ResolutionReason.found_on_site
    if body.visitors_expected is not None:
        m.visitors_expected = body.visitors_expected
    if body.visitors_accounted is not None:
        m.visitors_accounted = body.visitors_accounted
    m.counts = list(rows.values())
    db.flush()
    if found:
        on_found(db, m, m.muster_no)
    reconcile(db, m)
    return muster_read(db, m, p)


def sheet(db: Session, p: Principal, muster_id: uuid.UUID) -> MusterSheet:
    """MU-9: per engagement, names and worker_no only; each print audited (`export`)."""
    m = _muster(db, p, muster_id)
    g = _runner(db, p, m)
    if m.status != MusterStatus.open or m.mode != MusterMode.roll:
        raise invalid_transition("Muster", m.status, "printed")
    groups: dict[str, list[dict[str, str]]] = {}
    for e in entries(db, m):
        if not g.covers_engagement(e.engagement_id):
            continue
        w = ec.worker_of(db, e.deployment_id)
        if w is None:
            continue
        code = ec.eng_code(db, e.engagement_id) or "-"
        groups.setdefault(code, []).append(
            {"worker_no": w.worker_no, "name_en": w.full_name_en, "name_ar": w.full_name_ar or ""}
        )
    audit.record(
        db, AuditAction.export, p.actor(m.project_id), entity_type=EntityType.emergency_muster,
        entity_id=m.id, project_id=m.project_id,
        details={"sheet": True, "rows": sum(len(v) for v in groups.values())},
    )  # fmt: skip
    return MusterSheet(
        muster_no=m.muster_no,
        generated_at=now(),
        engagements=[{"engagement_code": k, "workers": v} for k, v in sorted(groups.items())],
    )


def void(db: Session, p: Principal, muster_id: uuid.UUID, body: VoidInput) -> MusterRead:
    m = _muster(db, p, muster_id)
    p.require(m.project_id, C.emergency_void)
    if m.status == MusterStatus.voided:
        raise invalid_transition("Muster", m.status, MusterStatus.voided)
    m.status = MusterStatus.voided
    m.closed_at = m.closed_at or now()
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_muster, m.id, m.project_id, None,
        {"status": "voided", "reason": ec.reason(body.reason, 20)},
    )  # fmt: skip
    return muster_read(db, m, p)


# ---- MU-8 timers (emergency_minute) --------------------------------------------------------------


def headcount_timer(db: Session, m: Muster, at: datetime) -> int:
    c = ec.cfg(db, m.project_id)
    due = m.opened_at + timedelta(minutes=int(c["headcount_target_minutes"]))
    if m.status != MusterStatus.open or at < due:
        return 0
    n_open = 0
    if m.mode == MusterMode.roll:
        for e in entries(db, m):
            if e.state == ES.expected:
                e.state = ES.unaccounted
            if e.state == ES.unaccounted:
                n_open += 1
    else:
        n_open = sum(_row_outstanding(r) for r in m.counts or [])
    if not n_open or not ec.once(db, f"mu8:{m.id}"):
        return 0
    aps = _ap_codes(db, m)
    if m.source_type == MusterSource.event:
        ev = db.get(EmergencyEvent, m.source_id)
        if ev is not None and ev.late_entry:
            return 0
        users = (
            ec.managers(db)
            | ec.officers(db, m.project_id)
            | ec.site_engineers(db, m.project_id, m.site_id)
            | ec.coordinators(db, m.project_id, m.site_id, at)
        )
        return ec.send(
            db, users, NotificationKind.emergency_unaccounted,
            f"{n_open} persons unaccounted at {aps} — start search",
            f"يوجد {n_open} أشخاص غير محصورين في {aps} — ابدأ البحث",
            m.project_id, EntityType.emergency_event, m.source_id, email=True,
        )  # fmt: skip
    d = db.get(Drill, m.source_id)
    if d is None or d.late_entry:
        return 0
    return ec.send(
        db, {d.conductor_user_id, *(d.evaluator_user_ids or [])},
        NotificationKind.emergency_unaccounted,
        f"{d.drill_no}: {n_open} persons unaccounted at the headcount target",
        f"{d.drill_no}: يوجد {n_open} أشخاص غير محصورين عند هدف الحصر",
        m.project_id, EntityType.emergency_drill, d.id,
    )  # fmt: skip


def _ap_codes(db: Session, m: Muster) -> str:
    out = []
    for i in m.ap_ids or []:
        a = db.get(AssemblyPoint, i)
        if a is not None:
            out.append(a.ap_code)
    return ", ".join(out) or ec.site_code(db, m.site_id) or ""


# ---- muster_reader devices (2-access-permits v1.5 §3.19, §11.3) ---------------------------------


def device_read(d: MusterDevice) -> MusterDeviceRead:
    return MusterDeviceRead(
        id=d.id,
        ap_id=d.ap_id,
        device_id=d.device_id,
        label=d.label,
        registered_at=d.registered_at,
        last_seen_at=d.last_seen_at,
        revoked_at=d.revoked_at,
    )


def register_device(
    db: Session, p: Principal, project_id: uuid.UUID, body: MusterDeviceCreate
) -> MusterDeviceRegistered:
    ec.project(db, p, project_id)
    p.require(project_id, C.erp_prepare)
    ap = db.get(AssemblyPoint, body.ap_id)
    if ap is None or ap.project_id != project_id or ap.status != ActiveStatus.active:
        raise validation_error("ap_id", "Choose an active assembly point of the project.")
    token = secrets.token_urlsafe(32)
    d = MusterDevice(
        id=uuid.uuid4(),
        project_id=project_id,
        ap_id=ap.id,
        device_id=body.device_id,
        label=body.label,
        token_hash=token_digest(token),
        registered_at=now(),
        registered_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    ec.audit_change(
        db, p, EntityType.muster_device, d.id, project_id, None,
        {"ap": ap.ap_code, "device_id": body.device_id},
    )  # fmt: skip
    return MusterDeviceRegistered(device=device_read(d), device_token=token)


def revoke_device(db: Session, p: Principal, device_pk: uuid.UUID) -> MusterDeviceRead:
    d = db.get(MusterDevice, device_pk)
    if d is None or not p.can_see_project(d.project_id):
        raise not_found("Muster device")
    p.require(d.project_id, C.erp_prepare)
    if d.revoked_at is None:
        d.revoked_at = now()
        db.flush()
        ec.audit_change(
            db, p, EntityType.muster_device, d.id, d.project_id, None, {"revoked": True}
        )
    return device_read(d)


def _unauth() -> ApiError:
    return ApiError(
        401,
        ErrorCode.UNAUTHENTICATED,
        "This muster reader is not registered or was revoked.",
        "جهاز الحصر غير مسجل أو تم إلغاؤه.",
    )


def device_session(db: Session, body: MusterSessionInput) -> MusterSessionRead:
    d = db.scalar(
        select(MusterDevice).where(MusterDevice.token_hash == token_digest(body.device_token))
    )
    if d is None or d.revoked_at is not None:
        raise _unauth()
    ap = db.get(AssemblyPoint, d.ap_id)
    if ap is None:
        raise _unauth()
    at = now()
    d.last_seen_at = at
    s = get_settings()
    token = jwt.encode(
        {
            "sub": str(d.id),
            "sid": str(uuid.uuid4()),
            "typ": "gate",
            "kind": "muster_reader",
            "exp": at + timedelta(hours=12),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    db.flush()
    return MusterSessionRead(access_token=token, ap_id=ap.id, ap_code=ap.ap_code)


def device_scan(db: Session, token: str | None, body: ScanInput) -> MusterEntryRead:
    """MU-4 by a muster_reader: only for its own assembly point (else 403)."""
    claims = decode_jwt(token) if token else None
    if not claims or claims.get("kind") != "muster_reader":
        raise _unauth()
    try:
        dpk = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise _unauth() from exc
    d = db.get(MusterDevice, dpk)
    if d is None or d.revoked_at is not None:
        raise _unauth()
    if body.ap_id is not None and body.ap_id != d.ap_id:
        raise forbidden_error("This reader is bound to another assembly point.")
    d.last_seen_at = now()
    m = db.scalar(
        select(Muster)
        .where(
            Muster.project_id == d.project_id,
            Muster.status.in_(LIVE),
            Muster.ap_ids.any(d.ap_id),  # type: ignore[arg-type]
        )
        .order_by(Muster.opened_at.desc())
    )
    if m is None:
        raise forbidden_error("No open muster at this assembly point.")
    dep = _deployment_of(db, m, body.payload)
    return entry_read(db, account(db, m, dep, d.ap_id, None))
