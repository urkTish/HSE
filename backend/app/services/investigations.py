"""Investigations (spec 1-dashboard §3.5, rules I-13…I-16)."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import (
    CaSourceType,
    IcamLevel,
    IncidentStatus,
    InvestigationLevel,
    InvestigationMethod,
    RootCauseCode,
)
from app.models import CorrectiveAction, Investigation, ProjectEngagement, User
from app.schemas.hse_common import UserRef
from app.schemas.incidents import (
    InvestigationAssignment,
    InvestigationExtensionRead,
    InvestigationExtensionRequest,
    InvestigationRead,
    InvestigationUpdate,
    RootCauseRead,
)
from app.services import audit
from app.services.common import ensure_open, invalid_transition
from app.services.hse_common import Refs, covers, project_today, user_roles
from app.services.incidents import (
    DUE_DAYS,
    LEVEL_RANK,
    Bundle,
    bundle,
    get_incident,
    investigation_overdue,
    minimum_level,
)
from app.services.permissions import Principal, engagement_descendants, forbidden_error

UNKNOWN = UserRef(id=uuid.UUID(int=0), full_name_en="—")
L3_LEADS = {Role.hse_manager, Role.hse_officer}
L12_LEADS = {Role.hse_manager, Role.hse_officer, Role.site_engineer, Role.contractor_hse_rep}


def _too_low(minimum: InvestigationLevel) -> ApiError:
    return ApiError(
        422,
        ErrorCode.INVESTIGATION_LEVEL_TOO_LOW,
        f"The minimum investigation level for this incident is {minimum.value} (I-14).",
        f"الحد الأدنى لمستوى التحقيق لهذه الحادثة هو {minimum.value}.",
    )


def _check_lead(db: Session, b: Bundle, level: InvestigationLevel, lead_id: uuid.UUID) -> None:
    lead = db.get(User, lead_id)
    roles = user_roles(db, lead_id, b.project.id) if lead else set()
    allowed = L3_LEADS if level == InvestigationLevel.L3 else L12_LEADS
    if lead is None or not roles & allowed:
        raise ApiError(
            422,
            ErrorCode.INVESTIGATION_LEAD_NOT_ALLOWED,
            "L3 leads must be an HSE Officer or the HSE Manager; L1/L2 leads an HSE Officer, "
            "Site Engineer or Contractor HSE Rep on this project (I-15).",
            "قائد التحقيق غير مسموح لهذا المستوى.",
        )


def _contractor_member(db: Session, b: Bundle, member_ids: list[uuid.UUID]) -> bool:
    eng_id = b.inc.responsible_engagement_id
    if eng_id is None:
        return False
    contractors = set()
    for e in engagement_descendants(db, eng_id):
        eng = db.get(ProjectEngagement, e)
        if eng is not None:
            contractors.add(eng.contractor_id)
    for uid in member_ids:
        u = db.get(User, uid)
        if u is not None and u.employer_contractor_id in contractors:
            return True
    return False


def _team_issue(db: Session, b: Bundle, level: InvestigationLevel, team: list[uuid.UUID]) -> bool:
    return level == InvestigationLevel.L3 and (
        len(set(team)) < 2 or not _contractor_member(db, b, team)
    )


def _team_error() -> ApiError:
    return ApiError(
        422,
        ErrorCode.INVESTIGATION_TEAM_INCOMPLETE,
        "An L3 team needs at least 2 members including 1 from the responsible contractor (I-15).",
        "فريق التحقيق الشامل يحتاج عضوين على الأقل أحدهما من المقاول المسؤول.",
    )


def _check_members(db: Session, team: list[uuid.UUID]) -> None:
    for uid in team:
        if db.get(User, uid) is None:
            raise validation_error("team_member_ids", "Unknown team member.")


def assign(db: Session, b: Bundle, a: InvestigationAssignment) -> Investigation:
    """Reported → Under Investigation: level ≥ minimum, lead and team rules, due date."""
    minimum = minimum_level(b.inc, b.cases)
    if LEVEL_RANK[a.level] < LEVEL_RANK[minimum]:
        raise _too_low(minimum)
    _check_lead(db, b, a.level, a.lead_investigator_id)
    _check_members(db, a.team_member_ids)
    if _team_issue(db, b, a.level, a.team_member_ids):
        raise _team_error()
    inv = b.inv or Investigation(
        incident_id=b.inc.id, extensions=[], root_causes=[], alerts_sent=[]
    )
    inv.level = a.level
    inv.lead_investigator_id = a.lead_investigator_id
    inv.team_member_ids = list(dict.fromkeys(a.team_member_ids))
    inv.method = a.method or (
        InvestigationMethod.icam
        if a.level == InvestigationLevel.L3
        else InvestigationMethod.simple
        if a.level == InvestigationLevel.L1
        else InvestigationMethod.five_why
    )
    if not inv.extensions:
        inv.due_date = b.inc.occurred_date + timedelta(days=DUE_DAYS[a.level])
    inv.updated_at = now()
    if b.inv is None:
        db.add(inv)
        b.inv = inv
    db.flush()
    return inv


def missing_for_submit(db: Session, b: Bundle) -> list[str]:
    inv = b.inv
    if inv is None:
        return ["investigation"]
    out = []
    minimum = minimum_level(b.inc, b.cases)
    if LEVEL_RANK[inv.level] < LEVEL_RANK[minimum]:
        out.append("level")
    for f in ("method", "sequence_of_events", "immediate_causes"):
        if not getattr(inv, f):
            out.append(f)
    if inv.level != InvestigationLevel.L1 and not inv.root_causes:
        out.append("root_causes")
    for i, rc in enumerate(inv.root_causes or []):
        if not rc.get("linked_ca_ids") and not (rc.get("no_action_justification") or "").strip():
            out.append(f"root_causes[{i}].linked_ca_ids")
    if inv.level == InvestigationLevel.L3:
        if not inv.lessons_learned:
            out.append("lessons_learned")
        if not inv.preliminary_report_at:
            out.append("preliminary_report")
        if _team_issue(db, b, inv.level, list(inv.team_member_ids or [])):
            out.append("team_member_ids")
    return out


def submit(db: Session, b: Bundle) -> None:
    missing = missing_for_submit(db, b)
    if missing:
        raise ApiError(
            409,
            ErrorCode.INVESTIGATION_INCOMPLETE,
            "The investigation is incomplete: " + ", ".join(missing) + ".",
            "التحقيق غير مكتمل.",
        )
    assert b.inv is not None  # noqa: S101
    b.inv.submitted_at = now()
    b.inv.returned_comment = None


def _icam(code: str) -> IcamLevel:
    return IcamLevel(code.split("-", maxsplit=1)[0])


def to_read(db: Session, b: Bundle) -> InvestigationRead:
    inv = b.inv
    assert inv is not None  # noqa: S101
    ext_users = [e.get("approved_by") for e in inv.extensions or []]
    refs = Refs(db).load(
        users=[
            inv.lead_investigator_id,
            inv.approved_by_user_id,
            *inv.team_member_ids,
            *[uuid.UUID(u) for u in ext_users if u],
        ]
    )
    day = project_today(b.project)
    prelim_due = (
        b.inc.occurred_at + timedelta(hours=48) if inv.level == InvestigationLevel.L3 else None
    )
    return InvestigationRead(
        incident_id=b.inc.id,
        level=inv.level,
        minimum_level=minimum_level(b.inc, b.cases),
        lead_investigator=refs.user(inv.lead_investigator_id),
        team_members=[u for u in (refs.user(x) for x in inv.team_member_ids) if u],
        method=inv.method,
        due_date=inv.due_date,
        overdue=investigation_overdue(b.inc, inv, day),
        extensions=[
            InvestigationExtensionRead(
                new_due_date=e["new_due_date"],
                previous_due_date=e["previous_due_date"],
                reason=e["reason"],
                approved_by=refs.user(uuid.UUID(e["approved_by"])) or UNKNOWN,
                approved_at=datetime.fromisoformat(e["approved_at"]),
            )
            for e in inv.extensions or []
        ],
        preliminary_report=inv.preliminary_report,
        preliminary_report_at=inv.preliminary_report_at,
        preliminary_report_due_at=prelim_due,
        sequence_of_events=inv.sequence_of_events,
        immediate_causes=inv.immediate_causes,
        root_causes=[
            RootCauseRead(
                code=RootCauseCode(rc["code"]),
                icam_level=_icam(rc["code"]),
                text=rc["text"],
                linked_ca_ids=[uuid.UUID(x) for x in rc.get("linked_ca_ids", [])],
                no_action_justification=rc.get("no_action_justification"),
            )
            for rc in inv.root_causes or []
        ],
        lessons_learned=inv.lessons_learned,
        ptw_involved=inv.ptw_involved,
        ptw_ref=inv.ptw_ref,
        submitted_at=inv.submitted_at,
        returned_comment=inv.returned_comment,
        approved_by=refs.user(inv.approved_by_user_id),
        approved_at=inv.approved_at,
        higher_control_justification=b.inc.higher_control_justification,
        missing_for_submit=missing_for_submit(db, b),
    )


def _load(db: Session, p: Principal, incident_id: uuid.UUID) -> Bundle:
    b = bundle(db, get_incident(db, p, incident_id))
    if b.inv is None:
        raise not_found("Investigation")
    return b


def get(db: Session, p: Principal, incident_id: uuid.UUID) -> InvestigationRead:
    return to_read(db, _load(db, p, incident_id))


def _snapshot(inv: Investigation) -> dict[str, Any]:
    keys = (
        "level",
        "lead_investigator_id",
        "team_member_ids",
        "method",
        "due_date",
        "sequence_of_events",
        "immediate_causes",
        "root_causes",
        "lessons_learned",
        "ptw_involved",
        "ptw_ref",
        "preliminary_report",
    )
    return {k: getattr(inv, k) for k in keys}


def update(
    db: Session, p: Principal, incident_id: uuid.UUID, body: InvestigationUpdate
) -> InvestigationRead:
    b = _load(db, p, incident_id)
    inv = b.inv
    assert inv is not None  # noqa: S101
    ensure_open(b.project)
    p.ensure_writer()
    if b.inc.status != IncidentStatus.under_investigation:
        raise invalid_transition("Investigation", b.inc.status, "edited")
    classify = covers(p.grant(b.inc.project_id, Capability.incident_classify), b.inc.site_id, None)
    member = p.user.id == inv.lead_investigator_id or p.user.id in (inv.team_member_ids or [])
    if not classify and not (
        member and p.grant(b.inc.project_id, Capability.investigation_edit) is not None
    ):
        raise forbidden_error("Only the lead, the team or HSE staff may edit the investigation.")
    ch = body.changes()
    if {"level", "lead_investigator_id", "team_member_ids"} & set(ch) and not classify:
        raise forbidden_error("Only HSE staff may change the level, lead or team.")
    before = _snapshot(inv)
    level = ch.get("level") or inv.level
    minimum = minimum_level(b.inc, b.cases)
    if LEVEL_RANK[level] < LEVEL_RANK[minimum]:
        raise _too_low(minimum)
    if "lead_investigator_id" in ch or "level" in ch:
        lead = ch.get("lead_investigator_id") or inv.lead_investigator_id
        if lead is None:
            raise validation_error("lead_investigator_id", "A lead investigator is required.")
        _check_lead(db, b, level, lead)
        inv.lead_investigator_id = lead
    if "team_member_ids" in ch:
        _check_members(db, ch["team_member_ids"] or [])
        inv.team_member_ids = list(dict.fromkeys(ch["team_member_ids"] or []))
    if "level" in ch and ch["level"] != inv.level:
        inv.level = level
        if not inv.extensions:
            inv.due_date = b.inc.occurred_date + timedelta(days=DUE_DAYS[level])
    for k in (
        "method",
        "sequence_of_events",
        "immediate_causes",
        "lessons_learned",
        "ptw_involved",
        "ptw_ref",
    ):
        if k in ch:
            setattr(inv, k, ch[k])
    if "preliminary_report" in ch:
        inv.preliminary_report = ch["preliminary_report"]
        if ch["preliminary_report"] and inv.preliminary_report_at is None:
            inv.preliminary_report_at = now()
    if "root_causes" in ch:
        valid = {
            ca.id
            for ca in db.scalars(
                select(CorrectiveAction).where(
                    CorrectiveAction.source_type == CaSourceType.incident,
                    CorrectiveAction.source_id == b.inc.id,
                )
            )
        }
        rcs = []
        for i, rc in enumerate(ch["root_causes"] or []):
            for ca_id in rc.get("linked_ca_ids", []):
                if ca_id not in valid:
                    raise validation_error(
                        f"root_causes[{i}].linked_ca_ids",
                        "Linked corrective actions must belong to this incident.",
                    )
            rcs.append(
                {
                    "code": RootCauseCode(rc["code"]).value,
                    "text": rc["text"],
                    "linked_ca_ids": [str(x) for x in rc.get("linked_ca_ids", [])],
                    "no_action_justification": rc.get("no_action_justification"),
                }
            )
        inv.root_causes = rcs
    inv.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snapshot(inv))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(b.inc.project_id),
            entity_type=EntityType.investigation,
            entity_id=b.inc.id,
            project_id=b.inc.project_id,
            before=bf,
            after=af,
        )
    return to_read(db, b)


def extend(
    db: Session, p: Principal, incident_id: uuid.UUID, body: InvestigationExtensionRequest
) -> InvestigationRead:
    b = _load(db, p, incident_id)
    inv = b.inv
    assert inv is not None  # noqa: S101
    ensure_open(b.project)
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error("Only the HSE Manager can extend an investigation.")
    if b.inc.status not in (IncidentStatus.under_investigation, IncidentStatus.reported):
        raise invalid_transition("Investigation", b.inc.status, "extended")
    if inv.due_date is not None and body.new_due_date <= inv.due_date:
        raise validation_error("new_due_date", "The new due date must be after the current one.")
    prev = inv.due_date or body.new_due_date
    inv.extensions = [
        *(inv.extensions or []),
        {
            "new_due_date": body.new_due_date.isoformat(),
            "previous_due_date": prev.isoformat(),
            "reason": body.reason,
            "approved_by": str(p.user.id),
            "approved_at": now().isoformat(),
        },
    ]
    inv.due_date = body.new_due_date
    inv.alerts_sent = []
    inv.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(b.inc.project_id),
        entity_type=EntityType.investigation,
        entity_id=b.inc.id,
        project_id=b.inc.project_id,
        before={"due_date": prev},
        after={"due_date": body.new_due_date},
        details={"extension_reason": body.reason},
    )
    return to_read(db, b)
