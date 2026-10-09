"""Notification requirements (spec 6f-incident-followup §3.3, §4.1, §6.1, NR-1…NR-10, §7).

Derivation (`derive`) runs from `followup_minute` (within 60 s of any change) and right after a
6f write. NR-5 clock: the first derivation of an incident stamps every true trigger with
occurred_at (it was true at Reported); a trigger that becomes true later is stamped with the time
of that derivation. A reclassification never moves an existing requirement's due time."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, ZoneType
from app.core.errors import ErrorCode, not_found
from app.core.followup_enums import (
    FuDeadlineBasis,
    FuFiler,
    FuForm,
    FuPackStatus,
    FuRequirementStatus,
    FuStage,
    FuSubmissionStatus,
    FuWaiverReason,
)
from app.core.followup_enums import FuTrigger as T
from app.core.hse_enums import (
    AttachmentOwner,
    CaseCategory,
    DangerousOccurrenceCategory,
    EnvReached,
    ExternalBody,
    IncidentStatus,
    IncidentType,
    PermanentDisability,
    PersonType,
)
from app.models import (
    FuIncidentClock,
    FuPack,
    FuRequirement,
    FuRule,
    FuSubmission,
    Incident,
    InjuryCase,
    Investigation,
    Zone,
)
from app.schemas.followup import FuRequirementPage, FuRequirementRead, FuWaiverRequest
from app.services.followup import common as fc
from app.services.permissions import Grant, Principal

C = Capability
NK = NotificationKind
ET = EntityType
RS = FuRequirementStatus
RECORDABLE = {CaseCategory.FAT, CaseCategory.LTI, CaseCategory.RWC, CaseCategory.JTC,
              CaseCategory.MTC}  # fmt: skip
CASE_TRIGGERS = {
    T.recordable_contractor_case, T.commuting_case, T.fatality, T.permanent_disability, T.lti,
    T.any_recordable_case,
}  # fmt: skip


# ---- triggers (list NT) --------------------------------------------------------------------------


def _case_true(c: InjuryCase, t: T) -> bool:
    cat = c.category
    if t == T.recordable_contractor_case:
        return c.person_type == PersonType.contractor_worker and cat in RECORDABLE
    if t == T.commuting_case:
        return bool(c.commuting)
    if t == T.fatality:
        return cat == CaseCategory.FAT
    if t == T.permanent_disability:
        return c.permanent_disability != PermanentDisability.none
    if t == T.lti:
        return cat == CaseCategory.LTI
    if t == T.any_recordable_case:
        return cat in RECORDABLE
    return False


def _env_on(db: Session, inc: Incident) -> bool:
    from app.services.env import common as env_common  # noqa: PLC0415

    start = env_common.cfg(db, inc.project_id).notifications_from
    return (
        IncidentType.environmental.value in (inc.incident_types or [])
        and start is not None
        and inc.occurred_date >= start
    )


def _incident_true(db: Session, inc: Incident, t: T, params: dict[str, Any]) -> bool:
    from app.services.incidents import GACA_FLAGS  # noqa: PLC0415

    flags = set(inc.airside_flags or [])
    if t == T.fire_explosion_do:
        return inc.do_category == DangerousOccurrenceCategory.fire_explosion
    if t == T.any_do:
        return IncidentType.dangerous_occurrence.value in (inc.incident_types or [])
    if t == T.hipo:
        return bool(inc.hipo)
    if t == T.gaca_airside_flag:
        return bool(flags & {f.value for f in GACA_FLAGS})
    if t == T.any_airside_flag:
        return bool(flags)
    if t == T.env_ncec:
        return _env_on(db, inc) and (
            inc.env_reached in (EnvReached.drain, EnvReached.water_body)
            or (inc.actual_severity or 0) >= 3
        )
    if t == T.env_airside:
        z = db.get(Zone, inc.zone_id) if inc.zone_id else None
        return _env_on(db, inc) and z is not None and z.zone_type == ZoneType.airside
    if t == T.property_damage_ge_sar:
        limit = Decimal(str(params.get("property_damage_ge_sar", "50000")))
        return (inc.pd_estimated_cost_sar or Decimal(0)) >= limit
    return False


def true_keys(
    db: Session, inc: Incident, cases: Sequence[InjuryCase], rules: list[FuRule]
) -> set[str]:
    """Clock keys of the triggers true now: `<trigger>:P<n>` for case triggers, `<trigger>` else."""
    if inc.status in (IncidentStatus.draft, IncidentStatus.voided):
        return set()
    out: set[str] = set()
    wanted = {T(t) for r in rules for t in r.triggers}
    params: dict[str, Any] = {}
    for r in rules:
        params.update(r.trigger_params or {})
    for t in wanted:
        if t in CASE_TRIGGERS:
            out |= {f"{t.value}:P{c.person_no}" for c in cases if _case_true(c, t)}
        elif _incident_true(db, inc, t, params):
            out.add(t.value)
    return out


def _per_case(r: FuRule) -> bool:
    """NR-2 / NR-6: GOSI and MHRSD-F rows produce one requirement per triggering case."""
    return r.body == ExternalBody.gosi or r.rule_code == "MHRSD-F"


def _matches(r: FuRule, keys: set[str], case_key: str | None) -> list[str]:
    trig = set(r.triggers)
    out = []
    for k in keys:
        base, _, ck = k.partition(":")
        if base not in trig:
            continue
        if case_key is not None and ck != case_key:
            continue
        out.append(k)
    return out


def _main_contractor(db: Session, eng_id: uuid.UUID | None) -> uuid.UUID | None:
    from app.services.field.common import tier1_of  # noqa: PLC0415

    return tier1_of(db, eng_id) if eng_id else None


def _due(
    db: Session, inc: Incident, r: FuRule, cases: Sequence[InjuryCase], met: datetime
) -> datetime:
    """§6.1."""
    if r.deadline_basis == FuDeadlineBasis.investigation_due:
        inv = db.get(Investigation, inc.id)
        if inv is not None and inv.due_date is not None:
            d = inv.due_date
        else:
            from app.services.incidents import DUE_DAYS, minimum_level  # noqa: PLC0415

            d = inc.occurred_date + timedelta(days=DUE_DAYS[minimum_level(inc, cases)])
        return fc.end_of_day(d)
    return met + timedelta(hours=r.deadline_hours or 0)


@dataclass
class Derived:
    created: list[FuRequirement]
    released: list[FuRequirement]


def derive(db: Session, inc: Incident, at: datetime | None = None) -> Derived:
    """NR-1…NR-7 for one incident under the profile."""
    t = at or now()
    out = Derived([], [])
    if not fc.under_profile(db, inc):
        return out
    rules = list(fc.ensure_profile(db, inc.project_id))
    cases = list(
        db.scalars(
            select(InjuryCase)
            .where(InjuryCase.incident_id == inc.id)
            .order_by(InjuryCase.person_no)
        )
    )
    clock = db.get(FuIncidentClock, inc.id)
    first = clock is None
    if clock is None:
        if inc.status in (IncidentStatus.draft,):
            return out
        clock = FuIncidentClock(incident_id=inc.id, project_id=inc.project_id, trigger_times={})
        db.add(clock)
    keys = true_keys(db, inc, cases, rules)
    times = dict(clock.trigger_times or {})
    for k in keys:
        if k not in times:
            times[k] = (inc.occurred_at if first else t).isoformat()
    clock.trigger_times = times
    clock.derived_at = t
    existing = {
        (r.rule_code, r.case_key): r
        for r in db.scalars(select(FuRequirement).where(FuRequirement.incident_id == inc.id))
    }
    seen: set[tuple[str, str]] = set()
    by_no = {f"P{c.person_no}": c for c in cases}
    for r in rules:
        groups: list[tuple[str, list[str]]] = []
        if _per_case(r):
            for ck in sorted({k.partition(":")[2] for k in _matches(r, keys, None) if ":" in k}):
                groups.append((ck, _matches(r, keys, ck)))
        else:
            hit = _matches(r, keys, None)
            if hit:
                groups.append(("", hit))
        for ck, hit in groups:
            seen.add((r.rule_code, ck))
            req = existing.get((r.rule_code, ck))
            if req is not None:
                if not req.required:
                    req.required = True
                    req.not_required_at = None
                    req.trigger_note = None
                continue
            if not r.active:
                continue
            met = min(datetime.fromisoformat(times[k]) for k in hit)
            case = by_no.get(ck)
            filer_eng = (
                case.employer_engagement_id
                if case is not None and r.filer == FuFiler.employer_engagement
                else _main_contractor(db, inc.responsible_engagement_id)
            )
            req = FuRequirement(
                project_id=inc.project_id, incident_id=inc.id, rule_code=r.rule_code, case_key=ck,
                body=r.body, stage=r.stage, source=r.source, form_code=r.form_code, filer=r.filer,
                trigger_met_at=met, due_at=_due(db, inc, r, cases, met),
                deadline_hours=r.deadline_hours,
                filer_engagement_id=filer_eng,
                responsible_engagement_id=(filer_eng if r.body == ExternalBody.gosi
                                           else inc.responsible_engagement_id),
                case_ids=[case.id] if case is not None else [
                    c.id for c in cases if any(k.endswith(f":P{c.person_no}") for k in hit)],
                required=True, alerts_sent=[], seed_fake=bool(inc.seed_fake),
            )  # fmt: skip
            db.add(req)
            out.created.append(req)
    valid = _valid_subs(db, [r.id for r in existing.values()])
    for key, req in existing.items():
        if key in seen or not req.required:
            continue
        if valid.get(req.id):
            req.trigger_note = "Trigger no longer applies"
            continue
        req.required = False
        req.not_required_at = t
        req.trigger_note = FuWaiverReason.incident_reclassified.value
        out.released.append(req)
    db.flush()
    for req in out.created:
        creation_alert(db, inc, req)
    return out


def _valid_subs(db: Session, req_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[FuSubmission]]:
    out: dict[uuid.UUID, list[FuSubmission]] = {}
    if not req_ids:
        return out
    for s in db.scalars(
        select(FuSubmission)
        .where(
            FuSubmission.requirement_id.in_(req_ids),
            FuSubmission.status != FuSubmissionStatus.voided,
        )
        .order_by(FuSubmission.submitted_at)
    ):
        out.setdefault(s.requirement_id, []).append(s)
    return out


def derive_project(db: Session, project_id: uuid.UUID, at: datetime | None = None) -> int:
    c = fc.cfg(db, project_id)
    if c.rules_from is None:
        return 0
    n = 0
    for inc in db.scalars(
        select(Incident).where(
            Incident.project_id == project_id,
            Incident.occurred_date >= c.rules_from,
            Incident.status != IncidentStatus.draft,
        )
    ):
        d = derive(db, inc, at)
        n += len(d.created)
    return n


# ---- status (§4.1) -------------------------------------------------------------------------------


def status_of(req: FuRequirement, subs: list[FuSubmission], at: datetime) -> RS:
    if req.waived_at is not None:
        return RS.waived
    if subs:
        return RS.acknowledged if any(s.acknowledged_at for s in subs) else RS.submitted
    if not req.required:
        return RS.not_required
    return RS.overdue if at > req.due_at else RS.due


def is_open(req: FuRequirement, subs: list[FuSubmission]) -> bool:
    return req.required and req.waived_at is None and not subs


# ---- alerts (§7) ---------------------------------------------------------------------------------


def recipients(
    db: Session, inc: Incident, req: FuRequirement, overdue: bool = False
) -> set[uuid.UUID]:
    pid = inc.project_id
    who = set(fc.officers(db, pid))
    if req.stage == FuStage.verbal:
        who |= fc.managers(db)
        who |= fc.reps(db, pid, inc.responsible_engagement_id)
    if req.body == ExternalBody.gosi:
        who |= fc.reps(db, pid, req.filer_engagement_id)
    if overdue:
        who |= fc.managers(db)
    return who


def _label(req: FuRequirement, inc: Incident) -> tuple[str, str]:
    return (f"{inc.ref}: {req.rule_code} ({req.body.value} · {req.stage.value})",
            f"{inc.ref}: {req.rule_code}")  # fmt: skip


def creation_alert(db: Session, inc: Incident, req: FuRequirement) -> None:
    if not fc.once(db, f"fu:req:{req.id}:created"):
        return
    en, ar = _label(req, inc)
    due = fc.to_local(req.due_at)
    fc.send(
        db, recipients(db, inc, req), NK.followup_requirement,
        f"{en} required, due {due:%Y-%m-%d %H:%M}", f"{ar} مطلوب، الموعد {due:%Y-%m-%d %H:%M}",
        inc.project_id, ET.followup_requirement, req.id, email=True,
    )  # fmt: skip


def pre_due_at(db: Session, req: FuRequirement) -> datetime:
    """§6.1: due − lead hours for windows ≥ 24 h, else due − 25 % of the window."""
    window = req.due_at - req.trigger_met_at
    if window >= timedelta(hours=24):
        lead = int(fc.cfg(db, req.project_id)["notification_alert_lead_hours"])
        return req.due_at - timedelta(hours=lead)
    return req.due_at - window / 4


def run_alerts(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """Pre-due and overdue alerts (followup_minute); daily overdue repeats at 07:10."""
    n = 0
    rows = list(
        db.scalars(
            select(FuRequirement).where(
                FuRequirement.project_id == project_id,
                FuRequirement.required.is_(True),
                FuRequirement.waived_at.is_(None),
            )
        )
    )
    subs = _valid_subs(db, [r.id for r in rows])
    for req in rows:
        if subs.get(req.id):
            continue
        inc = db.get(Incident, req.incident_id)
        if inc is None:
            continue
        en, ar = _label(req, inc)
        if at >= req.due_at:
            if fc.once(db, f"fu:req:{req.id}:overdue"):
                n += fc.send(
                    db, recipients(db, inc, req, overdue=True), NK.followup_requirement,
                    f"{en} is overdue", f"{ar} متأخر", project_id, ET.followup_requirement,
                    req.id, email=True,
                )  # fmt: skip
        elif at >= pre_due_at(db, req) and fc.once(db, f"fu:req:{req.id}:pre"):
            n += fc.send(
                db, recipients(db, inc, req), NK.followup_requirement,
                f"{en} due at {fc.to_local(req.due_at):%Y-%m-%d %H:%M}",
                f"{ar} يستحق قريباً", project_id, ET.followup_requirement, req.id, email=True,
            )  # fmt: skip
    return n


def daily_overdue(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    n = 0
    day = fc.local_day(at)
    rows = list(
        db.scalars(
            select(FuRequirement).where(
                FuRequirement.project_id == project_id,
                FuRequirement.required.is_(True),
                FuRequirement.waived_at.is_(None),
                FuRequirement.due_at < at,
            )
        )
    )
    subs = _valid_subs(db, [r.id for r in rows])
    for req in rows:
        if subs.get(req.id) or fc.local_day(req.due_at) >= day:
            continue
        inc = db.get(Incident, req.incident_id)
        if inc is None or not fc.once(db, f"fu:req:{req.id}:daily:{day.isoformat()}"):
            continue
        en, ar = _label(req, inc)
        n += fc.send(
            db, recipients(db, inc, req, overdue=True), NK.followup_requirement,
            f"{en} is still overdue", f"{ar} لا يزال متأخراً", project_id,
            ET.followup_requirement, req.id, email=True,
        )  # fmt: skip
    return n


# ---- reads ---------------------------------------------------------------------------------------


def _current_pack(db: Session, req_id: uuid.UUID) -> FuPack | None:
    return db.scalars(
        select(FuPack)
        .where(FuPack.requirement_id == req_id, FuPack.status != FuPackStatus.superseded)
        .order_by(FuPack.version.desc())
    ).first()


def to_read(
    db: Session,
    req: FuRequirement,
    subs: list[FuSubmission] | None = None,
    at: datetime | None = None,
) -> FuRequirementRead:
    inc = db.get(Incident, req.incident_id)
    s = subs if subs is not None else _valid_subs(db, [req.id]).get(req.id, [])
    first = s[0] if s else None
    pk = _current_pack(db, req.id)
    cases = [db.get(InjuryCase, cid) for cid in req.case_ids or []]
    return FuRequirementRead(
        id=req.id, project_id=req.project_id, incident_id=req.incident_id,
        incident_ref=inc.ref if inc else "?", rule_code=req.rule_code, body=req.body,
        stage=req.stage, source=req.source,
        form_code=FuForm(req.form_code) if req.form_code else None, filer=req.filer,
        case_labels=[f"P{c.person_no}" for c in cases if c is not None],
        trigger_met_at=req.trigger_met_at, due_at=req.due_at,
        filer_engagement_id=req.filer_engagement_id,
        filer_code=fc.eng_code(db, req.filer_engagement_id),
        responsible_code=fc.eng_code(db, req.responsible_engagement_id),
        status=status_of(req, s, at or now()), trigger_note=req.trigger_note,
        waiver_reason_code=req.waiver_reason_code, waiver_text=req.waiver_text,
        waiver_reference=req.waiver_reference, waived_at=req.waived_at,
        submission_no=first.submission_no if first else None,
        submitted_at=first.submitted_at if first else None,
        on_time=first.on_time if first else None,
        reference_no=first.reference_no if first else None,
        acknowledged_at=next((x.acknowledged_at for x in s if x.acknowledged_at), None),
        pack_id=pk.id if pk else None, pack_no=pk.pack_no if pk else None,
        pack_status=pk.status if pk else None,
    )  # fmt: skip


def scope_ok(g: Grant, inc: Incident, req: FuRequirement) -> bool:
    if not g.covers_site(inc.site_id):
        return False
    if g.engagement_ids is None:
        return True
    return any(
        e is not None and g.covers_engagement(e)
        for e in (inc.responsible_engagement_id, req.filer_engagement_id)
    )


def get_req(
    db: Session, p: Principal, req_id: uuid.UUID, cap: Capability = C.followup_view
) -> tuple[FuRequirement, Incident]:
    req = db.get(FuRequirement, req_id)
    if req is None or not p.can_see_project(req.project_id):
        raise not_found("Notification requirement")
    inc = db.get(Incident, req.incident_id)
    assert inc is not None  # noqa: S101
    g = p.grant(req.project_id, cap)
    if g is None:
        v = p.grant(req.project_id, C.followup_view)
        if v is None or not scope_ok(v, inc, req):
            raise not_found("Notification requirement")
        p.require(req.project_id, cap)  # 403 with the right code
    elif not scope_ok(g, inc, req):
        raise not_found("Notification requirement")
    return req, inc


def list_requirements(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    bodies: list[ExternalBody] | None,
    stages: list[FuStage] | None,
    statuses: list[RS] | None,
    engagement_id: uuid.UUID | None,
    incident_id: uuid.UUID | None,
    page: int,
    size: int,
) -> FuRequirementPage:
    g = fc.view_grant(db, p, project_id)
    stmt = select(FuRequirement).where(FuRequirement.project_id == project_id)
    if bodies:
        stmt = stmt.where(FuRequirement.body.in_(bodies))
    if stages:
        stmt = stmt.where(FuRequirement.stage.in_(stages))
    if incident_id:
        stmt = stmt.where(FuRequirement.incident_id == incident_id)
    rows = list(db.scalars(stmt.order_by(FuRequirement.due_at, FuRequirement.rule_code)))
    subs = _valid_subs(db, [r.id for r in rows])
    t = now()
    tree = fc.descendants(db, engagement_id) if engagement_id else None
    out = []
    for r in rows:
        inc = db.get(Incident, r.incident_id)
        if inc is None or not scope_ok(g, inc, r):
            continue
        attributed = r.filer_engagement_id if r.body == ExternalBody.gosi else (
            inc.responsible_engagement_id)  # fmt: skip
        if tree is not None and attributed not in tree:
            continue
        st = status_of(r, subs.get(r.id, []), t)
        if statuses and st not in statuses:
            continue
        out.append((r, subs.get(r.id, [])))
    items = [to_read(db, r, s, t) for r, s in out[(page - 1) * size : page * size]]
    return FuRequirementPage(items=items, total=len(out), page=page, page_size=size)


def read_requirement(db: Session, p: Principal, req_id: uuid.UUID) -> FuRequirementRead:
    req, _inc = get_req(db, p, req_id)
    return to_read(db, req)


def waive(db: Session, p: Principal, req_id: uuid.UUID, body: FuWaiverRequest) -> FuRequirementRead:
    """NR-8 (218 only)."""
    req, _inc = get_req(db, p, req_id)
    p.require(req.project_id, C.followup_settings)
    if body.reason_code == FuWaiverReason.incident_reclassified:
        raise fc.code_err(ErrorCode.VALIDATION_ERROR, "incident_reclassified is set by the system.",
                          "يُحدد هذا السبب من النظام.", "reason_code")  # fmt: skip
    if _valid_subs(db, [req.id]).get(req.id) or req.waived_at is not None:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Requirement", "submitted", "waived")
    needs_file = body.reason_code in (
        FuWaiverReason.body_confirmed_not_required,
        FuWaiverReason.reported_by_other_party,
    )
    if (needs_file and body.evidence_file is None) or (
        body.reason_code == FuWaiverReason.reported_by_other_party and not body.reference
    ):
        raise fc.code_err(
            ErrorCode.WAIVER_EVIDENCE_REQUIRED,
            "Attach the written confirmation (and, when another party filed, its reference).",
            "أرفق الإثبات المكتوب ومرجع الطرف الآخر.",
            "evidence_file" if needs_file and body.evidence_file is None else "reference",
        )
    if body.evidence_file is not None:
        req.waiver_file_id = fc.store_file(
            db, body.evidence_file, AttachmentOwner.fu_evidence, req.id, req.project_id,
            p.user.id, "evidence_file",
        )  # fmt: skip
    req.waiver_reason_code = body.reason_code
    req.waiver_text = body.text
    req.waiver_reference = body.reference
    req.waived_by_user_id = p.user.id
    req.waived_at = now()
    req.updated_by_user_id = p.user.id
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.followup_requirement, req, req.project_id,
              details={"waived": body.reason_code.value})  # fmt: skip
    return to_read(db, req)


# ---- Phase 1 read model (1-dashboard v1.9 §3.3) --------------------------------------------------


def open_by_body(db: Session, inc: Incident) -> dict[ExternalBody, tuple[str, datetime]]:
    """Bodies with an open requirement → (rule codes, earliest due) for the Phase 1 views."""
    rows = list(db.scalars(select(FuRequirement).where(FuRequirement.incident_id == inc.id)))
    subs = _valid_subs(db, [r.id for r in rows])
    out: dict[ExternalBody, tuple[str, datetime]] = {}
    for r in sorted(rows, key=lambda x: x.due_at):
        if not is_open(r, subs.get(r.id, [])):
            continue
        if r.body in out:
            codes, due = out[r.body]
            out[r.body] = (f"{codes}, {r.rule_code}", due)
        else:
            out[r.body] = (r.rule_code, r.due_at)
    return out


def phase1_reads(db: Session, inc: Incident, refs: Any, at: datetime) -> list[Any]:
    from app.core.hse_enums import NotificationState  # noqa: PLC0415
    from app.schemas.incidents import ExternalNotificationRead  # noqa: PLC0415

    rows = sorted(
        db.scalars(select(FuRequirement).where(FuRequirement.incident_id == inc.id)),
        key=lambda r: (r.due_at, r.rule_code),
    )
    subs = _valid_subs(db, [r.id for r in rows])
    out = []
    for r in rows:
        s = subs.get(r.id, [])
        st = status_of(r, s, at)
        state = {RS.due: NotificationState.due, RS.overdue: NotificationState.overdue}.get(
            st, NotificationState.done if s else None
        )
        first = s[0] if s else None
        out.append(
            ExternalNotificationRead(
                body=r.body, required=r.required and r.waived_at is None,
                required_reason=f"{r.rule_code} ({r.source.value})", due_at=r.due_at, state=state,
                notified_at=first.submitted_at if first else None,
                reference_no=first.reference_no if first else None,
                notified_by=refs.user(first.created_by_user_id) if first else None,
                stage=r.stage, rule_code=r.rule_code, requirement_id=r.id, followup_status=st,
            )
        )  # fmt: skip
    return out


def phase1_required(inc: Incident) -> list[Any] | None:
    """I-20 under the profile (1-dashboard v1.9 §11.2): one Phase 1 item per body with a required,
    unwaived requirement, due at the earliest such due time; None when the incident is not under
    the profile (the Phase 1 rules apply)."""
    from sqlalchemy.orm import object_session  # noqa: PLC0415

    from app.services.incidents import Required  # noqa: PLC0415

    db = object_session(inc)
    if db is None or not fc.under_profile(db, inc):
        return None
    if inc.status in (IncidentStatus.draft, IncidentStatus.voided):
        return []
    out: dict[ExternalBody, Any] = {}
    for r in sorted(
        db.scalars(select(FuRequirement).where(FuRequirement.incident_id == inc.id)),
        key=lambda x: (x.due_at, x.rule_code),
    ):
        if not r.required or r.waived_at is not None:
            continue
        if r.body in out:
            out[r.body].reason += f", {r.rule_code}"
        else:
            out[r.body] = Required(r.body, r.rule_code, r.due_at)
    order = list(ExternalBody)
    return sorted(out.values(), key=lambda x: order.index(x.body))
