"""Checklist execution (spec 6d-field-assurance §3.4–§3.6, EXE-1…EXE-9, FND-1…FND-7): idempotent
offline-tolerant submissions that complete the Phase 1 inspection, score the answers, create the
findings (repeats, FND-5), the Phase 1 CAs (FND-3), the stop-work order and the critical-failure
alerts; response reads, the findings register, inspection voids and the offline pack."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, validation_error
from app.core.field_enums import (
    INSPECTION_SEVERITIES,
    FindingSeverity,
    ItemType,
    ResponseOwnerType,
    ResponseResult,
    StopOrderStatus,
    StopRule,
    VersionStatus,
)
from app.core.hse_enums import AttachmentOwner, CaSourceType, ControlLevel, InspectionStatus
from app.core.ptw_enums import PermitStatus
from app.models import (
    ChecklistResponse,
    ChecklistTemplate,
    Deployment,
    FieldFinding,
    Inspection,
    InspectionPlan,
    Permit,
    Project,
    StopWorkOrder,
    ToolboxTopic,
    Worker,
)
from app.schemas.field import (
    AnswerRead,
    FieldFindingPage,
    FieldFindingRead,
    InspectionVoid,
    OfflineDeployment,
    OfflineInstance,
    OfflinePack,
    ResponseRead,
    SectionScore,
    SubmissionCreate,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.inspections import InspectionRead
from app.services import hse_settings
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.field import common as fc
from app.services.field import library, scoring
from app.services.field.reference import grade_for
from app.services.hse_common import Refs, check_engagement, check_site_zone, covers, make_ref
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
ST = InspectionStatus
FS = FindingSeverity
D = Decimal
PHASE1_SEVERITY = {
    FS.observation: "low",
    FS.ofi: "low",
    FS.minor: "medium",
    FS.minor_nc: "medium",
    FS.major: "high",
    FS.major_nc: "high",
    FS.critical: "critical",
}
CA_SEVERITIES = (FS.critical, FS.major, FS.major_nc, FS.minor_nc)
MAX_PHOTOS = 40
LIVE_PERMITS = (PermitStatus.issued, PermitStatus.active)


# ---- helpers -------------------------------------------------------------------------------------


def _warn(code: str, en: str, ar: str | None = None, fld: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": en, "message_ar": ar, "field": fld}


def _p18(text: str | None, fld: str, out: list[dict[str, Any]]) -> None:
    if fc.p18(text):
        out.append(
            _warn(
                "POSSIBLE_ID_NUMBER",
                "The text may contain an ID number (P1-8): remove it.",
                "قد يحتوي النص على رقم هوية: احذفه.",
                fld,
            )
        )


def _too_late(db: Session, p: Principal, proj: Project, completed_at: datetime) -> None:
    """EXE-6 rejection: alert the submitter and the HSE Officers at sync. The request rolls
    back, so the notification is written in its own session."""
    with Session(bind=db.get_bind()) as s2:
        fc.send(
            s2,
            {p.user.id} | fc.officers(s2, proj.id),
            NotificationKind.offline_submission_rejected,
            f"An offline submission completed {completed_at:%Y-%m-%d %H:%M} UTC was rejected: "
            "older than the offline limit.",
            "رُفض إرسال سُجل دون اتصال لتجاوزه المهلة المسموحة.",
            proj.id,
        )
        s2.commit()


def check_times(
    db: Session, p: Principal, proj: Project, at: datetime, received: datetime, fld: str
) -> None:
    """EXE-6: completed_at ≤ received + 5 min (CLOCK_SKEW) and ≥ received − max hours."""
    if at > received + timedelta(minutes=5):
        raise fc.err(422, ErrorCode.CLOCK_SKEW, "The device time is ahead of the server time.",
                     "وقت الجهاز يسبق وقت الخادم.", field=fld)  # fmt: skip
    hours = int(fc.cfg(db, proj.id)["offline_submit_max_hours"])
    if at < received - timedelta(hours=hours):
        _too_late(db, p, proj, at)
        raise fc.err(
            422,
            ErrorCode.OFFLINE_SUBMIT_TOO_LATE,
            f"Recorded more than {hours} h ago: the submission is too late (EXE-6).",
            f"سُجل قبل أكثر من {hours} ساعة: انتهت مهلة الإرسال.",
            field=fld,
        )


def fix_err(fld: str) -> Any:
    return fc.err(
        422,
        ErrorCode.FIX_ON_SPOT_NOT_ALLOWED,
        "Only a minor finding can be fixed on the spot (FND-3).",
        "يسمح بالتصحيح الفوري للملاحظات البسيطة فقط.",
        field=fld,
    )


def delay_min(at: datetime, received: datetime) -> int | None:
    """EXE-7: stored when the submission arrives more than 15 minutes after completion."""
    m = int((received - at).total_seconds() // 60)
    return m if m > 15 else None


def record_scope_ok(g: Grant, site_id: uuid.UUID, engagement_id: uuid.UUID | None) -> bool:
    """EXE-4: a C-scope holder records engagements in scope or inspections with no engagement."""
    if not g.covers_site(site_id):
        return False
    return engagement_id is None or g.covers_engagement(engagement_id)


def _pin(
    db: Session, body: SubmissionCreate, code: str | None, project_id: uuid.UUID
) -> ChecklistTemplate:
    """TPL-4: the version Published at started_at (a client-pinned version is accepted when it was
    Published at started_at, even if Superseded since)."""
    t: ChecklistTemplate | None = None
    if body.template_id is not None:
        t = db.get(ChecklistTemplate, body.template_id)
        ok = (
            t is not None
            and t.published_at is not None
            and t.published_at <= body.started_at
            and t.status in (VersionStatus.published, VersionStatus.superseded)
        )
        if not ok:
            t = library.published(db, t.template_code, body.started_at) if t else None
    elif code:
        t = library.published(db, code, body.started_at)
    if t is None:
        raise validation_error("template_code", "No Published checklist template applies.")
    if not library.offered(t, project_id):
        raise _not_applicable("The template is not offered on this project (TPL-1).")
    return t


def _not_applicable(en: str) -> Any:
    return fc.err(422, ErrorCode.TEMPLATE_NOT_APPLICABLE, en, "النموذج لا ينطبق على هذا الموقع.",
                  field="template_code")  # fmt: skip


def _repeat_of(
    db: Session,
    project_id: uuid.UUID,
    item_code: str,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    eng: uuid.UUID | None,
    day: date,
) -> FieldFinding | None:
    """FND-5 / §6.3: the latest earlier non-compliance of the same key within the window."""
    days = int(fc.cfg(db, project_id)["repeat_finding_days"])
    F = FieldFinding  # noqa: N806
    stmt = select(F).where(
        F.project_id == project_id,
        F.item_code == item_code,
        F.voided.is_(False),
        F.completed_date >= day - timedelta(days=days),
        F.completed_date <= day,
        F.engagement_id == eng if eng else F.engagement_id.is_(None),
    )
    stmt = (
        stmt.where(F.zone_id == zone_id)
        if zone_id
        else stmt.where(F.site_id == site_id, F.zone_id.is_(None))
    )
    return db.scalar(stmt.order_by(F.completed_date.desc(), F.finding_no.desc()).limit(1))


# ---- submission ----------------------------------------------------------------------------------


def submit(
    db: Session, p: Principal, project_id: uuid.UUID, body: SubmissionCreate
) -> ResponseRead:
    proj = fc.project(db, p, project_id)
    prior = db.scalar(
        select(ChecklistResponse).where(
            ChecklistResponse.project_id == project_id,
            ChecklistResponse.client_uuid == body.client_uuid,
        )
    )
    if prior is not None:  # EXE-6 idempotency: nothing is created twice
        return response_read(db, p, prior)
    ensure_open(proj)
    g = p.require(project_id, C.inspection_record)
    received = now()
    check_times(db, p, proj, body.completed_at, received, "completed_at")
    if body.started_at > body.completed_at:
        raise validation_error("started_at", "started_at must be before completed_at.")
    ins: Inspection | None = None
    plan: InspectionPlan | None = None
    if body.inspection_id is not None:
        ins = db.get(Inspection, body.inspection_id)
        if ins is None or ins.project_id != project_id:
            raise validation_error("inspection_id", "Unknown inspection.")
        if ins.status not in (ST.planned, ST.missed):
            raise invalid_transition("Inspection", ins.status, ST.completed)
        if p.user.id != ins.assignee_user_id and not covers(g, ins.site_id, ins.engagement_id):
            raise forbidden_error()
        plan = db.get(InspectionPlan, ins.plan_id) if ins.plan_id else None
        site_id, zone_id, eng_id = ins.site_id, ins.zone_id, ins.engagement_id
        code = body.template_code or (plan.template_code if plan else None)
    else:
        if body.site_id is None:
            raise validation_error("site_id", "site_id is required for an unplanned inspection.")
        site_id, zone_id, eng_id = body.site_id, body.zone_id, body.engagement_id
        check_site_zone(db, proj, site_id, zone_id)
        if eng_id:
            check_engagement(db, proj, eng_id)
        if not record_scope_ok(g, site_id, eng_id):
            raise forbidden_error("The inspection is outside your scope (EXE-4).")
        code = body.template_code
    t = _pin(db, body, code, project_id)
    if t.kind.value != "inspection":
        raise _not_applicable("Use an inspection template.")
    if ins is not None and t.inspection_type != ins.inspection_type:
        raise _not_applicable("The template is for another inspection type.")
    zt = fc.zone_type(db, zone_id)
    if t.zone_types and zt is not None and zt not in t.zone_types:
        raise _not_applicable("The template does not apply to this zone type (EXE-1).")
    airside = zt == "airside"
    answers = [a.model_dump(mode="json") for a in body.answers]
    if sum(len(a.photos) for a in body.answers) > MAX_PHOTOS:
        raise validation_error("answers", f"At most {MAX_PHOTOS} photos per response (EXE-5).")
    sc = scoring.evaluate(t.items, answers, airside)
    cfg = fc.cfg(db, project_id)
    day = fc.local_day(body.completed_at)
    # ---- findings (FND-1, FND-3, FND-5) and the stop rule (FND-7) -------------------------------
    by_code = {a.item_code: (i, a) for i, a in enumerate(body.answers)}
    planned: list[dict[str, Any]] = []
    stop_item: str | None = None
    for ev in sc.evals:
        sev0 = scoring.finding_severity(ev, audit=False)
        if sev0 is None:
            continue
        idx, a = by_code[ev.code]
        fld = f"answers[{idx}]"
        if a.severity is not None and a.severity not in INSPECTION_SEVERITIES:
            raise validation_error(f"{fld}.severity", "Use minor, major or critical.")
        sev = scoring.raised(sev0, a.severity, f"{fld}.severity")
        if a.fixed_on_spot and sev != FS.minor:
            raise fix_err(f"{fld}.fixed_on_spot")
        rep = _repeat_of(db, project_id, ev.code, site_id, zone_id, eng_id, day)
        if rep is not None and sev == FS.minor:
            sev = FS.major
        if ev.item.get("stop_rule") == StopRule.stop_work.value and stop_item is None:
            stop_item = ev.code
        planned.append(
            {
                "ev": ev,
                "a": a,
                "sev": sev,
                "repeat": rep,
                "fixed": a.fixed_on_spot and sev == FS.minor,
            }
        )
    if stop_item is not None:
        sw = body.stop_work
        if sw is None or not ((sw.activity_en or "").strip() or (sw.activity_ar or "").strip()):
            raise fc.err(
                422,
                ErrorCode.STOP_RECORD_REQUIRED,
                f"{stop_item} failed: record the stopped activity, who was told and when (FND-7).",
                "سجّل النشاط الموقوف ومن أُبلغ ومتى.",
                field="stop_work",
            )
        if sw.instructed_at > body.completed_at + timedelta(minutes=10):
            raise validation_error(
                "stop_work.instructed_at", "instructed_at must be ≤ completed_at + 10 min."
            )
    permits = _permits(db, project_id, site_id, zone_id, body) if stop_item else []
    for i, mf in enumerate(body.manual_findings):
        fld = f"manual_findings[{i}]"
        if mf.severity not in INSPECTION_SEVERITIES:
            raise validation_error(f"{fld}.severity", "Use minor, major or critical.")
        if not ((mf.description_en or "").strip() or (mf.description_ar or "").strip()):
            raise validation_error(f"{fld}.description_en", "Describe the finding.")
        if mf.fixed_on_spot and mf.severity != FS.minor:
            raise fix_err(f"{fld}.fixed_on_spot")
    # ---- the inspection (EXE-3) ------------------------------------------------------------------
    if ins is None:
        seq = fc.next_seq(db, Inspection, project_id, day.year)
        assert t.inspection_type is not None  # noqa: S101
        ins = Inspection(
            project_id=project_id,
            ref=make_ref("INS", proj.code, day.year, seq, 5),
            year=day.year,
            seq=seq,
            inspection_type=t.inspection_type,
            site_id=site_id,
            zone_id=zone_id,
            engagement_id=eng_id,
            status=ST.completed,
            findings=[],
        )
        db.add(ins)
        db.flush()
    src_status = ins.status
    delay = delay_min(body.completed_at, received)
    pass_mark = max(D(t.pass_mark_pct), cfg.dec("inspection_pass_mark_pct"))
    pct = sc.pct
    result = (
        ResponseResult.fail
        if sc.critical_fails or (pct is not None and pct < pass_mark)
        else ResponseResult.pass_
    )
    warnings: list[dict[str, Any]] = []
    r = ChecklistResponse(
        project_id=project_id,
        client_uuid=body.client_uuid,
        owner_type=ResponseOwnerType.inspection,
        inspection_id=ins.id,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        inspection_type=t.inspection_type,
        site_id=site_id,
        zone_id=zone_id,
        engagement_id=eng_id,
        airside=airside,
        started_at=body.started_at,
        completed_at=body.completed_at,
        completed_date=day,
        received_at=received,
        offline_delay_min=delay,
        inspector_id=p.user.id,
        answers=[],
        applicable_count=sc.applicable_count,
        compliant_count=sc.compliant_count,
        applicable_weight=sc.applicable_weight,
        earned_weight=sc.earned_weight,
        score_pct=scoring.q(pct) if pct is not None else None,
        critical_fail_count=sc.critical_fails,
        result=result,
        self_inspection=g.engagement_ids is not None
        and eng_id is not None
        and eng_id in g.engagement_ids,
        submitted=True,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    r.answers = store_answers(db, p.user.id, r, sc, by_code, warnings)
    # findings
    findings: list[FieldFinding] = []
    n = 0
    ca_of: dict[str, uuid.UUID] = {}
    for f in planned:
        ev, a, sev = f["ev"], f["a"], f["sev"]
        n += 1
        desc_en = (a.finding_description_en or a.note or ev.item.get("text_en") or "").strip()
        desc_ar = (a.finding_description_ar or "").strip() or None
        _p18(desc_en, f"answers[{by_code[ev.code][0]}].note", warnings)
        ff = FieldFinding(
            project_id=project_id,
            response_id=r.id,
            finding_no=f"{ins.ref}-F{n:02d}",
            item_code=ev.code,
            severity=sev,
            critical_item=ev.critical,
            description_en=desc_en[:1000] or None,
            description_ar=desc_ar,
            repeat_of_id=f["repeat"].id if f["repeat"] else None,
            fixed_on_spot=f["fixed"],
            ca_required=bool(a.ca_required),
            responsible_engagement_id=eng_id or fc.tier1_on_site(db, project_id, site_id),
            site_id=site_id,
            zone_id=zone_id,
            engagement_id=eng_id,
            completed_date=day,
            created_by_user_id=p.user.id,
        )
        db.add(ff)
        needs_ca = (
            sev in CA_SEVERITIES or f["repeat"] is not None or (a.ca_required and not f["fixed"])
        )
        if needs_ca:
            ctl = ev.item.get("suggested_control_level")
            ca = fc.make_ca(
                db, proj, CaSourceType.inspection, ins.id, site_id, zone_id, eng_id, sev.value,
                ev.item.get("suggested_ca_en") or f"{ev.code}: {ev.item.get('text_en', '')}",
                f"{ff.finding_no}: {desc_en}"[:2000],
                ControlLevel(ctl) if ctl else None, p.user.id, p.user.id,
            )  # fmt: skip
            ff.ca_id = ca.id
            ca_of[ev.code] = ca.id
        findings.append(ff)
    for mf in body.manual_findings:
        n += 1
        fixed = mf.fixed_on_spot and mf.severity == FS.minor
        meng = mf.responsible_engagement_id or eng_id
        ff = FieldFinding(
            project_id=project_id,
            response_id=r.id,
            finding_no=f"{ins.ref}-F{n:02d}",
            item_code=None,
            severity=mf.severity,
            description_en=mf.description_en,
            description_ar=mf.description_ar,
            fixed_on_spot=fixed,
            ca_required=mf.ca_required,
            responsible_engagement_id=meng or fc.tier1_on_site(db, project_id, site_id),
            site_id=site_id,
            zone_id=zone_id,
            engagement_id=eng_id,
            completed_date=day,
            created_by_user_id=p.user.id,
        )
        db.add(ff)
        _p18(mf.description_en, "manual_findings", warnings)
        if mf.severity in CA_SEVERITIES or (mf.ca_required and not fixed):
            ca = fc.make_ca(
                db, proj, CaSourceType.inspection, ins.id, site_id, zone_id, meng,
                mf.severity.value, (mf.description_en or mf.description_ar or "Finding")[:150],
                ff.description_en or ff.description_ar or "", None, p.user.id, p.user.id,
            )  # fmt: skip
            ff.ca_id = ca.id
        findings.append(ff)
    db.flush()
    r.warnings = warnings
    # Phase 1 inspection (EXE-3) and its findings read model (§3.6)
    ins.completed_at = body.completed_at
    ins.completed_date = day
    ins.inspector_id = p.user.id
    ins.items_checked = sc.applicable_count
    ins.items_compliant = sc.compliant_count
    ins.status = ST.completed
    ins.response_id = r.id
    ins.offline_delay_min = delay
    ins.findings = [phase1_finding(ff) for ff in findings]
    ins.updated_at = now()
    # stop-work order (FND-7)
    if stop_item is not None:
        assert body.stop_work is not None  # noqa: S101
        _order(db, p, proj, r, ins, stop_item, ca_of.get(stop_item), permits, body, delay)
    db.flush()
    fc.record(db, p, AuditAction.create, EntityType.checklist_response, r, project_id,
              details={"inspection": ins.ref, "from_status": src_status.value})  # fmt: skip
    if sc.critical_fails:
        _critical_alert(db, proj, r, ins, delay)
    return response_read(db, p, r)


def phase1_finding(ff: FieldFinding) -> dict[str, Any]:
    return {
        "id": str(ff.id),
        "description": (ff.description_en or ff.description_ar or ff.item_code or "")[:1000],
        "severity": PHASE1_SEVERITY[ff.severity],
        "ca_required": ff.ca_id is not None,
        "ca_id": str(ff.ca_id) if ff.ca_id else None,
    }


def store_answers(
    db: Session,
    user_id: uuid.UUID,
    r: ChecklistResponse,
    sc: scoring.Score,
    by_code: dict[str, tuple[int, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out = []
    for ev in sc.evals:
        idx, a = by_code.get(ev.code, (None, None))
        if a is None:
            continue
        photo_ids = fc.store_photos(
            db, AttachmentOwner.field_photo, r.id, r.project_id, a.photos, user_id,
            f"answers[{idx}].photos",
        )  # fmt: skip
        _p18(a.note, f"answers[{idx}].note", warnings)
        out.append(
            {
                "item_code": ev.code,
                "item_type": ev.item["item_type"],
                "answer": a.answer,
                "numeric_value": str(a.numeric_value) if a.numeric_value is not None else None,
                "count_value": a.count_value,
                "note": a.note,
                "photo_ids": [str(x) for x in photo_ids],
                "equipment_ref": a.equipment_ref,
                "applicable": ev.applicable,
                "compliant": ev.compliant if ev.applicable else None,
                "earned_weight": fc.w3(ev.earned) if ev.applicable else None,
                "weight": fc.w3(ev.weight) if ev.applicable else None,
                "rating": ev.rating,
                "critical": ev.critical,
                "section_code": ev.item.get("section_code"),
            }
        )
    return out


def _permits(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    body: SubmissionCreate,
) -> list[Permit]:
    """FND-9: named permits must be Issued / Active and cover the zone."""
    out = []
    assert body.stop_work is not None  # noqa: S101
    for i, pid in enumerate(body.stop_work.permit_ids):
        pm = db.get(Permit, pid)
        ok = (
            pm is not None
            and pm.project_id == project_id
            and pm.site_id == site_id
            and pm.status in LIVE_PERMITS
            and (zone_id is None or zone_id in (pm.zone_ids or []))
        )
        if not ok:
            raise validation_error(
                f"stop_work.permit_ids[{i}]", "Name Issued or Active permits on the zone (FND-9)."
            )
        assert pm is not None  # noqa: S101
        out.append(pm)
    return out


def _order(
    db: Session,
    p: Principal,
    proj: Project,
    r: ChecklistResponse,
    ins: Inspection,
    item_code: str,
    ca_id: uuid.UUID | None,
    permits: list[Permit],
    body: SubmissionCreate,
    delay: int | None,
) -> StopWorkOrder:
    sw = body.stop_work
    assert sw is not None  # noqa: S101
    year = fc.local_day(body.completed_at).year
    seq = fc.next_seq(db, StopWorkOrder, proj.id, year)
    o = StopWorkOrder(
        order_no=make_ref("SWO", proj.code, year, seq, 3),
        year=year,
        seq=seq,
        project_id=proj.id,
        response_id=r.id,
        item_code=item_code,
        site_id=r.site_id,
        zone_id=r.zone_id,
        engagement_id=r.engagement_id,
        activity_en=sw.activity_en,
        activity_ar=sw.activity_ar,
        instructed_role=sw.instructed_role,
        instructed_at=sw.instructed_at,
        raised_at=body.completed_at,
        received_at=r.received_at or now(),
        recorded_offline=delay is not None,
        permit_ids=[pm.id for pm in permits],
        ca_id=ca_id,
        status=StopOrderStatus.active,
        created_by_user_id=p.user.id,
    )
    db.add(o)
    db.flush()
    r.stop_work_order_id = o.id
    fc.record(db, p, AuditAction.create, EntityType.stop_work_order, o, proj.id,
              details={"inspection": ins.ref})  # fmt: skip
    process_order(db, o)
    return o


def process_order(db: Session, o: StopWorkOrder) -> None:
    """FND-7 alerts and FND-9 suspensions (inline at receipt; `field_minute` retries)."""
    from app.core.ptw_enums import StatusReason  # noqa: PLC0415
    from app.services.ptw import lifecycle  # noqa: PLC0415

    if o.processed:
        return
    pid = o.project_id
    people = (
        fc.managers(db)
        | fc.officers(db, pid)
        | fc.site_engineers(db, pid, o.site_id)
        | fc.reps(db, pid, o.engagement_id)
    )
    for pm_id in o.permit_ids or []:
        pm = db.get(Permit, pm_id)
        if pm is None:
            continue
        people.add(pm.receiver_user_id)
        if pm.issuer_user_id:
            people.add(pm.issuer_user_id)
        if o.status == StopOrderStatus.active:
            lifecycle.auto_suspend(
                db, pm, StatusReason.stop_work, f"Stop-work order {o.order_no}", o.order_no
            )
    r = db.get(ChecklistResponse, o.response_id)
    off_en = fc.offline_label(r.offline_delay_min if r else None, o.raised_at)
    off_ar = fc.offline_label_ar(r.offline_delay_min if r else None, o.raised_at)
    act = o.activity_en or o.activity_ar or ""
    fc.send(
        db,
        people,
        NotificationKind.stop_work_order,
        f"STOP WORK {o.order_no}: {o.item_code} – {act}{off_en}",
        f"أمر إيقاف عمل {o.order_no}: {o.item_code}{off_ar}",
        pid,
        EntityType.stop_work_order,
        o.id,
        email=True,
    )
    o.processed = True
    db.flush()


def _critical_alert(
    db: Session, proj: Project, r: ChecklistResponse, ins: Inspection, delay: int | None
) -> None:
    """FND-6: site engineers, HSE Officers and the engagement's Contractor HSE Rep."""
    if not fc.once(db, f"field:critical:{r.id}"):
        return
    codes = ", ".join(
        a["item_code"] for a in r.answers if a.get("critical") and a.get("compliant") is False
    )
    fc.send(
        db,
        fc.site_engineers(db, proj.id, r.site_id)
        | fc.officers(db, proj.id)
        | fc.reps(db, proj.id, r.engagement_id),
        NotificationKind.critical_item_failure,
        f"Critical item failed on {ins.ref}: {codes}{fc.offline_label(delay, r.completed_at)}",
        f"إخفاق بند حرج في {ins.ref}: {codes}{fc.offline_label_ar(delay, r.completed_at)}",
        proj.id,
        EntityType.inspection,
        ins.id,
    )


# ---- reads ---------------------------------------------------------------------------------------


def can_see(db: Session, p: Principal, r: ChecklistResponse) -> bool:
    if r.inspector_id == p.user.id:
        return True
    g = p.grant(r.project_id, C.field_view)
    if r.owner_type == ResponseOwnerType.audit:
        return g is not None and (g.engagement_ids is None or covers(g, None, r.engagement_id))
    return covers(g, r.site_id, r.engagement_id) or (
        g is not None and g.engagement_ids is not None and r.engagement_id is None
        and g.covers_site(r.site_id)
    )  # fmt: skip


def get_response(db: Session, p: Principal, response_id: uuid.UUID) -> ChecklistResponse:
    r = db.get(ChecklistResponse, response_id)
    if r is None or not p.can_see_project(r.project_id) or not can_see(db, p, r):
        from app.core.errors import not_found  # noqa: PLC0415

        raise not_found("Checklist response")
    return r


def read_response(db: Session, p: Principal, response_id: uuid.UUID) -> ResponseRead:
    return response_read(db, p, get_response(db, p, response_id))


def finding_reads(
    db: Session, rows: list[FieldFinding], owner_refs: dict[uuid.UUID, str] | None = None
) -> list[FieldFindingRead]:
    if not rows:
        return []
    refs = Refs(db).load(
        sites=[f.site_id for f in rows],
        zones=[f.zone_id for f in rows],
        engs=[f.responsible_engagement_id for f in rows],
    )
    rep_ids = {f.repeat_of_id for f in rows if f.repeat_of_id}
    rep_no = (
        dict(
            db.execute(
                select(FieldFinding.id, FieldFinding.finding_no).where(FieldFinding.id.in_(rep_ids))
            ).all()
        )
        if rep_ids
        else {}
    )
    texts: dict[tuple[uuid.UUID, str], tuple[str, str]] = {}
    resp = {
        r.id: r
        for r in db.scalars(
            select(ChecklistResponse).where(ChecklistResponse.id.in_({f.response_id for f in rows}))
        )
    }
    tpls = {
        t.id: t
        for t in db.scalars(
            select(ChecklistTemplate).where(
                ChecklistTemplate.id.in_({r.template_id for r in resp.values()})
            )
        )
    }
    for r in resp.values():
        for it in tpls[r.template_id].items:
            texts[(r.id, it["item_code"])] = (it.get("text_en", ""), it.get("text_ar", ""))
    out = []
    for f in rows:
        ca_ref, ca_status = fc.ca_info(db, f.ca_id)
        tx = texts.get((f.response_id, f.item_code or ""))
        out.append(
            FieldFindingRead(
                id=f.id,
                finding_no=f.finding_no,
                owner_ref=f.finding_no.rsplit("-F", 1)[0],
                item_code=f.item_code,
                item_text_en=tx[0] if tx else None,
                item_text_ar=tx[1] if tx else None,
                severity=f.severity,
                critical_item=f.critical_item,
                description_en=f.description_en,
                description_ar=f.description_ar,
                repeat_of=rep_no.get(f.repeat_of_id) if f.repeat_of_id else None,
                fixed_on_spot=f.fixed_on_spot,
                ca_required=f.ca_required or f.ca_id is not None,
                ca_id=f.ca_id,
                ca_ref=ca_ref,
                ca_status=ca_status,
                responsible_engagement=refs.eng(f.responsible_engagement_id),
                site=refs.site(f.site_id),
                zone=refs.zone(f.zone_id),
                completed_date=f.completed_date,
                voided=f.voided,
            )
        )
    return out


def response_read(db: Session, p: Principal | None, r: ChecklistResponse) -> ResponseRead:
    t = db.get(ChecklistTemplate, r.template_id)
    assert t is not None  # noqa: S101
    refs = Refs(db).load(
        sites=[r.site_id], zones=[r.zone_id], engs=[r.engagement_id], users=[r.inspector_id]
    )
    viewer = p is not None and fc.is_viewer(p, r.project_id)
    ins = db.get(Inspection, r.inspection_id) if r.inspection_id else None
    order = db.get(StopWorkOrder, r.stop_work_order_id) if r.stop_work_order_id else None
    rows = list(
        db.scalars(
            select(FieldFinding)
            .where(FieldFinding.response_id == r.id)
            .order_by(FieldFinding.finding_no)
        )
    )
    answers = []
    for a in r.answers or []:
        nc = a.get("compliant") is False
        answers.append(
            AnswerRead(
                item_code=a["item_code"],
                item_type=ItemType(a["item_type"]),
                answer=a.get("answer"),
                numeric_value=a.get("numeric_value"),
                count_value=a.get("count_value"),
                note=a.get("note"),
                photo_ids=[] if viewer else [uuid.UUID(x) for x in a.get("photo_ids") or []],
                equipment_ref=a.get("equipment_ref"),
                applicable=bool(a.get("applicable")),
                compliant=a.get("compliant"),
                earned_weight=a.get("earned_weight"),
                raise_defect_for=a.get("equipment_ref") if nc and a.get("equipment_ref") else None,
            )
        )
    secs = []
    for s in sorted(t.sections or [], key=lambda x: x.get("order", 0)):
        aw = sum(
            (D(a["weight"]) for a in r.answers or []
             if a.get("section_code") == s["code"] and a.get("weight")), D(0),
        )  # fmt: skip
        ew = sum(
            (D(a["earned_weight"]) for a in r.answers or []
             if a.get("section_code") == s["code"] and a.get("earned_weight")), D(0),
        )  # fmt: skip
        secs.append(
            SectionScore(
                section_code=s["code"],
                title_en=s.get("title_en", ""),
                title_ar=s.get("title_ar", ""),
                applicable_weight=fc.w3(aw),
                earned_weight=fc.w3(ew),
                score_pct=fc.pct_str(ew / aw * 100) if aw else None,
            )
        )
    pm_cfg = fc.cfg(db, r.project_id).dec("inspection_pass_mark_pct")
    pass_mark = (
        str(fc.q1(max(D(t.pass_mark_pct), pm_cfg)))
        if r.owner_type == ResponseOwnerType.inspection
        else None
    )
    return ResponseRead(
        id=r.id,
        client_uuid=r.client_uuid,
        owner_type=r.owner_type,
        inspection_id=r.inspection_id,
        inspection_ref=ins.ref if ins else None,
        audit_id=r.audit_id,
        template_id=r.template_id,
        template_code=r.template_code,
        template_version=r.template_version,
        site=refs.site(r.site_id),
        zone=refs.zone(r.zone_id),
        engagement=refs.eng(r.engagement_id),
        started_at=r.started_at,
        completed_at=r.completed_at,
        received_at=r.received_at,
        offline_delay_min=r.offline_delay_min,
        recorded_offline=r.offline_delay_min is not None,
        inspector=refs.user(r.inspector_id),
        answers=answers,
        applicable_count=r.applicable_count,
        compliant_count=r.compliant_count,
        applicable_weight=fc.w3(r.applicable_weight),
        earned_weight=fc.w3(r.earned_weight),
        score_pct=fc.pct_str(r.score_pct),
        pass_mark_pct=pass_mark,
        critical_fail_count=r.critical_fail_count,
        result=r.result,
        grade=r.grade,
        section_scores=secs,
        findings=finding_reads(db, rows),
        stop_work_order_id=r.stop_work_order_id,
        stop_work_order_no=order.order_no if order else None,
        self_inspection=r.self_inspection,
        submitted=r.submitted,
        voided=r.voided,
        warnings=[ApiWarning(**w) for w in r.warnings or []],
    )


def audit_grade(score: Decimal | None, capped: bool) -> Any:
    return grade_for(score, capped)


# ---- void (EXE-9) --------------------------------------------------------------------------------


def void_inspection(
    db: Session, p: Principal, inspection_id: uuid.UUID, body: InspectionVoid
) -> InspectionRead:
    from app.services import inspections  # noqa: PLC0415

    ins = inspections.get_ins(db, p, inspection_id)
    proj = fc.project(db, p, ins.project_id)
    ensure_open(proj)
    p.require(proj.id, C.field_void)
    why = fc.reason(body.reason, 20)
    if ins.status != ST.completed:
        raise invalid_transition("Inspection", ins.status, ST.voided)
    before = {"status": ins.status.value, "response_id": str(ins.response_id)}
    if ins.response_id:
        r = db.get(ChecklistResponse, ins.response_id)
        if r is not None:
            r.voided = True
            for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == r.id)):
                f.voided = True
    if ins.plan_id and ins.planned_date:
        grace = hse_settings.get(db, proj.id).inspection_grace_days
        late = fc.local_day() > ins.planned_date + timedelta(days=grace)
        ins.status = ST.missed if late else ST.planned
        ins.completed_at = None
        ins.completed_date = None
        ins.inspector_id = None
        ins.items_checked = None
        ins.items_compliant = None
        ins.findings = []
        ins.response_id = None
        ins.offline_delay_min = None
    else:
        ins.status = ST.voided
    ins.void_reason = why
    ins.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.inspection, ins, proj.id,
              before=before, details={"reason": why, "action": "void"})  # fmt: skip
    return inspections.reads(db, [ins])[0]


# ---- findings register ---------------------------------------------------------------------------


def list_findings(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    severity: list[FindingSeverity] | None,
    item_code: str | None,
    repeat: bool | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> FieldFindingPage:
    fc.project(db, p, project_id)
    g = fc.view_grant(p, project_id)
    F = FieldFinding  # noqa: N806
    stmt = select(F).where(F.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(F.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        stmt = stmt.where(
            or_(F.responsible_engagement_id.in_(engs), F.engagement_id.in_(engs))
            if engs
            else false()
        )
    if site_id:
        stmt = stmt.where(F.site_id == site_id)
    if engagement_id:
        stmt = stmt.where(F.responsible_engagement_id == engagement_id)
    if severity:
        stmt = stmt.where(F.severity.in_(severity))
    if item_code:
        stmt = stmt.where(F.item_code == item_code)
    if repeat is not None:
        stmt = stmt.where(F.repeat_of_id.is_not(None) if repeat else F.repeat_of_id.is_(None))
    if date_from:
        stmt = stmt.where(F.completed_date >= date_from)
    if date_to:
        stmt = stmt.where(F.completed_date <= date_to)
    items, total = paginate(
        db, stmt.order_by(F.completed_date.desc(), F.finding_no.desc()), page, page_size
    )
    return FieldFindingPage(
        items=finding_reads(db, list(items)), total=total, page=page, page_size=page_size
    )


# ---- offline pack (EXE-6, P6d-6) -----------------------------------------------------------------


def offline_pack(db: Session, p: Principal, project_id: uuid.UUID) -> OfflinePack:
    fc.project(db, p, project_id)
    g = p.grant(project_id, C.inspection_record) or p.grant(project_id, C.toolbox_record)
    if g is None:
        raise forbidden_error()
    today = fc.local_day()
    In = Inspection  # noqa: N806
    stmt = select(In).where(
        In.project_id == project_id,
        In.status.in_((ST.planned, ST.missed)),
        In.planned_date >= today - timedelta(days=7),
        In.planned_date <= today + timedelta(days=3),
    )
    mine = In.assignee_user_id == p.user.id
    gi = p.grant(project_id, C.inspection_record)
    if gi is None:
        stmt = stmt.where(mine)
    else:
        conds: list[Any] = []
        if gi.site_ids is not None:
            conds.append(In.site_id.in_(gi.site_ids) if gi.site_ids else false())
        if gi.engagement_ids is not None:
            engs = list(gi.engagement_ids)
            conds.append(In.engagement_id.in_(engs) if engs else false())
        if conds:
            stmt = stmt.where(or_(and_(*conds), mine))
    inst = list(db.scalars(stmt.order_by(In.planned_date)))
    plans = {
        pl.id: pl
        for pl in db.scalars(
            select(InspectionPlan).where(InspectionPlan.id.in_({i.plan_id for i in inst}))
        )
    }
    templates = [
        t
        for t in db.scalars(
            select(ChecklistTemplate)
            .where(ChecklistTemplate.status == VersionStatus.published)
            .order_by(ChecklistTemplate.template_code)
        )
        if library.offered(t, project_id)
    ]
    tid = {t.template_code: t.id for t in templates}
    topics = list(
        db.scalars(
            select(ToolboxTopic)
            .where(ToolboxTopic.status == VersionStatus.published)
            .order_by(ToolboxTopic.topic_code)
        )
    )
    dq = (
        select(Deployment, Worker)
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(Deployment.project_id == project_id, Deployment.status == DeploymentStatus.mobilised)
    )
    if g.engagement_ids is not None:
        dq = dq.where(Deployment.engagement_id.in_(list(g.engagement_ids) or [uuid.UUID(int=0)]))
    deps = [
        OfflineDeployment(
            deployment_id=d.id,
            worker_no=w.worker_no,
            name_en=w.full_name_en,
            name_ar=w.full_name_ar,
            trade=d.trade.value,
            primary_language=w.primary_language,
            engagement_id=d.engagement_id,
        )
        for d, w in db.execute(dq.order_by(Worker.worker_no)).all()
        if g.site_ids is None or set(d.site_ids or []) & set(g.site_ids)
    ]
    gen = now()
    return OfflinePack(
        project_id=project_id,
        generated_at=gen,
        expires_at=gen + timedelta(hours=int(fc.cfg(db, project_id)["offline_cache_hours"])),
        instances=[
            OfflineInstance(
                inspection_id=i.id,
                ref=i.ref,
                planned_date=i.planned_date,
                site_id=i.site_id,
                zone_id=i.zone_id,
                engagement_id=i.engagement_id,
                template_id=tid.get(plans[i.plan_id].template_code or "")
                if i.plan_id in plans
                else None,
            )
            for i in inst
        ],
        templates=[library.template_read(db, t) for t in templates],
        topics=[library.topic_read(t) for t in topics],
        deployments=deps,
    )
