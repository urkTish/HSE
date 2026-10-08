"""JSA / risk assessment: templates and permit instances (spec 3-ptw §3.8, §4.3, JS-1…JS-10, §6.1).

Steps are stored as JSON; every hazard line carries a stable id. Scores and bands are derived
on read. A permit's JSA is approved by the permit Approve (DECISIONS) or by an explicit
transition of an appointed issuer; templates by an HSE Officer / Manager (capability 96)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.hse_enums import HIGHER_CONTROLS, ControlLevel
from app.core.ptw_enums import (
    PERMIT_TERMINAL,
    AppointmentFunction,
    Exposure,
    Hazard,
    JsaStatus,
    JsaWarningCode,
    PermitStatus,
    PermitType,
    RiskBand,
    SignaturePurpose,
)
from app.kpi.periods import add_months
from app.models import Jsa, Permit
from app.schemas.jsa import (
    CrewBriefingRead,
    JsaControlRead,
    JsaHazardLineRead,
    JsaInstanceCreate,
    JsaListItem,
    JsaPage,
    JsaRead,
    JsaStepInput,
    JsaStepRead,
    JsaTemplateCreate,
    JsaTemplateRef,
    JsaTransition,
    JsaUpdate,
    ResidualAcceptanceInput,
    ResidualAcceptanceRead,
)
from app.services import audit, notify, projects
from app.services.access import common as acommon
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, user_roles
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common, rules

C = Capability
BAND_ACCEPTORS: dict[RiskBand, tuple[str, ...]] = {
    RiskBand.low: ("receiver",),
    RiskBand.medium: ("issuer",),
    RiskBand.high: ("issuer", "hse"),
}
ALERT_DAYS = (30, 0)


# ---- line maths ----------------------------------------------------------------------------------


def _lines(j: Jsa) -> list[dict[str, Any]]:
    return [h for s in j.steps or [] for h in s.get("hazards", [])]


def line_facts(h: dict[str, Any]) -> dict[str, Any]:
    i_score = h["initial_l"] * h["initial_s"]
    r_score = h["residual_l"] * h["residual_s"]
    levels = {ControlLevel(c["level"]) for c in h.get("controls", [])}
    higher = bool(levels & HIGHER_CONTROLS)
    warnings = []
    if h["residual_s"] < h["initial_s"] and not higher:
        warnings.append(JsaWarningCode.SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL)
    return {
        "initial_score": i_score,
        "initial_band": rules.band(i_score),
        "residual_score": r_score,
        "residual_band": rules.band(r_score),
        "higher": higher,
        "ppe_only": bool(levels) and levels == {ControlLevel.ppe},
        "warnings": warnings,
    }


def governing_band(j: Jsa) -> RiskBand | None:
    scores = [h["residual_l"] * h["residual_s"] for h in _lines(j)]
    return rules.band(max(scores)) if scores else None


def has_extreme(j: Jsa) -> bool:
    return any(line_facts(h)["residual_band"] == RiskBand.extreme for h in _lines(j))


def required_roles(j: Jsa) -> tuple[str, ...]:
    b = governing_band(j)
    return BAND_ACCEPTORS.get(b, ()) if b else ()


def missing_acceptances(j: Jsa) -> list[str]:
    band = governing_band(j)
    have = {a["as"] for a in j.residual_acceptances or [] if a.get("band") == (band or "")}
    return [r for r in required_roles(j) if r not in have]


def _validate_steps(steps: list[JsaStepInput]) -> list[dict[str, Any]]:
    """JS-5 (residual ≤ initial) and JS-8 (PPE-only cannot lower the band); returns JSON."""
    out = []
    nos = [s.step_no for s in steps]
    if len(set(nos)) != len(nos):
        raise validation_error("steps", "Step numbers must be unique.")
    for si, s in enumerate(sorted(steps, key=lambda x: x.step_no)):
        hazards = []
        for hi, h in enumerate(s.hazards):
            loc = f"steps.{si}.hazards.{hi}"
            if h.residual_l > h.initial_l or h.residual_s > h.initial_s:
                raise common.err(
                    ErrorCode.RESIDUAL_ABOVE_INITIAL,
                    "Residual likelihood and severity cannot exceed the initial values.",
                    "لا يمكن أن يتجاوز الاحتمال والشدة المتبقيان القيم الأولية.",
                    field=loc,
                )
            row = {
                "id": str(uuid.uuid4()),
                "hazard_code": h.hazard_code.value,
                "description": h.description,
                "initial_l": h.initial_l,
                "initial_s": h.initial_s,
                "controls": [{"text": c.text, "level": c.level.value} for c in h.controls],
                "residual_l": h.residual_l,
                "residual_s": h.residual_s,
            }
            f = line_facts(row)
            if (
                f["ppe_only"]
                and rules.BAND_RANK[f["residual_band"]] < rules.BAND_RANK[f["initial_band"]]
            ):
                raise common.err(
                    ErrorCode.PPE_ONLY_CONTROLS,
                    "PPE-only controls cannot lower the risk band (JS-8).",
                    "ضوابط معدات الحماية الشخصية وحدها لا تخفض فئة الخطر.",
                    field=loc,
                )
            hazards.append(row)
        out.append(
            {
                "step_no": s.step_no,
                "description_en": s.description_en,
                "description_ar": s.description_ar,
                "hazards": hazards,
            }
        )
    return out


def _copy_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in steps:
        out.append(
            {
                **s,
                "hazards": [
                    {**h, "id": str(uuid.uuid4()), "controls": [dict(c) for c in h["controls"]]}
                    for h in s.get("hazards", [])
                ],
            }
        )
    return out


# ---- mandatory hazards (JS-4) --------------------------------------------------------------------


def mandatory(db: Session, j: Jsa) -> list[Hazard]:
    if j.permit_id:
        permit = db.get(Permit, j.permit_id)
        if permit is not None:
            from app.services.ptw import facts  # noqa: PLC0415

            return facts.compute(db, permit).hazards
    return rules.mandatory_hazards(list(j.work_types or []), {}, Exposure.indoor, [], ("", ""), {})


def missing_hazards(db: Session, j: Jsa) -> list[Hazard]:
    present = {h["hazard_code"] for h in _lines(j)}
    return [h for h in mandatory(db, j) if h.value not in present]


# ---- read models ---------------------------------------------------------------------------------


def _template_ref(db: Session, tid: uuid.UUID | None) -> JsaTemplateRef | None:
    t = db.get(Jsa, tid) if tid else None
    if t is None:
        return None
    return JsaTemplateRef(
        id=t.id,
        jsa_no=t.jsa_no,
        title_en=t.title_en,
        status=t.status,
        review_due_on=t.review_due_on,
    )


def _shift_no(db: Session, shift_id: Any) -> int:
    from app.models import PermitShift  # noqa: PLC0415

    s = db.get(PermitShift, uuid.UUID(str(shift_id))) if shift_id else None
    return s.shift_no if s else 0


def to_read(db: Session, j: Jsa, refs: Refs | None = None) -> JsaRead:
    refs = refs or Refs(db)
    permit = db.get(Permit, j.permit_id) if j.permit_id else None
    steps = []
    max_i = max_r = None
    for s in j.steps or []:
        lines = []
        for h in s.get("hazards", []):
            f = line_facts(h)
            max_i = max(max_i or 0, f["initial_score"])
            max_r = max(max_r or 0, f["residual_score"])
            lines.append(
                JsaHazardLineRead(
                    id=uuid.UUID(h["id"]),
                    hazard_code=Hazard(h["hazard_code"]),
                    description=h["description"],
                    initial_l=h["initial_l"],
                    initial_s=h["initial_s"],
                    initial_score=f["initial_score"],
                    initial_band=f["initial_band"],
                    controls=[
                        JsaControlRead(text=c["text"], level=ControlLevel(c["level"]))
                        for c in h["controls"]
                    ],
                    residual_l=h["residual_l"],
                    residual_s=h["residual_s"],
                    residual_score=f["residual_score"],
                    residual_band=f["residual_band"],
                    has_higher_control=f["higher"],
                    warnings=f["warnings"],
                )
            )
        steps.append(
            JsaStepRead(
                step_no=s["step_no"],
                description_en=s["description_en"],
                description_ar=s.get("description_ar"),
                hazards=lines,
            )
        )
    accs = []
    for a in j.residual_acceptances or []:
        u = refs.user(uuid.UUID(a["user_id"]))
        if u:
            accs.append(
                ResidualAcceptanceRead(
                    band=RiskBand(a["band"]),
                    accepted_by=u,
                    accepted_as=a["as"],
                    accepted_at=datetime.fromisoformat(a["at"]),
                    alarp_justification=a.get("alarp"),
                )
            )
    briefings = []
    for b in j.crew_briefings or []:
        u = refs.user(uuid.UUID(b["briefed_by_user_id"]))
        if u:
            briefings.append(
                CrewBriefingRead(
                    shift_no=b.get("shift_no") or _shift_no(db, b.get("shift_id")),
                    worker_count=len(b.get("worker_ids", [])),
                    briefed_by=u,
                    at=datetime.fromisoformat(b["at"]),
                )
            )
    created = refs.user(j.created_by_user_id)
    if created is None:
        created = refs.user(j.approved_by_user_id) or _system_user()
    mand = mandatory(db, j)
    present = {h["hazard_code"] for h in _lines(j)}
    return JsaRead(
        id=j.id,
        project_id=j.project_id,
        jsa_no=j.jsa_no,
        revision=j.revision,
        is_template=j.is_template,
        template=_template_ref(db, j.template_id),
        engagement=refs.eng(j.engagement_id),
        permit=common.permit_ref(permit) if permit else None,
        work_types=[PermitType(t) for t in j.work_types],
        title_en=j.title_en,
        title_ar=j.title_ar,
        steps=steps,
        governing_residual_band=governing_band(j),
        max_initial_score=max_i,
        max_residual_score=max_r,
        mandatory_hazards=mand,
        missing_mandatory_hazards=[h for h in mand if h.value not in present],
        required_acceptances=[] if j.is_template else missing_acceptances(j),
        residual_acceptances=accs,
        review_due_on=j.review_due_on,
        status=j.status,
        returned_comment=j.returned_comment,
        approved_by=refs.user(j.approved_by_user_id),
        approved_at=j.approved_at,
        crew_briefings=briefings,
        created_by=created,
        created_at=j.created_at,
        updated_at=j.updated_at,
    )


def _system_user() -> Any:
    from app.schemas.hse_common import UserRef  # noqa: PLC0415

    return UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام")


def list_item(db: Session, j: Jsa, refs: Refs) -> JsaListItem:
    permit = db.get(Permit, j.permit_id) if j.permit_id else None
    return JsaListItem(
        id=j.id,
        jsa_no=j.jsa_no,
        revision=j.revision,
        is_template=j.is_template,
        engagement=refs.eng(j.engagement_id),
        permit=common.permit_ref(permit) if permit else None,
        work_types=[PermitType(t) for t in j.work_types],
        title_en=j.title_en,
        title_ar=j.title_ar,
        governing_residual_band=governing_band(j),
        status=j.status,
        review_due_on=j.review_due_on,
        updated_at=j.updated_at,
    )


# ---- access --------------------------------------------------------------------------------------


def _view_template(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    projects.get_visible(db, p, project_id)
    if p.grant(project_id, C.permit_view) is None and (
        p.grant(project_id, C.jsa_template_manage) is None
    ):
        raise forbidden_error()


def get_row(db: Session, p: Principal, jsa_id: uuid.UUID) -> Jsa:
    j = db.get(Jsa, jsa_id)
    if j is None:
        raise not_found("JSA")
    if j.permit_id:
        common.get_permit(db, p, j.permit_id)
    else:
        _view_template(db, p, j.project_id)
        g = p.grant(j.project_id, C.permit_view) or p.grant(j.project_id, C.jsa_template_manage)
        if j.engagement_id and g is not None and not g.covers_engagement(j.engagement_id):
            raise forbidden_error("This JSA template is outside your scope.")
    return j


def _require_edit(db: Session, p: Principal, j: Jsa) -> Permit | None:
    if j.permit_id:
        permit = db.get(Permit, j.permit_id)
        assert permit is not None  # noqa: S101
        acommon.require_cap(
            p, j.project_id, C.permit_prepare, [permit.site_id], permit.engagement_id
        )
        return permit
    acommon.require_cap(p, j.project_id, C.jsa_template_manage, None, j.engagement_id)
    return None


def _is_hse(db: Session, p: Principal, project_id: uuid.UUID) -> bool:
    return p.is_manager or Role.hse_officer in user_roles(db, p.user.id, project_id)


def _audit(
    db: Session,
    p: Principal | None,
    j: Jsa,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(j.project_id) if p else audit.SYSTEM,
        entity_type=EntityType.jsa,
        entity_id=j.id,
        project_id=j.project_id,
        before=before,
        after=after,
        details=details,
    )


# ---- templates -----------------------------------------------------------------------------------


def list_templates(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    work_types: list[PermitType] | None,
    statuses: list[JsaStatus] | None,
    engagement_id: uuid.UUID | None,
    review_due: bool | None,
    q: str | None,
) -> JsaPage:
    _view_template(db, p, project_id)
    g = p.grant(project_id, C.permit_view) or p.grant(project_id, C.jsa_template_manage)
    stmt = select(Jsa).where(Jsa.project_id == project_id, Jsa.is_template.is_(True))
    if g is not None and g.engagement_ids is not None:
        stmt = stmt.where(
            or_(Jsa.engagement_id.is_(None), Jsa.engagement_id.in_(list(g.engagement_ids)))
        )
    if work_types:
        stmt = stmt.where(Jsa.work_types.overlap([t.value for t in work_types]))
    if statuses:
        stmt = stmt.where(Jsa.status.in_(statuses))
    else:
        stmt = stmt.where(Jsa.status != JsaStatus.superseded)
    if engagement_id:
        stmt = stmt.where(Jsa.engagement_id == engagement_id)
    if review_due is not None:
        stmt = stmt.where(
            (Jsa.status == JsaStatus.review_due)
            if review_due
            else (Jsa.status != JsaStatus.review_due)
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Jsa.jsa_no.ilike(like), Jsa.title_en.ilike(like)))
    rows, total = paginate(db, stmt.order_by(Jsa.jsa_no, Jsa.revision), page, size)
    refs = Refs(db).load(engs=[r.engagement_id for r in rows])
    return JsaPage(
        items=[list_item(db, r, refs) for r in rows], total=total, page=page, page_size=size
    )


def create_template(
    db: Session, p: Principal, project_id: uuid.UUID, body: JsaTemplateCreate
) -> JsaRead:
    projects.get_visible(db, p, project_id)
    acommon.require_cap(p, project_id, C.jsa_template_manage, None, body.engagement_id)
    g = p.grant(project_id, C.jsa_template_manage)
    if body.engagement_id is None and g is not None and g.engagement_ids is not None:
        raise forbidden_error("Contractor representatives propose templates for their engagement.")
    if body.engagement_id is not None:
        from app.models import ProjectEngagement  # noqa: PLC0415

        e = db.get(ProjectEngagement, body.engagement_id)
        if e is None or e.project_id != project_id:
            raise validation_error("engagement_id", "Engagement is not on this project.")
    seq = (
        db.scalar(
            select(func.max(Jsa.seq)).where(Jsa.project_id == project_id, Jsa.is_template.is_(True))
        )
        or 0
    ) + 1
    j = Jsa(
        id=uuid.uuid4(),
        project_id=project_id,
        jsa_no=f"JSA-T-{common.project_code(db, project_id)}-{seq:04d}",
        seq=seq,
        revision=0,
        is_template=True,
        engagement_id=body.engagement_id,
        work_types=[t.value for t in body.work_types],
        title_en=body.title_en,
        title_ar=body.title_ar,
        steps=_validate_steps(body.steps),
        residual_acceptances=[],
        crew_briefings=[],
        status=JsaStatus.draft,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(j)
    db.flush()
    _audit(db, p, j, AuditAction.create, None, {"jsa_no": j.jsa_no, "status": j.status.value})
    return to_read(db, j)


# ---- permit instance -----------------------------------------------------------------------------


def instance_no(permit: Permit) -> str:
    return "JSA-" + permit.permit_no.removeprefix("PTW-")


def current_for_permit(db: Session, permit: Permit) -> Jsa | None:
    return db.get(Jsa, permit.jsa_id) if permit.jsa_id else None


def create_instance(
    db: Session, p: Principal, permit_id: uuid.UUID, body: JsaInstanceCreate
) -> JsaRead:
    permit = common.get_permit(db, p, permit_id)
    acommon.require_cap(
        p, permit.project_id, C.permit_prepare, [permit.site_id], permit.engagement_id
    )
    if permit.status in PERMIT_TERMINAL:
        raise common.err(
            ErrorCode.PERMIT_READ_ONLY, "The permit is closed.", "التصريح مغلق.", status=409
        )
    if permit.jsa_id is not None:
        raise duplicate("permit_id", "The permit already has a JSA (one per permit, JS-1).")
    template = None
    if body.template_id:
        template = db.get(Jsa, body.template_id)
        if template is None or not template.is_template or template.project_id != permit.project_id:
            raise validation_error("template_id", "Template not found on this project.")
        if template.status == JsaStatus.review_due or (
            template.review_due_on is not None and template.review_due_on < today()
        ):
            raise common.err(
                ErrorCode.TEMPLATE_REVIEW_DUE,
                f"{template.jsa_no} is due for review and cannot be copied (JS-9).",
                f"القالب {template.jsa_no} مستحق المراجعة ولا يمكن نسخه.",
                field="template_id",
            )
        if template.status != JsaStatus.approved:
            raise validation_error("template_id", "Only Approved templates can be copied.")
    if body.steps is not None:
        steps = _validate_steps(body.steps)
    elif template is not None:
        steps = _copy_steps(template.steps)
    else:
        raise validation_error("steps", "Give steps or a template_id.")
    if body.work_types:
        types = [t.value for t in body.work_types]
    elif template is not None:
        types = list(dict.fromkeys([*template.work_types, *permit.work_types]))
    else:
        types = list(permit.work_types)
    _check_types(types, permit)
    j = Jsa(
        id=uuid.uuid4(),
        project_id=permit.project_id,
        jsa_no=instance_no(permit),
        seq=permit.seq,
        revision=0,
        is_template=False,
        template_id=template.id if template else None,
        engagement_id=permit.engagement_id,
        permit_id=permit.id,
        work_types=types,
        title_en=body.title_en or (template.title_en if template else permit.title),
        title_ar=body.title_ar or (template.title_ar if template else None),
        steps=steps,
        residual_acceptances=[],
        crew_briefings=[],
        status=JsaStatus.draft,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(j)
    db.flush()
    permit.jsa_id = j.id
    db.flush()
    _audit(db, p, j, AuditAction.create, None, {"jsa_no": j.jsa_no, "permit": permit.permit_no})
    _refresh(db, permit)
    return to_read(db, j)


def _check_types(types: list[str], permit: Permit) -> None:
    missing = [t for t in permit.work_types if t not in types]
    if missing:
        raise common.err(
            ErrorCode.JSA_TYPE_MISMATCH,
            f"The JSA must cover every permit type (missing {', '.join(missing)}).",
            f"يجب أن يغطي تحليل السلامة كل أنواع التصريح (ناقص {', '.join(missing)}).",
            field="work_types",
            meta={"missing": missing},
        )


def _refresh(db: Session, permit: Permit | None) -> None:
    if permit is None or permit.status in PERMIT_TERMINAL:
        return
    from app.services.ptw import evaluation  # noqa: PLC0415

    evaluation.refresh(db, permit)


# ---- edit / transitions --------------------------------------------------------------------------


def update(db: Session, p: Principal, jsa_id: uuid.UUID, body: JsaUpdate) -> JsaRead:
    j = get_row(db, p, jsa_id)
    permit = _require_edit(db, p, j)
    if j.status != JsaStatus.draft:
        raise common.err(
            ErrorCode.JSA_FROZEN,
            "Only a Draft JSA can be edited; create a revision instead (JS-10).",
            "يمكن تعديل المسودة فقط؛ أنشئ مراجعة جديدة بدلاً من ذلك.",
            status=409,
        )
    ch = body.changes()
    before = {"work_types": list(j.work_types), "title_en": j.title_en, "steps": len(j.steps)}
    if "work_types" in ch:
        types = [t.value for t in body.work_types or []]
        if permit is not None:
            _check_types(types, permit)
        j.work_types = types
    if "title_en" in ch:
        j.title_en = body.title_en or j.title_en
    if "title_ar" in ch:
        j.title_ar = body.title_ar
    if "steps" in ch:
        j.steps = _validate_steps(body.steps or [])
    j.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        j,
        AuditAction.update,
        before,
        {"work_types": list(j.work_types), "title_en": j.title_en, "steps": len(j.steps)},
    )
    _refresh(db, permit)
    return to_read(db, j)


def _issuer_ok(db: Session, p: Principal, permit: Permit) -> bool:
    if p.grant(permit.project_id, C.permit_issue) is None:
        return False
    if permit.issuer_user_id and permit.issuer_user_id != p.user.id:
        return False
    if p.user.id == permit.receiver_user_id:
        return False
    return (
        common.find_appointment(
            db,
            permit.project_id,
            AppointmentFunction.issuer,
            permit.work_types,
            permit.site_id,
            [],
            common.permit_days(permit),
            user_id=p.user.id,
        )
        is not None
    )


def _ensure_acceptable(j: Jsa) -> None:
    if has_extreme(j):
        raise common.err(
            ErrorCode.JSA_RESIDUAL_EXTREME,
            "A line has an Extreme residual risk: redesign the task (JS-6).",
            "يوجد خطر متبقٍ حرج: أعد تصميم المهمة.",
        )
    missing = missing_acceptances(j)
    if missing:
        raise common.err(
            ErrorCode.RESIDUAL_ACCEPTANCE_MISSING,
            f"Residual risk acceptance missing: {', '.join(missing)} (JS-7).",
            f"قبول الخطر المتبقي ناقص: {', '.join(missing)}.",
            meta={"missing": missing},
        )


def _submit_checks(db: Session, j: Jsa, permit: Permit | None) -> None:
    if not _lines(j):
        raise validation_error("steps", "Every JSA needs at least one hazard line.")
    if permit is not None:
        _check_types(list(j.work_types), permit)
    miss = missing_hazards(db, j)
    if miss:
        names = ", ".join(h.value for h in miss)
        raise common.err(
            ErrorCode.JSA_MANDATORY_HAZARD_MISSING,
            f"Mandatory hazards missing: {names} (JS-4).",
            f"مخاطر إلزامية ناقصة: {names}.",
            meta={"missing": [h.value for h in miss]},
        )


def approve(db: Session, p: Principal | None, j: Jsa, user_id: uuid.UUID | None) -> None:
    """Submitted → Approved (instances: from the permit Approve or the issuer's transition)."""
    j.status = JsaStatus.approved
    j.approved_by_user_id = user_id
    j.approved_at = now()
    if j.is_template:
        s = common.settings(db, j.project_id)
        j.review_due_on = add_months(today(), s.jsa_review_months)
        j.alerts_sent = []
    for old in db.scalars(
        select(Jsa).where(
            Jsa.project_id == j.project_id,
            Jsa.jsa_no == j.jsa_no,
            Jsa.id != j.id,
            Jsa.status.in_([JsaStatus.approved, JsaStatus.review_due]),
        )
    ):
        prev = old.status
        old.status = JsaStatus.superseded
        old.superseded_by_id = j.id
        _audit(
            db, p, old, AuditAction.status_change, {"status": prev.value}, {"status": "superseded"}
        )
    db.flush()


def transition(db: Session, p: Principal, jsa_id: uuid.UUID, body: JsaTransition) -> JsaRead:
    j = get_row(db, p, jsa_id)
    permit = db.get(Permit, j.permit_id) if j.permit_id else None
    src, to = j.status, body.to_status
    allowed = {
        JsaStatus.draft: {JsaStatus.submitted},
        JsaStatus.submitted: {JsaStatus.approved, JsaStatus.draft},
    }
    if to not in allowed.get(src, set()):
        raise invalid_transition("JSA", src, to)
    if to == JsaStatus.submitted:
        _require_edit(db, p, j)
        _submit_checks(db, j, permit)
    elif to == JsaStatus.draft:
        if not body.comment or len(body.comment.strip()) < 10:
            raise validation_error("comment", "A comment of at least 10 characters is required.")
        _require_approver(db, p, j, permit, returning=True)
        j.returned_comment = body.comment.strip()
        j.residual_acceptances = []
    else:
        _require_approver(db, p, j, permit, returning=False)
        if permit is not None:
            common.require_reauth(db, p, j.project_id)
            _submit_checks(db, j, permit)
            _ensure_acceptable(j)
    if to == JsaStatus.approved:
        approve(db, p, j, p.user.id)
        if permit is not None:
            common.sign(
                db,
                permit,
                SignaturePurpose.approve,
                "issuer",
                user_id=p.user.id,
                entity_id=j.id,
            )
    else:
        j.status = to
    j.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        j,
        AuditAction.status_change,
        {"status": src.value},
        {"status": to.value},
        {"comment": body.comment} if body.comment else None,
    )
    if permit is not None and to == JsaStatus.draft:
        common.tell(
            db,
            permit,
            [permit.receiver_user_id, j.created_by_user_id] if j.created_by_user_id else [],
            NotificationKind.permit_update,
            f"JSA returned: {j.returned_comment}",
            f"أعيد تحليل السلامة: {j.returned_comment}",
        )
    _refresh(db, permit)
    return to_read(db, j)


def _require_approver(
    db: Session, p: Principal, j: Jsa, permit: Permit | None, *, returning: bool
) -> None:
    p.ensure_writer()
    if permit is None:
        acommon.require_cap(p, j.project_id, C.jsa_template_manage, None, j.engagement_id)
        if not _is_hse(db, p, j.project_id):
            raise forbidden_error(
                "Templates are approved or returned by an HSE Officer or the HSE Manager."
            )
        return
    if returning and (
        p.grant(permit.project_id, C.permit_area_review)
        or p.grant(permit.project_id, C.permit_hse_review)
    ):
        return
    if not _issuer_ok(db, p, permit):
        raise forbidden_error("Only an appointed issuer of this permit can approve its JSA.")


# ---- residual acceptance (JS-7) ------------------------------------------------------------------


def accept(db: Session, p: Principal, jsa_id: uuid.UUID, body: ResidualAcceptanceInput) -> JsaRead:
    j = get_row(db, p, jsa_id)
    p.ensure_writer()
    if j.is_template or not j.permit_id:
        raise validation_error("jsa_id", "Residual risk is accepted on a permit's JSA.")
    permit = db.get(Permit, j.permit_id)
    assert permit is not None  # noqa: S101
    if j.status != JsaStatus.submitted:
        raise invalid_transition("JSA", j.status, "residual_acceptance")
    band = governing_band(j)
    if band is None:
        raise validation_error("steps", "The JSA has no hazard lines.")
    if band == RiskBand.extreme:
        raise common.err(
            ErrorCode.JSA_RESIDUAL_EXTREME,
            "An Extreme residual risk cannot be accepted (JS-6).",
            "لا يمكن قبول خطر متبقٍ حرج.",
        )
    missing = missing_acceptances(j)
    capacities = [r for r in missing if _can_accept(db, p, permit, r)]
    if not capacities:
        if not missing:
            raise common.err(
                ErrorCode.INVALID_TRANSITION,
                "Residual risk is already fully accepted.",
                "تم قبول الخطر المتبقي بالكامل.",
                status=409,
            )
        raise forbidden_error(
            f"This {band.value} residual risk must be accepted by: {', '.join(missing)}."
        )
    role = capacities[0]
    alarp = body.alarp_justification
    if band == RiskBand.high:
        if j.created_by_user_id == p.user.id:
            raise common.err(
                ErrorCode.SOD_CONFLICT,
                "The JSA author cannot accept its High residual risk (PR-5 i).",
                "لا يمكن لكاتب التحليل قبول خطره المتبقي المرتفع.",
            )
        if role == "hse":
            if not alarp or len(alarp.strip()) < 30:
                raise validation_error(
                    "alarp_justification",
                    "An ALARP justification of at least 30 characters is required.",
                )
            for h in _lines(j):
                f = line_facts(h)
                if f["residual_band"] == RiskBand.high and not f["higher"]:
                    raise common.err(
                        ErrorCode.HIGHER_CONTROL_REQUIRED,
                        f"High line '{h['description']}' needs an engineering-or-higher control.",
                        f"البند المرتفع '{h['description']}' يحتاج ضابطاً هندسياً أو أعلى.",
                    )
    common.require_reauth(db, p, j.project_id)
    at = now()
    j.residual_acceptances = [
        *(j.residual_acceptances or []),
        {
            "band": band.value,
            "user_id": str(p.user.id),
            "as": role,
            "at": at.isoformat(),
            "alarp": alarp.strip() if alarp else None,
        },
    ]
    common.sign(
        db,
        permit,
        SignaturePurpose.residual_acceptance,
        {"receiver": "permit_receiver", "issuer": "issuer", "hse": "hse_reviewer"}[role],
        user_id=p.user.id,
        entity_id=j.id,
        at=at,
    )
    db.flush()
    _audit(
        db,
        p,
        j,
        AuditAction.update,
        None,
        {"residual_acceptance": role, "band": band.value},
    )
    _refresh(db, permit)
    return to_read(db, j)


def _can_accept(db: Session, p: Principal, permit: Permit, role: str) -> bool:
    if role == "receiver":
        return p.user.id == permit.receiver_user_id
    if role == "issuer":
        return _issuer_ok(db, p, permit)
    return p.grant(permit.project_id, C.permit_hse_review) is not None


# ---- revisions -----------------------------------------------------------------------------------


def revise(db: Session, p: Principal, jsa_id: uuid.UUID) -> JsaRead:
    j = get_row(db, p, jsa_id)
    permit = _require_edit(db, p, j)
    if j.status not in (JsaStatus.approved, JsaStatus.review_due):
        raise invalid_transition("JSA", j.status, "revision")
    latest = db.scalar(
        select(func.max(Jsa.revision)).where(Jsa.project_id == j.project_id, Jsa.jsa_no == j.jsa_no)
    )
    pending = db.scalar(
        select(Jsa.id).where(
            Jsa.project_id == j.project_id,
            Jsa.jsa_no == j.jsa_no,
            Jsa.status.in_([JsaStatus.draft, JsaStatus.submitted]),
        )
    )
    if pending:
        raise duplicate("jsa_id", "A draft revision already exists.")
    if permit is not None and permit.status in PERMIT_TERMINAL:
        raise common.err(
            ErrorCode.PERMIT_READ_ONLY, "The permit is closed.", "التصريح مغلق.", status=409
        )
    n = Jsa(
        id=uuid.uuid4(),
        project_id=j.project_id,
        jsa_no=j.jsa_no,
        seq=j.seq,
        revision=(latest or 0) + 1,
        is_template=j.is_template,
        template_id=j.template_id,
        engagement_id=j.engagement_id,
        permit_id=j.permit_id,
        work_types=list(j.work_types),
        title_en=j.title_en,
        title_ar=j.title_ar,
        steps=_copy_steps(j.steps),
        residual_acceptances=[],
        crew_briefings=[],
        status=JsaStatus.draft,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(n)
    db.flush()
    _audit(db, p, n, AuditAction.create, None, {"jsa_no": n.jsa_no, "revision": n.revision})
    if permit is not None:
        permit.jsa_id = n.id
        if permit.status in (PermitStatus.approved, PermitStatus.issued):
            # JS-10 / PT-13: control changes return the permit to Reviewed
            from app.services.ptw import lifecycle  # noqa: PLC0415

            lifecycle.back_to_reviewed(db, p, permit, "JSA revision")
        db.flush()
        _refresh(db, permit)
    return to_read(db, n)


def revisions(db: Session, p: Principal, jsa_id: uuid.UUID) -> list[JsaListItem]:
    j = get_row(db, p, jsa_id)
    rows = list(
        db.scalars(
            select(Jsa)
            .where(Jsa.project_id == j.project_id, Jsa.jsa_no == j.jsa_no)
            .order_by(Jsa.revision)
        )
    )
    refs = Refs(db).load(engs=[r.engagement_id for r in rows])
    return [list_item(db, r, refs) for r in rows]


def read(db: Session, p: Principal, jsa_id: uuid.UUID) -> JsaRead:
    return to_read(db, get_row(db, p, jsa_id))


# ---- briefings / job -----------------------------------------------------------------------------


def record_briefing(
    db: Session,
    j: Jsa | None,
    shift_id: uuid.UUID,
    shift_no: int,
    workers: list[uuid.UUID],
    by: uuid.UUID,
) -> None:
    if j is None:
        return
    j.crew_briefings = [
        *(j.crew_briefings or []),
        {
            "shift_id": str(shift_id),
            "shift_no": shift_no,
            "worker_ids": [str(w) for w in workers],
            "briefed_by_user_id": str(by),
            "at": now().isoformat(),
        },
    ]


def daily_job(db: Session, at: datetime | None = None) -> int:
    """§4.3 Approved template → Review Due when today > review_due_on; alerts 30 / 0 days."""
    at = at or now()
    day = acommon.local_day(at)
    n = 0
    for t in db.scalars(
        select(Jsa).where(Jsa.is_template.is_(True), Jsa.status == JsaStatus.approved)
    ):
        if t.review_due_on is None:
            continue
        left = (t.review_due_on - day).days
        if day > t.review_due_on:
            t.status = JsaStatus.review_due
            _audit(
                db,
                None,
                t,
                AuditAction.status_change,
                {"status": "approved"},
                {"status": "review_due"},
            )
            n += 1
        for d in ALERT_DAYS:
            key = f"review_{d}"
            if left <= d and key not in (t.alerts_sent or []):
                t.alerts_sent = [*(t.alerts_sent or []), key]
                ids = common.officers(db, t.project_id)
                if ids:
                    notify.notify(
                        db,
                        ids,
                        NotificationKind.jsa_template_review_due,
                        f"{t.jsa_no} review due {t.review_due_on.isoformat()}",
                        f"مراجعة {t.jsa_no} مستحقة في {t.review_due_on.isoformat()}",
                        None,
                        None,
                        EntityType.jsa,
                        t.id,
                        t.project_id,
                    )
    db.flush()
    return n
