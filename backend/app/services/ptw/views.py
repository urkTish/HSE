# ruff: noqa: E501
"""Read models of permits (spec 3-ptw §3.5-§3.7, §3.13, §3.14, PT-19, HK3-4): the full permit
with sections, checklists, links, gas state, shifts and the caller's allowed actions; list
items; shift, suspension, handover, exemption, signature and crew reads."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, RequirementKind
from app.core.clock import now
from app.core.enums import Capability, Role
from app.core.ptw_enums import (
    KEY_CREW_ROLES,
    PERMIT_TERMINAL,
    ChecklistAnswer,
    ChecklistKind,
    ClosureItem,
    CrewLineStatus,
    GasStatus,
    PauseReason,
    PermitAction,
    PermitStatus,
    PermitType,
    PreIssueItem,
    PtwCrewRole,
    StatusReason,
)
from app.models import (
    GasDetector,
    Incident,
    Investigation,
    IsolationPoint,
    Jsa,
    NotamRequest,
    ObstacleClearance,
    Permit,
    PermitDocument,
    PermitEquipment,
    PermitExemption,
    PermitHandover,
    PermitRecord,
    PermitShift,
    PermitSignature,
    PermitSuspension,
    PtwAppointment,
    Vehicle,
    Wap,
    Worker,
)
from app.schemas import permits as sch
from app.schemas.access_common import HookCondition
from app.schemas.ptw_common import SignatureRead
from app.services.access import common as acommon
from app.services.hse_common import Refs, user_roles
from app.services.permissions import Principal
from app.services.ptw import common, evaluation, rules
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref
from app.services.ptw.appointments import appointment_ref

T = PermitType
S = PermitStatus
A = PermitAction
C = Capability

SECTION_INPUT: dict[str, Any] = {
    T.hot_work.value: sch.HotWorkSectionInput,
    T.confined_space.value: sch.ConfinedSpaceSectionInput,
    T.work_at_height.value: sch.WorkAtHeightSectionInput,
    T.excavation.value: sch.ExcavationSectionInput,
    T.electrical_isolation.value: sch.ElectricalSectionInput,
    T.lifting.value: sch.LiftingSectionInput,
    T.radiography.value: sch.RadiographySectionInput,
    T.airside_works.value: sch.AirsideSectionInput,
}
SECTION_ORDER = [t.value for t in PermitType]


def names_ok(p: Principal | None, project_id: uuid.UUID) -> bool:
    return acommon.can_see_names(p, project_id)


def medical_ok(p: Principal | None, project_id: uuid.UUID) -> bool:
    """HK3-4 as revised by 6a HK6-7: kind and code of medical results for capability 156."""
    if p is None:
        return True
    return p.grant(project_id, C.fitness_functional_view) is not None


def clinical_ok(p: Principal | None, project_id: uuid.UUID | None) -> bool:
    """6a HK6-7: the medical hook reason_code for capability 157 only."""
    if p is None or project_id is None:
        return p is None
    return p.grant(project_id, C.fitness_clinical_view) is not None


def _worker(db: Session, wid: uuid.UUID | None, names: bool) -> Any:
    if wid is None or not names:
        return None
    w = db.get(Worker, wid)
    return acommon.worker_ref(w, True) if w else None


# ---- crew / equipment / documents ----------------------------------------------------------------


def _eligibility(
    items: list[dict[str, Any]], medical: bool, clinical: bool = False
) -> list[sch.CrewEligibilityItem]:
    out = []
    for it in items or []:
        d = dict(it)
        zid = d.pop("zone_id", None)
        if d.get("hook_kind") == HookKind.medical_fitness.value and not medical:
            bad = d.get("status") in ("not_met", "not_evaluated")
            d = {
                "kind": RequirementKind.hook.value,
                "code": None,
                "hook_kind": None,
                "status": d.get("status"),
                "valid_until": None,
                "ref": None,
                "reason_code": None,
                "message_en": "Not eligible — HSE check" if bad else None,
                "message_ar": "غير مؤهل — مراجعة السلامة" if bad else None,
            }
            out.append(
                sch.CrewEligibilityItem(**d, zone_id=uuid.UUID(zid) if zid else None, redacted=True)
            )
            continue
        if d.get("hook_kind") == HookKind.medical_fitness.value:
            d["reason_code"] = None  # AC99 / HK3-4: kind and code only, never the reason
            if not clinical:
                d["hook_reason_code"] = None  # 6a HK6-7: the reason for 157 holders only
        out.append(sch.CrewEligibilityItem(**d, zone_id=uuid.UUID(zid) if zid else None))
    return out


def crew_read(
    db: Session,
    p: Principal | None,
    line: Any,
    shift: PermitShift | None = None,
    names: bool | None = None,
    medical: bool | None = None,
) -> sch.PermitCrewRead:
    permit = db.get(Permit, line.permit_id)
    pid = permit.project_id if permit else None
    names = names_ok(p, pid) if names is None and pid else bool(names)
    medical = medical_ok(p, pid) if medical is None and pid else bool(medical)
    a = db.get(PtwAppointment, line.appointment_id) if line.appointment_id else None
    redacted_reason = line.excluded_reason
    if not medical and any(
        i.get("hook_kind") == HookKind.medical_fitness.value
        and i.get("status") in ("not_met", "not_evaluated")
        for i in line.eligibility or []
    ):
        redacted_reason = "HSE_CHECK"
    return sch.PermitCrewRead(
        id=line.id,
        worker=_worker(db, line.worker_id, names),
        crew_role=line.crew_role,
        key_role=line.crew_role in KEY_CREW_ROLES,
        appointment=appointment_ref(db, p, a) if a else None,
        escort_worker=_worker(db, line.escort_worker_id, names),
        status=line.status,
        excluded_reason=redacted_reason,
        eligible=line.eligible,
        eligibility=_eligibility(line.eligibility, medical, clinical_ok(p, pid)),
        evaluated_at=line.evaluated_at,
        briefed_current_shift=bool(shift and line.worker_id in (shift.briefed or [])),
    )


def equipment_read(db: Session, e: PermitEquipment, names: bool = False) -> sch.PermitEquipmentRead:
    from app.models import EquipmentDeployment, EquipmentItem  # noqa: PLC0415
    from app.schemas.inductions import EligibilityItem  # noqa: PLC0415
    from app.services.cert import common as ccommon  # noqa: PLC0415

    v = db.get(Vehicle, e.vehicle_id) if e.vehicle_id else None
    tag = (
        sch.EquipmentTagInput(
            category=e.category,
            tag=e.tag,
            description=e.description,
            max_working_height_m=e.max_working_height_m,
        )
        if e.tag and e.category
        else None
    )

    def items(lst: list[dict[str, Any]] | None) -> list[Any]:
        return [
            EligibilityItem(**{k: v2 for k, v2 in it.items() if k != "zone_id"}) for it in lst or []
        ]

    item = db.get(EquipmentItem, e.equipment_item_id) if e.equipment_item_id else None
    dep = db.get(EquipmentDeployment, e.deployment_id) if e.deployment_id else None
    op = db.get(Worker, e.operator_worker_id) if e.operator_worker_id else None
    return sch.PermitEquipmentRead(
        id=e.id,
        vehicle=acommon.vehicle_ref(v) if v else None,
        equipment_tag=tag,
        use=e.use,
        max_working_height_m=e.max_working_height_m
        if e.max_working_height_m is not None
        else (
            Decimal(str(v.max_working_height_m_agl))
            if v and v.max_working_height_m_agl is not None
            else None
        ),
        hooks=items(e.hooks),
        equipment_item=ccommon.equipment_ref(db, item) if item else None,
        deployment=ccommon.deployment_ref(dep) if dep else None,
        operator=acommon.worker_ref(op, names) if op else None,
        operator_hooks=items(e.operator_hooks),
        conditions=[HookCondition(**c) for c in e.conditions or []],
        swl_t=e.swl_t,
    )


def document_read(
    db: Session, d: PermitDocument, refs: Refs, fallback_user: uuid.UUID
) -> sch.PermitDocumentRead:
    by = refs.user(d.added_by_user_id) or refs.user(fallback_user)
    assert by is not None  # noqa: S101
    return sch.PermitDocumentRead(
        id=d.id,
        doc_type=d.doc_type,
        ref=d.ref,
        revision=d.revision,
        attachment_id=d.attachment_id,
        approved_by_text=d.approved_by_text,
        valid_until=d.valid_until,
        added_by=by,
        added_at=d.added_at,
    )


# ---- sections -------------------------------------------------------------------------------------


def _input_fields(t: str, stored: dict[str, Any]) -> dict[str, Any]:
    model = SECTION_INPUT[t]
    return {k: v for k, v in stored.items() if k in model.model_fields}


def _record_user(refs: Refs, r: PermitRecord, fallback: uuid.UUID) -> Any:
    u = refs.user(r.recorded_by_user_id) or refs.user(fallback)
    assert u is not None  # noqa: S101
    return u


def wind_reads(
    db: Session, permit: Permit, f: facts_mod.Facts, refs: Refs
) -> list[sch.WindReadingRead]:
    lim = evaluation.wind_limit(f) if f.has(T.lifting) else rules.WAH_WIND_LIMIT_MS
    out = []
    for r in evaluation.records(db, permit.id, "wind"):
        sp = Decimal(str(r.data["speed_ms"]))
        out.append(
            sch.WindReadingRead(
                id=r.id,
                measured_at=r.at,
                speed_ms=sp,
                source=r.data["source"],
                source_ref=r.data.get("source_ref"),
                limit_ms=lim,
                within_limit=sp <= lim,
                recorded_by=_record_user(refs, r, permit.receiver_user_id),
            )
        )
    return out


def entry_reads(db: Session, permit: Permit, names: bool) -> list[sch.EntryLogRead]:
    return [
        sch.EntryLogRead(
            id=r.id, worker=_worker(db, r.worker_id, names), in_at=r.at, out_at=r.out_at
        )
        for r in evaluation.records(db, permit.id, "entry_log")
    ]


def inspection_read(
    db: Session, p: Principal | None, r: PermitRecord, refs: Refs, fallback: uuid.UUID
) -> sch.ExcavationInspectionRead:
    a = db.get(PtwAppointment, uuid.UUID(r.data["appointment_id"]))
    return sch.ExcavationInspectionRead(
        id=r.id,
        inspected_at=r.at,
        appointment=appointment_ref(db, p, a),
        result=r.data["result"],
        after_rain_or_event=bool(r.data.get("after_rain_or_event")),
        note=r.data.get("note"),
        recorded_by=_record_user(refs, r, fallback),
    )


def survey_read(
    r: PermitRecord, limit: Decimal, refs: Refs, fallback: uuid.UUID
) -> sch.BarrierSurveyRead:
    mx = Decimal(str(r.data["max_usv_h"]))
    return sch.BarrierSurveyRead(
        id=r.id,
        measured_at=r.at,
        max_usv_h=mx,
        meter_tag=r.data["meter_tag"],
        within_limit=mx <= limit,
        recorded_by=_record_user(refs, r, fallback),
    )


def fod_read(
    db: Session, d: dict[str, Any] | None, source: str, names: bool, refs: Refs
) -> sch.PermitFodCheckRead | None:
    if not d or not d.get("checked_at"):
        return None
    wid = d.get("checked_by_worker_id")
    uid = d.get("checked_by_user_id")
    return sch.PermitFodCheckRead(
        checked_by_worker=_worker(db, uuid.UUID(wid), names) if wid else None,
        checked_by_user=refs.user(uuid.UUID(uid)) if uid else None,
        checked_at=datetime.fromisoformat(d["checked_at"]),
        result=d["result"],
        source=source,
    )


def wap_links(db: Session, permit: Permit, f: facts_mod.Facts) -> list[Wap]:
    ids: list[uuid.UUID] = []
    wid = f.sec(T.airside_works).get("wap_id")
    if wid:
        ids.append(uuid.UUID(str(wid)))
    ids += [i for i in permit.linked_wap_ids or [] if i not in ids]
    out = [w for w in (db.get(Wap, i) for i in ids) if w is not None]
    if not out and f.airside:
        w = evaluation.linked_wap(db, permit, f, now())
        if w is not None:
            out.append(w)
    return out


def wap_link_read(w: Wap) -> sch.WapLinkRead:
    return sch.WapLinkRead(
        id=w.id,
        wap_no=w.wap_no,
        status=w.status,
        blockers=[b.get("code") for b in w.blockers or [] if b.get("code")],
    )


def _scaffold(db: Session, permit: Permit, tag: str | None) -> Any:
    """SF-1: scaffold_tag_ref resolved on the Phase 4 register of the permit's project."""
    if not tag:
        return None
    from app.services.cert import common as ccommon  # noqa: PLC0415
    from app.services.cert import providers  # noqa: PLC0415

    sc = providers.find_scaffold(db, permit.project_id, tag)
    return ccommon.scaffold_ref(sc) if sc else None


def section_reads(
    db: Session, p: Principal | None, permit: Permit, f: facts_mod.Facts, refs: Refs, names: bool
) -> list[Any]:
    from app.services.access.works import in_effect  # noqa: PLC0415
    from app.services.ptw import gas, lifecycle  # noqa: PLC0415

    out: list[Any] = []
    s = f.settings
    for t in SECTION_ORDER:
        if t not in f.types or not f.sections.get(t):
            continue
        stored = f.sections[t]
        base = _input_fields(t, stored)
        if t == T.hot_work.value:
            ended = stored.get("hot_work_ended_at")
            fw = stored.get("fire_watch_until")
            latest = permit.valid_to_at - timedelta(minutes=s.fire_watch_post_minutes)
            out.append(
                sch.HotWorkSectionRead(
                    **base,
                    hot_work_ended_at=datetime.fromisoformat(ended) if ended else None,
                    fire_watch_until=datetime.fromisoformat(fw) if fw else None,
                    hot_work_late=bool(ended and datetime.fromisoformat(ended) > latest),
                    latest_compliant_end_at=latest,
                )
            )
        elif t == T.confined_space.value:
            det = (
                db.get(GasDetector, uuid.UUID(str(stored["continuous_monitor_detector_id"])))
                if stored.get("continuous_monitor_detector_id")
                else None
            )
            temps = [
                x.internal_temp_c
                for x in gas.tests_of(db, permit.id)
                if x.internal_temp_c is not None
            ]
            out.append(
                sch.ConfinedSpaceSectionRead(
                    **base,
                    continuous_monitor=gas.detector_ref(det) if det else None,
                    internal_temp_c=temps[-1] if temps else None,
                    persons_inside=len(lifecycle.persons_inside(db, permit.id)),
                    entry_log=entry_reads(db, permit, names),
                )
            )
        elif t == T.work_at_height.value:
            out.append(
                sch.WorkAtHeightSectionRead(
                    **base,
                    scaffold=_scaffold(db, permit, stored.get("scaffold_tag_ref")),
                    required_clearance_m=rules.required_clearance(stored),
                    clearance_ok=rules.clearance_ok(stored),
                )
            )
        elif t == T.excavation.value:
            recs = evaluation.records(db, permit.id, "excavation_inspection")
            out.append(
                sch.ExcavationSectionRead(
                    **base,
                    inspections=[
                        inspection_read(db, p, r, refs, permit.receiver_user_id) for r in recs
                    ],
                    inspected_for_current_shift=lifecycle.excavation_inspected(db, permit, now()),
                )
            )
        elif t == T.electrical_isolation.value:
            out.append(
                sch.ElectricalSectionRead(
                    **base,
                    voltage_class=rules.voltage_class(
                        int(stored.get("system_voltage_v") or 0), bool(stored.get("dc"))
                    ),
                )
            )
        elif t == T.lifting.value:
            lift = f.lift or rules.lift(
                stored, f.zone_facts, s.critical_lift_capacity_pct, s.critical_lift_weight_t
            )
            out.append(
                sch.LiftingSectionRead(
                    **base,
                    gross_t=lift.gross_t,
                    capacity_pct=lift.capacity_display,
                    critical=lift.critical,
                    critical_reasons=lift.reasons,
                    effective_wind_limit_ms=evaluation.wind_limit(f),
                    wind_readings=wind_reads(db, permit, f, refs),
                )
            )
        elif t == T.radiography.value:
            lim = s.rg_barrier_limit_usv_h
            surveys = evaluation.records(db, permit.id, "barrier_survey")
            sr = permit.source_return
            out.append(
                sch.RadiographySectionRead(
                    **base,
                    dose_rate_1m_usv_h=rules.dose_rate_1m(stored).quantize(Decimal("0.1")),
                    computed_barrier_m=rules.barrier_m(stored, lim),
                    barrier_surveys=[
                        survey_read(r, lim, refs, permit.receiver_user_id) for r in surveys
                    ],
                    barrier_verified=bool(surveys)
                    and Decimal(str(surveys[-1].data["max_usv_h"])) <= lim,
                    source_returned=sch.SourceReturnInput(**sr) if sr else None,
                )
            )
        elif t == T.airside_works.value:
            ws = wap_links(db, permit, f)
            w = ws[0] if ws else None
            notams = []
            if w is not None:
                for nid in w.linked_ntm_ids or []:
                    n = db.get(NotamRequest, nid)
                    if n is not None:
                        notams.append(
                            sch.NotamLinkRead(
                                id=n.id,
                                ntm_no=n.ntm_no,
                                status=n.status,
                                in_effect_now=in_effect(n, now()),
                            )
                        )
            fod = fod_read(db, permit.fod_check, "permit", names, refs) or (
                fod_read(db, w.fod_check, "wap", names, refs) if w else None
            )
            out.append(
                sch.AirsideSectionRead(
                    **base,
                    wap=wap_link_read(w) if w else None,
                    notams=notams,
                    fod_check=fod,
                )
            )
    return out


# ---- checklists -----------------------------------------------------------------------------------


def checklist_read(
    db: Session, permit: Permit, kind: ChecklistKind, refs: Refs
) -> sch.ChecklistRead:
    if kind == ChecklistKind.pre_issue:
        items = evaluation.pre_issue_items(db, permit)
    else:
        items = evaluation.closure_items(db, permit)
    answers = (permit.checklists or {}).get(kind.value) or {}
    out = []
    for c in items:
        if kind == ChecklistKind.pre_issue:
            en, ar, na = ref.PRE_ISSUE[PreIssueItem(c)]
            wt = ref.PRE_ISSUE_TYPE.get(PreIssueItem(c))
        else:
            en, ar = ref.CLOSURE[ClosureItem(c)]
            na = True
            wt = ref.CLOSURE_TYPE.get(ClosureItem(c))
        a = answers.get(c.value) or {}
        by = a.get("by_user_id")
        out.append(
            sch.ChecklistItemRead(
                code=c.value,
                work_type=wt,
                label_en=en,
                label_ar=ar,
                na_allowed=na,
                answer=ChecklistAnswer(a["answer"]) if a.get("answer") else None,
                note=a.get("note"),
                answered_by=refs.user(uuid.UUID(by)) if by else None,
                answered_at=datetime.fromisoformat(a["at"]) if a.get("at") else None,
            )
        )
    gaps = evaluation.checklist_gaps(db, permit, kind.value)
    return sch.ChecklistRead(kind=kind, complete=not gaps, items=out)


# ---- shifts / suspensions / handovers / exemptions / signatures ----------------------------------


def shift_read(
    db: Session,
    p: Principal | None,
    s: PermitShift,
    refs: Refs | None = None,
    names: bool | None = None,
) -> sch.PermitShiftRead:
    refs = refs or Refs(db)
    names = names_ok(p, s.project_id) if names is None else names
    pauses = [
        sch.PauseRead(
            from_at=datetime.fromisoformat(x["from"]),
            to_at=datetime.fromisoformat(x["to"]) if x.get("to") else None,
            reason=PauseReason(x["reason"]),
            note=x.get("note"),
        )
        for x in s.pauses or []
    ]
    rec, iss = refs.user(s.receiver_user_id), refs.user(s.issuer_user_id)
    assert rec is not None and iss is not None  # noqa: S101
    return sch.PermitShiftRead(
        id=s.id,
        shift_no=s.shift_no,
        started_at=s.started_at,
        planned_end_at=s.planned_end_at,
        receiver=rec,
        issuer=iss,
        gas_test_id=s.gas_test_id,
        ambient_temp_c=s.ambient_temp_c,
        crew_present=[_worker(db, w, names) for w in s.crew_present or []],
        crew_present_count=len(s.crew_present or []),
        pauses=pauses,
        paused_now=s.ended_at is None and any(x.to_at is None for x in pauses),
        ended_at=s.ended_at,
        end_type=s.end_type,
        gas_compliant=s.gas_compliant if s.gas_required else None,
    )


def suspension_read(sp: PermitSuspension, refs: Refs) -> sch.SuspensionRead:
    return sch.SuspensionRead(
        id=sp.id,
        suspended_at=sp.suspended_at,
        reason=sp.reason,
        routine=sp.routine,
        raised_by=refs.user(sp.raised_by_user_id),
        detail=sp.detail,
        auto_source_ref=sp.auto_source_ref,
        resumed_at=sp.resumed_at,
        resumed_by=refs.user(sp.resumed_by_user_id),
        resume_gas_test_id=sp.resume_gas_test_id,
        cause_cleared_text=sp.cause_cleared_text,
    )


def handover_read(db: Session, h: PermitHandover, refs: Refs) -> sch.HandoverRead:
    sh = db.get(PermitShift, h.from_shift_id)
    fr, tr, ti = (
        refs.user(h.from_receiver_user_id),
        refs.user(h.to_receiver_user_id),
        refs.user(h.to_issuer_user_id),
    )
    assert fr is not None and tr is not None and ti is not None  # noqa: S101
    return sch.HandoverRead(
        id=h.id,
        permit_id=h.permit_id,
        from_shift_no=sh.shift_no if sh else 0,
        from_receiver=fr,
        to_receiver=tr,
        to_issuer=ti,
        initiated_at=h.initiated_at,
        accepted_at=h.accepted_at,
        receiver_signed_at=h.receiver_signed_at,
        issuer_signed_at=h.issuer_signed_at,
        status=h.status,
        notes_en=h.notes_en,
        notes_ar=h.notes_ar,
        deadline_at=h.deadline_at,
    )


def exemption_read(e: PermitExemption, refs: Refs) -> sch.ExemptionRead:
    by = refs.user(e.requested_by_user_id)
    assert by is not None  # noqa: S101
    return sch.ExemptionRead(
        id=e.id,
        permit_id=e.permit_id,
        kind=e.kind,
        status=e.status,
        midday_reason=e.midday_reason,
        reason_text=e.reason_text,
        heat_controls_text=e.heat_controls_text,
        valid_from=e.valid_from,
        valid_to=e.valid_to,
        requested_by=by,
        requested_at=e.requested_at,
        decided_by=refs.user(e.decided_by_user_id),
        decided_at=e.decided_at,
        decision_note=e.decision_note,
    )


def signature_read(db: Session, s: PermitSignature, refs: Refs, names: bool) -> SignatureRead:
    label = None
    if s.worker_id:
        w = db.get(Worker, s.worker_id)
        if w is not None and w.anonymised_at is not None:
            label = f"Anonymised worker {w.worker_no}"
        elif w is not None and names:
            label = f"{w.full_name_en} ({w.worker_no})"
        else:
            label = "Worker"
    a = db.get(PtwAppointment, s.appointment_id) if s.appointment_id else None
    return SignatureRead(
        id=s.id,
        purpose=s.purpose,
        user=refs.user(s.user_id),
        worker_label=label,
        role_label=s.role_label,
        appointment_no=a.appointment_no if a else None,
        signed_at=s.signed_at,
        permit_hash=s.permit_hash,
        co_signed_on_device_of=refs.user(s.co_signed_on_device_of_user_id),
    )


def signatures_of(db: Session, permit: Permit) -> list[PermitSignature]:
    return list(
        db.scalars(
            select(PermitSignature)
            .where(PermitSignature.permit_id == permit.id)
            .order_by(PermitSignature.signed_at)
        )
    )


def suspensions_of(db: Session, permit_id: uuid.UUID) -> list[PermitSuspension]:
    return list(
        db.scalars(
            select(PermitSuspension)
            .where(PermitSuspension.permit_id == permit_id)
            .order_by(PermitSuspension.suspended_at)
        )
    )


def handovers_of(db: Session, permit_id: uuid.UUID) -> list[PermitHandover]:
    return list(
        db.scalars(
            select(PermitHandover)
            .where(PermitHandover.permit_id == permit_id)
            .order_by(PermitHandover.initiated_at)
        )
    )


def exemptions_of(db: Session, permit_id: uuid.UUID) -> list[PermitExemption]:
    return list(
        db.scalars(
            select(PermitExemption)
            .where(PermitExemption.permit_id == permit_id)
            .order_by(PermitExemption.requested_at)
        )
    )


# ---- gas state -------------------------------------------------------------------------------------


def gas_brief(t: Any) -> sch.GasTestBrief | None:
    if t is None:
        return None
    return sch.GasTestBrief(
        id=t.id,
        test_no=t.test_no,
        tested_at=t.tested_at,
        result=t.result.value,
        fail_codes=list(t.fail_codes or []),
    )


def gas_state(db: Session, permit: Permit, f: facts_mod.Facts, at: datetime) -> sch.PermitGasState:
    from app.services.ptw import gas  # noqa: PLC0415

    st = gas.state(db, permit, f.interval, f.gas_required, at)
    shift = evaluation.current_shift(db, permit)
    paused = None
    for x in (shift.pauses if shift else None) or []:
        if not x.get("to"):
            paused = datetime.fromisoformat(x["from"])
    stopped_since = paused
    if permit.status == S.suspended:
        sp = evaluation.open_suspension(db, permit)
        stopped_since = sp.suspended_at if sp else None
    brk = timedelta(minutes=f.settings.gas_break_retest_minutes)
    post_break = bool(f.gas_required and stopped_since is not None and at - stopped_since >= brk)
    status = st.status
    if permit.status != S.active and status in (GasStatus.overdue, GasStatus.due_soon):
        status = GasStatus.valid if st.latest_pass else GasStatus.missing
    return sch.PermitGasState(
        required=f.gas_required,
        status=status,
        latest_passing=gas_brief(st.latest_pass),
        latest=gas_brief(st.latest),
        valid_for_start_until=st.latest_pass.valid_for_start_until if st.latest_pass else None,
        next_due_at=st.next_due_at if permit.status == S.active and paused is None else None,
        interval_minutes=f.interval if f.gas_required else None,
        post_break_test_required=post_break,
    )


# ---- allowed actions ---------------------------------------------------------------------------------


def allowed_actions(db: Session, p: Principal, permit: Permit) -> list[PermitAction]:
    if permit.status in PERMIT_TERMINAL or (
        p.employer_status is not None and p.employer_status.value == "suspended"
    ):
        return []
    pid = permit.project_id
    uid = p.user.id

    def has(c: Capability) -> bool:
        return p.grant(pid, c) is not None

    roles = user_roles(db, uid, pid)
    issuer = (
        has(C.permit_issue)
        and (p.is_manager or Role.permit_issuer in roles)
        and uid != permit.receiver_user_id
    )
    receiver = has(C.permit_receive) and uid == permit.receiver_user_id
    st = permit.status
    out: list[PermitAction] = []
    if st == S.draft and receiver:
        out.append(A.request)
    if st == S.requested and (
        issuer or (has(C.permit_area_review) and uid == permit.area_authority_user_id)
    ):
        out.append(A.return_)
    if st == S.reviewed and (issuer or has(C.permit_hse_review)):
        out.append(A.return_)
    if st == S.requested and has(C.permit_area_review) and uid == permit.area_authority_user_id:
        out.append(A.review)
    if (
        st in (S.requested, S.reviewed)
        and permit.high_risk
        and has(C.permit_hse_review)
        and (permit.hse_reviewer_user_id in (None, uid))
        and (permit.hse_review or {}).get("decision") != "accepted"
    ):
        out.append(A.hse_review)
    if st == S.reviewed and issuer:
        out.append(A.approve)
    if st == S.approved and issuer:
        out.append(A.issue)
    if st == S.issued and receiver:
        out.append(A.start)
    if st == S.active and receiver:
        out.append(A.end_shift)
        out.append(A.handover)
    if st in (S.issued, S.active) and has(C.permit_suspend):
        out.append(A.suspend)
    if st == S.suspended and issuer:
        if permit.status_reason in (StatusReason.shift_end, StatusReason.shift_lapsed):
            if T.radiography.value not in permit.work_types:
                out.append(A.revalidate)
        else:
            out.append(A.resume)
    if st in (S.issued, S.active, S.suspended) and receiver and permit.closure_request is None:
        out.append(A.request_closure)
    if st in (S.issued, S.active, S.suspended) and issuer and permit.closure_request is not None:
        out.append(A.close)
    if has(C.permit_cancel):
        client = p.is_manager or bool(roles & {Role.hse_officer, Role.permit_issuer})
        ok = st in (S.draft, S.requested, S.reviewed, S.approved, S.issued) or (
            st == S.suspended and permit.status_reason == StatusReason.contractor_blacklisted
        )
        if ok and (client or (receiver and st in (S.draft, S.requested))):
            out.append(A.cancel)
    return out


# ---- the permit ---------------------------------------------------------------------------------------


def jsa_summary(db: Session, permit: Permit) -> sch.JsaSummary | None:
    from app.services.ptw import jsa  # noqa: PLC0415

    j: Jsa | None = jsa.current_for_permit(db, permit)
    if j is None:
        return None
    return sch.JsaSummary(
        id=j.id,
        jsa_no=j.jsa_no,
        status=j.status,
        governing_residual_band=jsa.governing_band(j),
        residual_acceptance_complete=not jsa.missing_acceptances(j),
    )


def obs_links(db: Session, permit: Permit) -> list[sch.ObsLinkRead]:
    out = []
    for oid in permit.linked_obs_ids or []:
        o = db.get(ObstacleClearance, oid)
        if o is not None:
            out.append(
                sch.ObsLinkRead(
                    id=o.id,
                    obs_no=o.obs_no,
                    status=o.status.value,
                    valid_to=o.valid_to,
                    conditions=list(o.conditions or []),
                )
            )
    return out


def iso_links(db: Session, permit: Permit) -> list[sch.IsolationLinkRead]:
    from app.services.ptw import isolations  # noqa: PLC0415

    out = []
    for c in isolations.certs_of(db, permit):
        n = db.scalar(
            select(func.count())
            .select_from(IsolationPoint)
            .where(IsolationPoint.certificate_id == c.id)
        )
        out.append(
            sch.IsolationLinkRead(
                id=c.id,
                iso_no=c.iso_no,
                status=c.status.value,
                points_count=int(n or 0),
                personal_locks_applied=len(isolations.active_personal_locks(db, c.lockbox_id)),
            )
        )
    return out


def conflict_summaries(db: Session, permit: Permit) -> list[sch.ConflictSummary]:
    from app.services.ptw import simops  # noqa: PLC0415

    out = []
    for c in simops.conflicts_of(db, permit.id):
        other = db.get(Permit, c.permit_b_id if c.permit_a_id == permit.id else c.permit_a_id)
        if other is None:
            continue
        out.append(
            sch.ConflictSummary(
                id=c.id,
                conflict_no=c.conflict_no,
                rule_code=c.rule_code,
                result=c.result,
                status=c.status,
                other_permit=common.permit_ref(other),
                distance_m=c.distance_m.quantize(Decimal("0.1"))
                if c.distance_m is not None
                else None,
                overlap_from=c.overlap_from,
                overlap_to=c.overlap_to,
            )
        )
    return out


def incident_links(db: Session, permit: Permit) -> list[sch.IncidentLinkRead]:
    rows = db.execute(
        select(Incident)
        .join(Investigation, Investigation.incident_id == Incident.id)
        .where(Investigation.ptw_ids.contains([permit.id]))
    ).scalars()
    return [sch.IncidentLinkRead(id=i.id, ref=i.ref, occurred_at=i.occurred_at) for i in rows]


def crew_roles(lines: list[Any]) -> dict[PtwCrewRole, int]:
    out: dict[PtwCrewRole, int] = {}
    for x in lines:
        if x.status == CrewLineStatus.removed:
            continue
        out[x.crew_role] = out.get(x.crew_role, 0) + 1
    return out


def handovers_count(db: Session, permit_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(PermitHandover)
            .where(PermitHandover.permit_id == permit_id)
        )
        or 0
    )


def shifts_count(db: Session, permit_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(PermitShift).where(PermitShift.permit_id == permit_id)
        )
        or 0
    )


def permit_read(
    db: Session, p: Principal, permit: Permit, write_warnings: list[Any] | None = None
) -> sch.PermitRead:
    at = now()
    f = facts_mod.compute(db, permit)
    refs = Refs(db)
    names = names_ok(p, permit.project_id)
    medical = medical_ok(p, permit.project_id)
    shift = evaluation.current_shift(db, permit)
    lines = evaluation.crew_lines(db, permit.id, include_removed=True)
    visible_lines = [
        x for x in lines if x.status != CrewLineStatus.removed or permit.status not in (S.draft,)
    ]
    created_by = refs.user(permit.created_by_user_id) or refs.user(permit.receiver_user_id)
    receiver = refs.user(permit.receiver_user_id)
    assert created_by is not None and receiver is not None  # noqa: S101
    copied = db.get(Permit, permit.copied_from_id) if permit.copied_from_id else None
    pec = permit.post_expiry_check or {}
    pec_read = None
    if pec.get("checked_by_user_id"):
        by = refs.user(uuid.UUID(pec["checked_by_user_id"]))
        assert by is not None  # noqa: S101
        pec_read = sch.PostExpiryCheckRead(
            checked_by=by,
            checked_at=datetime.fromisoformat(pec["checked_at"]),
            site_visit_confirmed=True,
            area_safe=bool(pec.get("area_safe")),
            area_note=pec.get("area_note") or "",
            entrants_zero=pec.get("entrants_zero"),
            personal_locks_removed=pec.get("personal_locks_removed"),
            fire_watch_status=pec.get("fire_watch_status"),
            ca_id=uuid.UUID(pec["ca_id"]) if pec.get("ca_id") else None,
        )
    cr = permit.closure_request
    cr_read = None
    if cr:
        by = refs.user(uuid.UUID(cr["requested_by_user_id"]))
        assert by is not None  # noqa: S101
        cr_read = sch.ClosureRequestRead(
            requested_by=by,
            requested_at=datetime.fromisoformat(cr["requested_at"]),
            work_status=cr["work_status"],
            remaining_work=cr.get("remaining_work"),
        )
    ra = permit.receiver_acceptance
    ra_read = None
    if ra and datetime.fromisoformat(ra["valid_until"]) >= at:
        ra_read = sch.ReceiverAcceptanceRead(
            purpose=ra["purpose"],
            signed_at=datetime.fromisoformat(ra["signed_at"]),
            valid_until=datetime.fromisoformat(ra["valid_until"]),
        )
    docs = evaluation.documents(db, permit.id)
    sup = _worker(db, permit.supervisor_worker_id, names)
    return sch.PermitRead(
        id=permit.id,
        project_id=permit.project_id,
        permit_no=permit.permit_no,
        display_no=common.display_no(permit),
        site=refs.site(permit.site_id),
        zones=[z for z in (refs.zone(z) for z in permit.zone_ids or []) if z is not None],
        location_desc=permit.location_desc,
        grid_x_m=permit.grid_x_m,
        grid_y_m=permit.grid_y_m,
        level_code=permit.level_code,
        elevation_m=permit.elevation_m,
        engagement=refs.eng_required(permit.engagement_id),
        work_types=[T(t) for t in permit.work_types],
        primary_type=permit.primary_type,
        high_risk=bool(f.high_risk_reasons),
        high_risk_reasons_en=list(f.high_risk_reasons),
        title=permit.title,
        scope_en=permit.scope_en,
        scope_ar=permit.scope_ar,
        exposure=permit.exposure,
        flammables_in_use=permit.flammables_in_use,
        combustion_engine_plant=permit.combustion_engine_plant,
        valid_from_at=permit.valid_from_at,
        valid_to_at=permit.valid_to_at,
        windows=common.window_reads(permit),
        current_window=common.window_instance(common.current_instance(permit, at)),
        next_window=common.window_instance(common.next_instance(permit, at)),
        receiver=receiver,
        area_authority=refs.user(permit.area_authority_user_id),
        issuer=refs.user(permit.issuer_user_id),
        hse_reviewer=refs.user(permit.hse_reviewer_user_id),
        supervisor=sup,
        jsa=jsa_summary(db, permit),
        documents=[
            document_read(db, d, refs, permit.created_by_user_id or permit.receiver_user_id)
            for d in docs
        ],
        crew=[crew_read(db, p, x, shift, names, medical) for x in visible_lines],
        crew_count=len([x for x in lines if x.status != CrewLineStatus.removed]),
        crew_roles=crew_roles(lines),
        equipment=[equipment_read(db, e, names) for e in evaluation.equipment_lines(db, permit.id)],
        sections=section_reads(db, p, permit, f, refs, names),
        pre_issue_checklist=checklist_read(db, permit, ChecklistKind.pre_issue, refs),
        closure_checklist=checklist_read(db, permit, ChecklistKind.closure, refs),
        waps=[wap_link_read(w) for w in wap_links(db, permit, f)],
        obstacle_clearances=obs_links(db, permit),
        isolations=iso_links(db, permit),
        simops=conflict_summaries(db, permit),
        conditions_en=permit.conditions_en,
        conditions_ar=permit.conditions_ar,
        copied_conditions=list(permit.copied_conditions or []),
        hook_conditions=[HookCondition(**c) for c in permit.hook_conditions or []],
        emergency_info=permit.emergency_info,
        status=permit.status,
        status_reason=permit.status_reason,
        status_detail=permit.status_detail,
        blockers=common.blocker_reads(permit.blockers or [], names),
        warnings=common.warning_reads(permit.warnings or [], names),
        gas=gas_state(db, permit, f, at),
        current_shift=shift_read(db, p, shift, refs, names) if shift else None,
        shifts_count=shifts_count(db, permit.id),
        handovers_count=handovers_count(db, permit.id),
        exemptions=[exemption_read(e, refs) for e in exemptions_of(db, permit.id)],
        signatures=[signature_read(db, s, refs, names) for s in signatures_of(db, permit)],
        receiver_acceptance=ra_read,
        closure_request=cr_read,
        post_expiry_check_pending=permit.status == S.expired and permit.post_expiry_check is None,
        post_expiry_check=pec_read,
        incidents=incident_links(db, permit),
        first_requested_at=permit.first_requested_at,
        first_issued_at=permit.first_issued_at,
        issued_at=permit.issued_at,
        started_at=permit.started_at,
        closed_at=permit.closed_at,
        allowed_actions=allowed_actions(db, p, permit),
        copied_from=common.permit_ref(copied) if copied else None,
        write_warnings=write_warnings or [],
        created_at=permit.created_at,
        created_by=created_by,
        updated_at=permit.updated_at or permit.created_at,
    )


def list_item(db: Session, permit: Permit, refs: Refs, at: datetime) -> sch.PermitListItem:
    from app.services.ptw import gas, simops  # noqa: PLC0415

    f_interval = None
    receiver = refs.user(permit.receiver_user_id)
    assert receiver is not None  # noqa: S101
    n_crew = len(evaluation.crew_lines(db, permit.id))
    gas_required = any(b.get("code", "").startswith("GAS_") for b in permit.blockers or [])
    try:
        f = facts_mod.compute(db, permit)
        gas_required, f_interval = f.gas_required, f.interval
    except Exception:
        f = None
    st = gas.state(db, permit, f_interval, gas_required, at)
    status = st.status
    if permit.status != S.active and status in (GasStatus.overdue, GasStatus.due_soon):
        status = GasStatus.valid
    open_n = len([c for c in simops.conflicts_of(db, permit.id) if c.status.value == "open"])
    return sch.PermitListItem(
        id=permit.id,
        permit_no=permit.permit_no,
        display_no=common.display_no(permit),
        title=permit.title,
        work_types=[T(t) for t in permit.work_types],
        primary_type=permit.primary_type,
        high_risk=permit.high_risk,
        status=permit.status,
        status_reason=permit.status_reason,
        site=refs.site(permit.site_id),
        zones=[z for z in (refs.zone(z) for z in permit.zone_ids or []) if z is not None],
        engagement=refs.eng_required(permit.engagement_id),
        receiver=receiver,
        issuer=refs.user(permit.issuer_user_id),
        valid_from_at=permit.valid_from_at,
        valid_to_at=permit.valid_to_at,
        crew_count=n_crew,
        blockers=[
            b["code"]
            for b in sorted(
                permit.blockers or [], key=lambda b: ref.BLOCKER_ORDER[ref.B(b["code"])]
            )
        ],
        gas_status=status,
        simops_open=open_n,
        post_expiry_check_pending=permit.status == S.expired and permit.post_expiry_check is None,
    )


_ = (PermitDocument, PermitEquipment)
