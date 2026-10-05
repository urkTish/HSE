"""Contractors (master records) and project engagements (spec §3.4, §3.5, §4.2, §5.4)."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    Language,
    NotificationKind,
    Role,
    UserStatus,
)
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.text import like_pattern, normalize, search_blob
from app.models import Contractor, Project, ProjectEngagement, RoleAssignment, Site, User
from app.schemas.contractors import (
    ContractorCreate,
    ContractorRead,
    ContractorSummary,
    ContractorTransitionRequest,
    ContractorUpdate,
    EngagementCreate,
    EngagementRead,
    EngagementUpdate,
)
from app.services import audit, notify, projects
from app.services.common import (
    condition_not_met,
    duplicate,
    ensure_open,
    invalid_transition,
    require_reason,
)
from app.services.permissions import Principal, deny, engagement_descendants, forbidden_error
from app.services.users import deactivate, end_assignment

FIELDS = (
    "legal_name_en",
    "legal_name_ar",
    "short_code",
    "cr_number",
    "cr_expiry_date",
    "vat_number",
    "contractor_category",
    "primary_contact_name",
    "primary_contact_mobile",
    "primary_contact_email",
)
CONTACT_FIELDS = ("primary_contact_name", "primary_contact_mobile", "primary_contact_email")
ENG_FIELDS = (
    "scope_of_work_en",
    "scope_of_work_ar",
    "site_ids",
    "mobilisation_date",
    "demobilisation_date",
)


# ---- visibility ------------------------------------------------------------------------
def _sees_all_contractors(p: Principal) -> bool:
    # HSE Officers onboard contractors (capability 5), so they see the whole register.
    return p.is_manager or p.has_role_anywhere(Role.hse_officer)


def _engagement_condition(p: Principal, cap: Capability) -> Any:
    grants = p.project_grants(cap)
    if grants is None:
        return true()
    conds: list[Any] = []
    for pid, g in grants.items():
        if g.engagement_ids is None:
            conds.append(ProjectEngagement.project_id == pid)
        elif g.engagement_ids:
            conds.append(ProjectEngagement.id.in_(g.engagement_ids))
    return or_(*conds) if conds else false()


def _visible_condition(p: Principal) -> Any:
    if _sees_all_contractors(p):
        return true()
    return Contractor.id.in_(
        select(ProjectEngagement.contractor_id).where(
            _engagement_condition(p, Capability.contractor_view)
        )
    )


def contact_visible_ids(db: Session, p: Principal, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if _sees_all_contractors(p):
        return set(ids)
    if not p.has_any(Capability.contractor_view_contacts):
        return set()
    return set(
        db.scalars(
            select(ProjectEngagement.contractor_id).where(
                ProjectEngagement.contractor_id.in_(ids),
                _engagement_condition(p, Capability.contractor_view_contacts),
            )
        ).all()
    )


def contractor_read(c: Contractor, contacts: bool) -> ContractorRead:
    data: dict[str, Any] = {
        "id": c.id,
        "status": c.status,
        "status_reason": c.status_reason,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        **{f: getattr(c, f) for f in FIELDS if f not in CONTACT_FIELDS},
    }
    if contacts:
        data.update({f: getattr(c, f) for f in CONTACT_FIELDS})
    return ContractorRead(**data)


def get_visible(db: Session, p: Principal, contractor_id: uuid.UUID) -> Contractor:
    c = db.scalar(select(Contractor).where(Contractor.id == contractor_id, _visible_condition(p)))
    if c is None:
        raise deny(db, p, EntityType.contractor, contractor_id, what="Contractor")
    return c


def list_query(
    db: Session,
    p: Principal,
    statuses: list[ContractorStatus] | None = None,
    category: Any = None,
    project_id: uuid.UUID | None = None,
    cr_expiring_within_days: int | None = None,
    q: str | None = None,
    sort: str = "short_code",
    lang: Language = Language.en,
) -> Select[Contractor]:
    if not p.has_any(Capability.contractor_view) and not _sees_all_contractors(p):
        raise forbidden_error()
    stmt = select(Contractor).where(_visible_condition(p))
    if statuses:
        stmt = stmt.where(Contractor.status.in_(statuses))
    if category:
        stmt = stmt.where(Contractor.contractor_category == category)
    if project_id:
        projects.get_visible(db, p, project_id)
        stmt = stmt.where(
            Contractor.id.in_(
                select(ProjectEngagement.contractor_id).where(
                    ProjectEngagement.project_id == project_id
                )
            )
        )
    if cr_expiring_within_days is not None:
        stmt = stmt.where(
            Contractor.cr_expiry_date <= p.today + timedelta(days=cr_expiring_within_days)
        )
    if q:
        stmt = stmt.where(Contractor.search_text.like(like_pattern(q)))
    key = sort.lstrip("-")
    col: Any = {
        "short_code": Contractor.short_code,
        "cr_expiry_date": Contractor.cr_expiry_date,
        "name": Contractor.legal_name_ar.collate("ar-x-icu")
        if lang == Language.ar
        else Contractor.legal_name_en.collate("en-x-icu"),
    }[key]
    return stmt.order_by(
        col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last(), Contractor.id
    )


# ---- create / update -------------------------------------------------------------------
def _search(c: Contractor) -> str:
    return search_blob(c.short_code, c.cr_number, c.legal_name_en, c.legal_name_ar)


def _check_unique(db: Session, c: Contractor) -> None:
    checks = [
        ("short_code", Contractor.short_code == c.short_code, "Short code already in use."),
        ("cr_number", Contractor.cr_number == c.cr_number, "CR number already registered."),
        (
            "legal_name_en",
            Contractor.legal_name_en_norm == c.legal_name_en_norm,
            "A contractor with this English name exists.",
        ),
        (
            "legal_name_ar",
            Contractor.legal_name_ar_norm == c.legal_name_ar_norm,
            "A contractor with this Arabic name exists.",
        ),
    ]
    for fld, cond, msg in checks:
        if db.scalar(select(Contractor.id).where(cond, Contractor.id != c.id)):
            raise duplicate(fld, msg)


def _normalise(c: Contractor) -> None:
    c.legal_name_en_norm = normalize(c.legal_name_en)
    c.legal_name_ar_norm = normalize(c.legal_name_ar)
    c.primary_contact_email = c.primary_contact_email.lower()
    c.search_text = _search(c)


def _dict(c: Contractor) -> dict[str, Any]:
    return {f: getattr(c, f) for f in FIELDS}


def _require_onboarder(p: Principal) -> None:
    p.ensure_writer()
    if not _sees_all_contractors(p):
        raise forbidden_error()


def create(db: Session, p: Principal, body: ContractorCreate) -> Contractor:
    _require_onboarder(p)
    c = Contractor(
        id=uuid.uuid4(),
        status=ContractorStatus.draft,
        created_by_user_id=p.user.id,
        cr_alerts={},
        **body.model_dump(),
    )
    _normalise(c)
    _check_unique(db, c)
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(),
        entity_type=EntityType.contractor,
        entity_id=c.id,
        after={**_dict(c), "status": c.status},
    )
    return c


def update(
    db: Session, p: Principal, contractor_id: uuid.UUID, body: ContractorUpdate
) -> Contractor:
    c = get_visible(db, p, contractor_id)
    _require_onboarder(p)
    if not p.is_manager and c.status not in (
        ContractorStatus.draft,
        ContractorStatus.pending_approval,
    ):
        raise forbidden_error("Only the HSE Manager can edit an approved contractor.")
    before = _dict(c)
    for k, v in body.changes().items():
        setattr(c, k, v)
    _normalise(c)
    _check_unique(db, c)
    if "cr_expiry_date" in body.model_fields_set:
        c.cr_alerts = {}
    b, a = audit.diff(before, _dict(c))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(),
            entity_type=EntityType.contractor,
            entity_id=c.id,
            before=b,
            after=a,
        )
    return c


# ---- transitions -----------------------------------------------------------------------
CS = ContractorStatus
# (from, to) -> (manager only, reason required)   — spec §4.2
CONTRACTOR_TRANSITIONS: dict[tuple[ContractorStatus, ContractorStatus], tuple[bool, bool]] = {
    (CS.draft, CS.pending_approval): (False, False),
    (CS.pending_approval, CS.approved): (True, False),
    (CS.pending_approval, CS.draft): (True, True),
    (CS.approved, CS.suspended): (True, True),
    (CS.suspended, CS.approved): (True, True),
    (CS.approved, CS.demobilised): (True, False),
    (CS.suspended, CS.demobilised): (True, False),
    (CS.blacklisted, CS.suspended): (True, True),
    **{(s, CS.blacklisted): (True, True) for s in CS if s != CS.blacklisted},
}


def _stakeholders(db: Session, c: Contractor) -> tuple[list[uuid.UUID], list[Project]]:
    """Officers of engaged projects + contractor reps of this contractor and its parent."""
    engs = db.scalars(
        select(ProjectEngagement).where(ProjectEngagement.contractor_id == c.id)
    ).all()
    project_ids = {e.project_id for e in engs}
    recipients = set(notify.users_with_role(db, Role.hse_officer, project_ids))
    eng_ids = {e.id for e in engs} | {
        e.parent_engagement_id for e in engs if e.parent_engagement_id
    }
    if eng_ids:
        reps = db.scalars(
            select(RoleAssignment.user_id).where(
                RoleAssignment.role == Role.contractor_hse_rep,
                RoleAssignment.contractor_engagement_id.in_(eng_ids),
                RoleAssignment.revoked_at.is_(None),
            )
        ).all()
        recipients |= set(reps)
    projs = list(db.scalars(select(Project).where(Project.id.in_(project_ids))).all())
    return list(recipients), projs


def _blacklist_effects(db: Session, p: Principal, c: Contractor, reason: str) -> None:
    """Rule 27 (a) deactivate users, (b) end-date role assignments, (c) flag descendants."""
    users = db.scalars(select(User).where(User.employer_contractor_id == c.id)).all()
    for u in users:
        for a in u.assignments:
            if a.revoked_at is None and (a.valid_to is None or a.valid_to >= p.today):
                end_assignment(db, a, p.today, p.user.id)
                audit.record(
                    db,
                    AuditAction.role_revoked,
                    p.actor(a.project_id),
                    entity_type=EntityType.role_assignment,
                    entity_id=a.id,
                    project_id=a.project_id,
                    after={"valid_to": a.valid_to},
                    details={"reason": "contractor blacklisted"},
                )
        if u.status != UserStatus.deactivated:
            deactivate(db, u, f"Contractor {c.short_code} blacklisted: {reason}", p.actor())
    engs = db.scalars(
        select(ProjectEngagement).where(ProjectEngagement.contractor_id == c.id)
    ).all()
    flagged: set[uuid.UUID] = set()
    for e in engs:
        flagged |= engagement_descendants(db, e.id) - {e.id}
    for eid in flagged:
        d = db.get(ProjectEngagement, eid)
        if d and not d.parent_blacklisted:
            d.parent_blacklisted = True
            audit.record(
                db,
                AuditAction.update,
                p.actor(d.project_id),
                entity_type=EntityType.project_engagement,
                entity_id=d.id,
                project_id=d.project_id,
                before={"parent_blacklisted": False},
                after={"parent_blacklisted": True},
            )
            notify.notify(
                db,
                notify.managers(db),
                NotificationKind.engagement_parent_blacklisted,
                f"Review {d.contractor.short_code}: parent contractor blacklisted",
                f"مراجعة {d.contractor.short_code}: تم حظر المقاول الأعلى",
                entity_type=EntityType.project_engagement,
                entity_id=d.id,
                project_id=d.project_id,
            )


def transition(
    db: Session, p: Principal, contractor_id: uuid.UUID, body: ContractorTransitionRequest
) -> Contractor:
    c = get_visible(db, p, contractor_id)
    _require_onboarder(p)
    key = (c.status, body.to_status)
    rule = CONTRACTOR_TRANSITIONS.get(key)
    if rule is None:
        raise invalid_transition("Contractor", *key)
    manager_only, reason_required = rule
    if manager_only and not p.is_manager:
        raise forbidden_error("Only the HSE Manager can make this change.")
    reason = body.reason
    if reason_required:
        reason = require_reason(reason, f"move the contractor to {body.to_status.value}")
    if body.to_status == CS.demobilised:
        open_engs = db.scalars(
            select(ProjectEngagement).where(
                ProjectEngagement.contractor_id == c.id,
                or_(
                    ProjectEngagement.demobilisation_date.is_(None),
                    ProjectEngagement.demobilisation_date > p.today,
                ),
            )
        ).all()
        if open_engs:
            raise condition_not_met(
                "All engagements must have a demobilisation date on or before today.",
                "يجب أن يكون لكل ارتباطات المقاول تاريخ تسريح اليوم أو قبله.",
            )
    c.status = body.to_status
    c.status_reason = reason
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(),
        entity_type=EntityType.contractor,
        entity_id=c.id,
        before={"status": key[0]},
        after={"status": key[1]},
        details={"reason": reason},
    )
    if body.to_status == CS.pending_approval:
        notify.notify(
            db,
            notify.managers(db),
            NotificationKind.contractor_submitted,
            f"{c.short_code} submitted for approval",
            f"تم تقديم {c.short_code} للاعتماد",
            entity_type=EntityType.contractor,
            entity_id=c.id,
        )
    if body.to_status == CS.blacklisted:
        _blacklist_effects(db, p, c, reason or "")
    if body.to_status in (CS.suspended, CS.blacklisted) or key == (CS.suspended, CS.approved):
        recipients, _ = _stakeholders(db, c)
        notify.notify(
            db,
            recipients,
            NotificationKind.contractor_status_changed,
            f"{c.short_code} is now {body.to_status.value}",
            f"تغيرت حالة {c.short_code}",
            body_en=reason,
            entity_type=EntityType.contractor,
            entity_id=c.id,
        )
    return c


# ---- engagements -----------------------------------------------------------------------
def engagement_read(e: ProjectEngagement) -> EngagementRead:
    return EngagementRead(
        id=e.id,
        project_id=e.project_id,
        contractor_id=e.contractor_id,
        contractor=ContractorSummary.model_validate(e.contractor),
        tier=e.tier,
        parent_engagement_id=e.parent_engagement_id,
        root_engagement_id=e.root_engagement_id or e.id,
        scope_of_work_en=e.scope_of_work_en,
        scope_of_work_ar=e.scope_of_work_ar,
        site_ids=list(e.site_ids or []),
        mobilisation_date=e.mobilisation_date,
        demobilisation_date=e.demobilisation_date,
        parent_blacklisted=e.parent_blacklisted,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


def list_engagements_query(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    tier: int | None = None,
    contractor_id: uuid.UUID | None = None,
    parent_engagement_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    parent_blacklisted: bool | None = None,
) -> Select[ProjectEngagement]:
    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, Capability.contractor_view)
    if g is None:
        raise forbidden_error()
    stmt = (
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id == project_id)
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(ProjectEngagement.id.in_(g.engagement_ids or [uuid.UUID(int=0)]))
    if tier:
        stmt = stmt.where(ProjectEngagement.tier == tier)
    if contractor_id:
        stmt = stmt.where(ProjectEngagement.contractor_id == contractor_id)
    if parent_engagement_id:
        stmt = stmt.where(ProjectEngagement.parent_engagement_id == parent_engagement_id)
    if site_id:
        stmt = stmt.where(ProjectEngagement.site_ids.contains([site_id]))
    if parent_blacklisted is not None:
        stmt = stmt.where(ProjectEngagement.parent_blacklisted == parent_blacklisted)
    return stmt.order_by(ProjectEngagement.tier, Contractor.short_code)


def get_engagement(db: Session, p: Principal, engagement_id: uuid.UUID) -> ProjectEngagement:
    e = db.get(ProjectEngagement, engagement_id)
    if e is None or not p.can_see_project(e.project_id):
        raise deny(db, p, EntityType.project_engagement, engagement_id, e.project_id if e else None)
    g = p.grant(e.project_id, Capability.contractor_view)
    if g is None or not g.covers_engagement(e.id):
        raise deny(db, p, EntityType.project_engagement, engagement_id, e.project_id)
    return e


def _check_sites(db: Session, project_id: uuid.UUID, site_ids: list[uuid.UUID]) -> None:
    found = set(
        db.scalars(
            select(Site.id).where(Site.id.in_(site_ids), Site.project_id == project_id)
        ).all()
    )
    if found != set(site_ids):
        raise validation_error("site_ids", "All sites must belong to the project.")


def _eng_dict(e: ProjectEngagement) -> dict[str, Any]:
    d = {f: getattr(e, f) for f in ENG_FIELDS}
    d["site_ids"] = sorted(str(s) for s in e.site_ids or [])
    return d


def create_engagement(
    db: Session, p: Principal, project_id: uuid.UUID, body: EngagementCreate
) -> ProjectEngagement:
    project = projects.get_visible(db, p, project_id)
    p.require(project_id, Capability.engagement_manage)
    ensure_open(project)
    c = db.get(Contractor, body.contractor_id)
    if c is None:
        raise validation_error("contractor_id", "Contractor not found.")
    if c.status != ContractorStatus.approved:
        raise ApiError(
            409,
            ErrorCode.CONTRACTOR_NOT_APPROVED,
            f"{c.short_code} is not approved (status {c.status.value}).",
            "المقاول غير معتمد.",
        )
    if db.scalar(
        select(ProjectEngagement.id).where(
            ProjectEngagement.project_id == project_id,
            ProjectEngagement.contractor_id == c.id,
        )
    ):
        raise duplicate("contractor_id", "The contractor is already engaged on this project.")
    root: uuid.UUID | None = None
    if body.parent_engagement_id:
        parent = db.get(ProjectEngagement, body.parent_engagement_id)
        if parent is None or parent.project_id != project_id:
            raise validation_error(
                "parent_engagement_id", "The parent must be an engagement on the same project."
            )
        if parent.tier != body.tier - 1:
            raise validation_error(
                "parent_engagement_id",
                f"A tier-{body.tier} engagement needs a tier-{body.tier - 1} parent (rule 25).",
            )
        root = parent.root_engagement_id or parent.id
    _check_sites(db, project_id, body.site_ids)
    e = ProjectEngagement(
        id=uuid.uuid4(),
        project_id=project_id,
        contractor_id=c.id,
        tier=body.tier,
        parent_engagement_id=body.parent_engagement_id,
        scope_of_work_en=body.scope_of_work_en,
        scope_of_work_ar=body.scope_of_work_ar,
        site_ids=list(body.site_ids),
        mobilisation_date=body.mobilisation_date,
        demobilisation_date=body.demobilisation_date,
        parent_blacklisted=False,
    )
    e.root_engagement_id = root or e.id
    db.add(e)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.project_engagement,
        entity_id=e.id,
        project_id=project_id,
        after={
            **_eng_dict(e),
            "contractor_id": c.id,
            "tier": e.tier,
            "parent_engagement_id": e.parent_engagement_id,
        },
    )
    db.refresh(e)
    return e


def update_engagement(
    db: Session, p: Principal, engagement_id: uuid.UUID, body: EngagementUpdate
) -> ProjectEngagement:
    e = get_engagement(db, p, engagement_id)
    p.require(e.project_id, Capability.engagement_manage)
    project = db.get(Project, e.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    changes = body.changes()
    if "site_ids" in changes:
        _check_sites(db, e.project_id, changes["site_ids"])
    mob = changes.get("mobilisation_date", e.mobilisation_date)
    demob = changes.get("demobilisation_date", e.demobilisation_date)
    if demob and demob < mob:
        raise validation_error("demobilisation_date", "Must be on or after mobilisation_date.")
    before = _eng_dict(e)
    for k, v in changes.items():
        setattr(e, k, list(v) if k == "site_ids" else v)
    b, a = audit.diff(before, _eng_dict(e))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(e.project_id),
            entity_type=EntityType.project_engagement,
            entity_id=e.id,
            project_id=e.project_id,
            before=b,
            after=a,
        )
    return e


def clear_parent_blacklisted(
    db: Session, p: Principal, engagement_id: uuid.UUID
) -> ProjectEngagement:
    e = get_engagement(db, p, engagement_id)
    p.require(None, Capability.contractor_approve)
    if not e.parent_blacklisted:
        raise invalid_transition("Engagement flag", "clear", "clear")
    e.parent_blacklisted = False
    audit.record(
        db,
        AuditAction.update,
        p.actor(e.project_id),
        entity_type=EntityType.project_engagement,
        entity_id=e.id,
        project_id=e.project_id,
        before={"parent_blacklisted": True},
        after={"parent_blacklisted": False},
        details={"reviewed": True},
    )
    return e
