"""Server-side permission matrix and project/site/contractor scoping (spec §5.2, §5.10).

A ``Principal`` is built once per request from the user's *active* role assignments (today in
Asia/Riyadh). Permissions are the union of assignments within the project being accessed.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import (
    AuditAction,
    AuditResult,
    Capability,
    CapabilityScope,
    ContractorStatus,
    EntityType,
    Role,
)
from app.core.errors import ApiError, ErrorCode, not_found
from app.models import Contractor, Project, ProjectEngagement, RoleAssignment, User, UserSession
from app.services import audit
from app.services.audit import AuditActor

C = Capability
S = CapabilityScope

# Spec §5.10, one dict per role. Missing capability = "—".
MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_manager: {cap: S.all for cap in Capability},
    Role.hse_officer: {
        C.project_view: S.project,
        C.site_zone_manage: S.project,
        C.site_zone_view: S.project,
        C.contractor_create: S.project,
        C.engagement_manage: S.project,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_invite: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.audit_log_read: S.project,
        C.history_view: S.project,
        C.export_lists: S.project,
        C.profile_edit_own: S.all,
    },
    Role.site_engineer: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.history_view: S.sites,
        C.export_lists: S.sites,
        C.profile_edit_own: S.all,
    },
    Role.permit_issuer: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.history_view: S.sites,
        C.profile_edit_own: S.all,
    },
    Role.permit_receiver: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.own_engagement,
        C.contractor_view_contacts: S.own_engagement,
        C.user_view_directory: S.own_engagement,
        C.user_view_contacts: S.own_engagement,
        C.settings_view: S.project,
        C.history_view: S.own_engagement,
        C.profile_edit_own: S.all,
    },
    Role.contractor_hse_rep: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.contractor_tree,
        C.contractor_view_contacts: S.contractor_tree,
        C.user_view_directory: S.contractor_tree,
        C.user_view_contacts: S.contractor_tree,
        C.settings_view: S.project,
        C.history_view: S.contractor_tree,
        C.export_lists: S.contractor_tree,
        C.profile_edit_own: S.all,
    },
    Role.viewer_client: {
        C.project_view: S.project,
        C.site_zone_view: S.project,
        C.contractor_view: S.project,
        C.settings_view: S.project,
        C.history_view: S.project,
        C.export_lists: S.project,
        C.profile_edit_own: S.all,
    },
}

SCOPE_RANK = {S.own_engagement: 1, S.contractor_tree: 2, S.sites: 3, S.project: 4, S.all: 5}
ROLE_RANK = {r: i for i, r in enumerate(Role)}  # lower index = more senior
OFFICER_ASSIGNABLE = frozenset(
    {
        Role.site_engineer,
        Role.permit_issuer,
        Role.permit_receiver,
        Role.contractor_hse_rep,
        Role.viewer_client,
    }
)
CONTRACTOR_ROLES = frozenset({Role.contractor_hse_rep, Role.permit_receiver})


@dataclass(frozen=True)
class Grant:
    scope: CapabilityScope
    site_ids: frozenset[uuid.UUID] | None = None  # None = all sites
    engagement_ids: frozenset[uuid.UUID] | None = None  # None = all engagements

    def covers_site(self, site_id: uuid.UUID | None) -> bool:
        return self.site_ids is None or (site_id is not None and site_id in self.site_ids)

    def covers_engagement(self, engagement_id: uuid.UUID | None) -> bool:
        return self.engagement_ids is None or (
            engagement_id is not None and engagement_id in self.engagement_ids
        )


FULL = Grant(S.all)


def _merge(a: Grant | None, b: Grant) -> Grant:
    if a is None:
        return b
    scope = a.scope if SCOPE_RANK[a.scope] >= SCOPE_RANK[b.scope] else b.scope
    sites = None if a.site_ids is None or b.site_ids is None else a.site_ids | b.site_ids
    engs = (
        None
        if a.engagement_ids is None or b.engagement_ids is None
        else a.engagement_ids | b.engagement_ids
    )
    return Grant(scope, sites, engs)


@dataclass
class ProjectScope:
    project_id: uuid.UUID
    project_code: str
    assignments: list[RoleAssignment] = field(default_factory=list)
    grants: dict[Capability, Grant] = field(default_factory=dict)

    @property
    def roles(self) -> set[Role]:
        return {a.role for a in self.assignments}

    @property
    def read_only(self) -> bool:
        return self.roles == {Role.viewer_client}

    @property
    def primary_role(self) -> Role:
        return min(self.roles, key=lambda r: ROLE_RANK[r])


def engagement_descendants(db: Session, engagement_id: uuid.UUID) -> set[uuid.UUID]:
    """Spec K4: the engagement plus every engagement whose parent chain reaches it."""
    eng = db.get(ProjectEngagement, engagement_id)
    if eng is None:
        return set()
    rows = db.execute(
        select(ProjectEngagement.id, ProjectEngagement.parent_engagement_id).where(
            ProjectEngagement.project_id == eng.project_id
        )
    ).all()
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for rid, parent in rows:
        if parent is not None:
            children.setdefault(parent, []).append(rid)
    out = {engagement_id}
    stack = [engagement_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


@dataclass
class Principal:
    user: User
    session: UserSession | None
    today: date
    is_manager: bool
    projects: dict[uuid.UUID, ProjectScope]
    employer_status: ContractorStatus | None
    active_assignments: list[RoleAssignment]

    # ---- capability lookup -------------------------------------------------------------
    def grant(self, project_id: uuid.UUID | None, cap: Capability) -> Grant | None:
        if self.is_manager:
            return FULL
        if project_id is None:
            return None
        scope = self.projects.get(project_id)
        return scope.grants.get(cap) if scope else None

    def project_grants(self, cap: Capability) -> dict[uuid.UUID, Grant] | None:
        """Grants per project for a capability; ``None`` means every project (manager)."""
        if self.is_manager:
            return None
        return {pid: g for pid, s in self.projects.items() if (g := s.grants.get(cap))}

    def has_any(self, cap: Capability) -> bool:
        return self.is_manager or any(cap in s.grants for s in self.projects.values())

    def has_role_anywhere(self, role: Role) -> bool:
        return any(role in s.roles for s in self.projects.values())

    def can_see_project(self, project_id: uuid.UUID) -> bool:
        return self.is_manager or project_id in self.projects

    def actor(self, project_id: uuid.UUID | None = None) -> AuditActor:
        if self.is_manager:
            return AuditActor(self.user.id, Role.hse_manager, project_id)
        scope = self.projects.get(project_id) if project_id else None
        if scope:
            return AuditActor(self.user.id, scope.primary_role, project_id)
        roles = sorted(
            {a.role for a in self.active_assignments}, key=lambda r: ROLE_RANK[r]
        )
        return AuditActor(self.user.id, roles[0] if roles else None, project_id)

    # ---- guards -------------------------------------------------------------------------
    def ensure_writer(self) -> None:
        """Rule 28: users of a suspended contractor keep read access but cannot write."""
        if self.employer_status == ContractorStatus.suspended:
            raise ApiError(
                403,
                ErrorCode.CONTRACTOR_SUSPENDED,
                "Your contractor is suspended: changes are blocked.",
                "المقاول الذي تتبع له موقوف: التعديلات محظورة.",
            )

    def require(self, project_id: uuid.UUID | None, cap: Capability) -> Grant:
        self.ensure_writer()
        g = self.grant(project_id, cap)
        if g is None:
            scope = self.projects.get(project_id) if project_id else None
            if scope and scope.read_only:
                raise ApiError(
                    403,
                    ErrorCode.READ_ONLY_ROLE,
                    "Your role on this project is read-only.",
                    "دورك في هذا المشروع للاطلاع فقط.",
                )
            raise forbidden_error()
        return g

    def require_any(self, cap: Capability) -> None:
        self.ensure_writer()
        if not self.has_any(cap):
            raise forbidden_error()


def forbidden_error() -> ApiError:
    return ApiError(
        403,
        ErrorCode.FORBIDDEN,
        "You do not have permission for this action.",
        "ليس لديك صلاحية لتنفيذ هذا الإجراء.",
    )


def deny(
    db: Session,
    p: Principal,
    entity_type: EntityType,
    entity_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    what: str = "Resource",
) -> ApiError:
    """Rule 12: out-of-scope by ID → 404 plus an ``access_denied`` audit entry."""
    audit.record(
        db,
        AuditAction.access_denied,
        p.actor(project_id),
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        result=AuditResult.denied,
        defer=True,
    )
    return not_found(what)


def active_assignments(db: Session, user_id: uuid.UUID, day: date) -> list[RoleAssignment]:
    rows = db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.valid_from <= day,
        )
    ).all()
    return [a for a in rows if a.is_active_on(day)]


def build_principal(db: Session, user: User, session: UserSession | None) -> Principal:
    day = today()
    assignments = active_assignments(db, user.id, day)
    is_manager = any(a.role == Role.hse_manager for a in assignments)
    project_ids = {a.project_id for a in assignments if a.project_id}
    codes = dict(
        db.execute(select(Project.id, Project.code).where(Project.id.in_(project_ids))).all()
    )
    projects: dict[uuid.UUID, ProjectScope] = {}
    tree_cache: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for a in assignments:
        if a.project_id is None:
            continue
        scope = projects.setdefault(a.project_id, ProjectScope(a.project_id, codes[a.project_id]))
        scope.assignments.append(a)
        for cap, cap_scope in MATRIX[a.role].items():
            engs: frozenset[uuid.UUID] | None = None
            if cap_scope == S.contractor_tree and a.contractor_engagement_id:
                eid = a.contractor_engagement_id
                if eid not in tree_cache:
                    tree_cache[eid] = frozenset(engagement_descendants(db, eid))
                engs = tree_cache[eid]
            elif cap_scope == S.own_engagement and a.contractor_engagement_id:
                engs = frozenset({a.contractor_engagement_id})
            elif cap_scope in (S.contractor_tree, S.own_engagement):
                engs = frozenset()
            sites = frozenset(a.site_ids) if a.site_ids else None
            scope.grants[cap] = _merge(scope.grants.get(cap), Grant(cap_scope, sites, engs))
    employer_status = None
    if user.employer_contractor_id:
        employer_status = db.scalar(
            select(Contractor.status).where(Contractor.id == user.employer_contractor_id)
        )
    return Principal(
        user=user,
        session=session,
        today=day,
        is_manager=is_manager,
        projects=projects,
        employer_status=employer_status,
        active_assignments=assignments,
    )


def capability_list(scope: ProjectScope) -> Iterable[tuple[Capability, Grant]]:
    return sorted(scope.grants.items(), key=lambda kv: list(Capability).index(kv[0]))
