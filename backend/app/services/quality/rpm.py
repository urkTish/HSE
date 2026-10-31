"""Responsible-person matrix (spec 8-quality §A.4, Q-RPM-01…11): positions and holders, matrix
rows, resolution, segregation of duties and the one-record re-assignment.

No code path names a fixed signer: every step of list QRT is resolved through `q_rp_rules`
(Q-RPM-01). A user **resolves** for a step when the effective row names them (user), a platform
role they hold on the project with a scope covering the record (role), or a position they hold
(position), **and** they hold the step's capability on the project (Q-RPM-03). Signing then
checks segregation (Q-RPM-06) and the contractor's own tree (Q-RPM-07)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType, Role
from app.core.errors import ErrorCode
from app.core.quality.common import (
    DEFAULT_POSITIONS,
    RECORD_TYPES,
    QAssigneeKind,
    QProfileScope,
    QRecordType,
    QSectorProfile,
    StepDef,
    profile_allows,
    step_def,
)
from app.models import Project, RoleAssignment, User
from app.models.quality import QPosition, QPositionHolder, QRpRule, QSettings
from app.services import audit
from app.services.permissions import (
    QUALITY_ROLES,
    Grant,
    Principal,
    build_principal,
    engagement_descendants,
    forbidden_error,
)
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
S = CapabilityScope


# ---- seeding the defaults (§A.4.2, "on first Quality use") -------------------------------------


def _default_rows(profile: QSectorProfile) -> list[tuple[str, str, str | None, QAssigneeKind, str]]:
    rows: list[tuple[str, str, str | None, QAssigneeKind, str]] = []
    for rt, d in RECORD_TYPES.items():
        for st in d.steps:
            kind_value = st.default
            for prof, kind, value in st.by_profile:
                if prof == profile:
                    kind_value = (kind, value)
            if kind_value is not None:
                rows.append((rt.value, st.code, None, kind_value[0], kind_value[1]))
            for qual, kind, value in st.qualified:
                rows.append((rt.value, st.code, qual, kind, value))
    return rows


def seed_defaults(
    db: Session, project: Project, profile: QSectorProfile, user_id: uuid.UUID | None
) -> None:
    """Positions of the profile (missing ones) and, once per project, the default matrix."""
    from app.services.quality import settings as qs  # noqa: PLC0415

    have = {p.code for p in db.scalars(select(QPosition).where(QPosition.project_id == project.id))}
    for code, en, ar, scope in DEFAULT_POSITIONS:
        if code not in have and profile_allows(scope, profile):
            db.add(
                QPosition(
                    project_id=project.id,
                    code=code,
                    name_en=en,
                    name_ar=ar,
                    profile=scope,
                    active=True,
                    created_by_user_id=user_id,
                )
            )
    row = db.get(QSettings, project.id)
    if row is not None and row.defaults_seeded_at is None:
        paper = bool(qs.value(db, project.id, "paper_signoff_default"))
        for rt, step, qual, kind, value in _default_rows(profile):
            db.add(
                QRpRule(
                    project_id=project.id,
                    record_type=rt,
                    step=step,
                    qualifier=qual,
                    assignee_kind=kind,
                    assignee=value,
                    paper_allowed=paper,
                    created_by_user_id=user_id,
                )
            )
        row.defaults_seeded_at = now()
    db.flush()


# ---- effective row (Q-RPM-02) ------------------------------------------------------------------


def effective_rule(
    db: Session,
    project_id: uuid.UUID,
    record_type: QRecordType | str,
    step: str,
    *,
    qualifier: str | None = None,
    record_id: uuid.UUID | None = None,
) -> QRpRule | None:
    """The record's own override, then the most specific qualifier row, then the general row."""
    rows = list(
        db.scalars(
            select(QRpRule).where(
                QRpRule.project_id == project_id,
                QRpRule.record_type == str(QRecordType(record_type).value),
                QRpRule.step == step,
                QRpRule.active.is_(True),
            )
        )
    )
    if record_id is not None:
        own = [r for r in rows if r.record_id == record_id]
        if own:
            return max(own, key=lambda r: r.created_at)
    general = [r for r in rows if r.record_id is None]
    if qualifier is not None:
        q = [r for r in general if r.qualifier == qualifier]
        if q:
            return q[0]
    plain = [r for r in general if r.qualifier is None]
    return plain[0] if plain else None


# ---- resolution (Q-RPM-03, -04) ----------------------------------------------------------------


@dataclass
class Ctx:
    """What resolution needs to know about one record."""

    site_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    requesters: frozenset[uuid.UUID] = frozenset()
    on: date | None = None


@dataclass
class Resolution:
    rule: QRpRule | None
    users: dict[uuid.UUID, str] = field(default_factory=dict)  # user → capacity at signing


def _covers(g: Grant | None, ctx: Ctx) -> bool:
    if g is None:
        return False
    if g.scope == S.responsible:
        return True
    if ctx.site_id is not None and not g.covers_site(ctx.site_id):
        return False
    return g.engagement_ids is None or (
        ctx.engagement_id is not None and ctx.engagement_id in g.engagement_ids
    )


class _Grants:
    """Per-call cache of principals built for candidate users."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cache: dict[uuid.UUID, Principal | None] = {}

    def principal(self, uid: uuid.UUID) -> Principal | None:
        if uid not in self.cache:
            u = qc.active_user(self.db, uid)
            self.cache[uid] = build_principal(self.db, u, None) if u else None
        return self.cache[uid]

    def grant(self, uid: uuid.UUID, project_id: uuid.UUID, cap: Capability) -> Grant | None:
        p = self.principal(uid)
        return p.grant(project_id, cap) if p else None


def _position_holders(db: Session, project_id: uuid.UUID, code: str, on: date) -> list[uuid.UUID]:
    pos = db.scalar(
        select(QPosition).where(
            QPosition.project_id == project_id, QPosition.code == code, QPosition.active.is_(True)
        )
    )
    if pos is None:
        return []
    return [
        h.user_id
        for h in db.scalars(select(QPositionHolder).where(QPositionHolder.position_id == pos.id))
        if h.valid_from <= on and (h.valid_to is None or h.valid_to >= on)
    ]


def _role_users(db: Session, project: Project, role: str, ctx: Ctx, on: date) -> list[uuid.UUID]:
    out = []
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project.id,
            RoleAssignment.role == role,
            RoleAssignment.revoked_at.is_(None),
        )
    ):
        if not a.is_active_on(on):
            continue
        if ctx.site_id is not None and a.site_ids and ctx.site_id not in a.site_ids:
            continue
        out.append(a.user_id)
    return out


def _capacity(db: Session, rule: QRpRule) -> str:
    if rule.assignee_kind == QAssigneeKind.position:
        pos = db.scalar(
            select(QPosition).where(
                QPosition.project_id == rule.project_id, QPosition.code == rule.assignee
            )
        )
        return f"position:{rule.assignee}" + (f" ({pos.name_en})" if pos else "")
    if rule.assignee_kind == QAssigneeKind.role:
        return f"role:{rule.assignee}"
    return "named user"


def resolve(
    db: Session,
    project: Project,
    record_type: QRecordType,
    step: str,
    ctx: Ctx,
    *,
    qualifier: str | None = None,
    record_id: uuid.UUID | None = None,
    grants: _Grants | None = None,
) -> Resolution:
    sd = step_def(record_type, step)
    rule = effective_rule(
        db, project.id, record_type, step, qualifier=qualifier, record_id=record_id
    )
    if sd is None or rule is None:
        return Resolution(rule)
    on = ctx.on or qc.project_day(project)
    gs = grants or _Grants(db)
    if rule.assignee_kind == QAssigneeKind.user:
        try:
            cands = [uuid.UUID(rule.assignee)]
        except ValueError:
            cands = []
    elif rule.assignee_kind == QAssigneeKind.role:
        cands = _role_users(db, project, rule.assignee, ctx, on)
    else:
        cands = _position_holders(db, project.id, rule.assignee, on)
    capacity = _capacity(db, rule)
    users = {
        uid: capacity
        for uid in dict.fromkeys(cands)
        if _covers(gs.grant(uid, project.id, sd.capability), ctx)
    }
    return Resolution(rule, users)


def _own_tree_conflict(db: Session, p: Principal, project_id: uuid.UUID, ctx: Ctx) -> bool:
    """Q-RPM-07: the signer is contractor-assigned and the record's engagement is in that tree."""
    if ctx.engagement_id is None:
        return False
    for a in p.active_assignments:
        if a.project_id != project_id or a.contractor_engagement_id is None:
            continue
        if ctx.engagement_id in engagement_descendants(db, a.contractor_engagement_id):
            return True
    return False


def sod_problem(
    db: Session, p: Principal, project_id: uuid.UUID, rule: QRpRule, ctx: Ctx
) -> str | None:
    if p.user.id in ctx.requesters and not rule.self_approval_allowed:
        return "requester"
    if not rule.own_tree_allowed and _own_tree_conflict(db, p, project_id, ctx):
        return "own_tree"
    return None


def not_set_error(record_type: QRecordType, step: str) -> Any:
    return qc.err(
        422,
        ErrorCode.RESPONSIBLE_PERSON_NOT_SET,
        f"No responsible person is set for {record_type.value}.{step}; ask the Quality settings "
        "owner to complete the matrix.",
        "لم يُحدَّد الشخص المسؤول لهذه الخطوة؛ اطلب استكمال مصفوفة المسؤوليات.",
        record_type=record_type.value,
        step=step,
    )


def check_signer(
    db: Session,
    p: Principal,
    project: Project,
    record_type: QRecordType,
    step: str,
    ctx: Ctx,
    *,
    qualifier: str | None = None,
    record_id: uuid.UUID | None = None,
) -> tuple[QRpRule, str]:
    """The rule and the capacity in which `p` signs, or 422 RESPONSIBLE_PERSON_NOT_SET /
    403 (does not resolve, Q-RPM-09) / 422 SOD_CONFLICT (Q-RPM-06, -07)."""
    p.ensure_writer()
    res = resolve(db, project, record_type, step, ctx, qualifier=qualifier, record_id=record_id)
    if res.rule is None:
        raise not_set_error(record_type, step)
    if p.user.id not in res.users:
        raise forbidden_error(
            f"You are not the responsible person for {record_type.value}.{step} on this record."
        )
    problem = sod_problem(db, p, project.id, res.rule, ctx)
    if problem == "requester":
        raise qc.err(
            422,
            ErrorCode.SOD_CONFLICT,
            "You created, requested or submitted this record, so another responsible person "
            "must sign this step (Q-RPM-06).",
            "أنت من أنشأ السجل أو طلبه أو قدّمه؛ يجب أن يوقّع شخص مسؤول آخر هذه الخطوة.",
        )
    if problem == "own_tree":
        raise qc.err(
            422,
            ErrorCode.SOD_CONFLICT,
            "This record belongs to your own contractor tree; contractor self-certification is "
            "not allowed for this step (Q-RPM-07).",
            "هذا السجل يخص شجرة المقاول التابع لها؛ لا يُسمح بالاعتماد الذاتي لهذه الخطوة.",
        )
    return res.rule, res.users[p.user.id]


def resolves(
    db: Session,
    p: Principal,
    project: Project,
    record_type: QRecordType,
    step: str,
    ctx: Ctx,
    *,
    qualifier: str | None = None,
    record_id: uuid.UUID | None = None,
    can_act: bool = True,
) -> bool:
    res = resolve(db, project, record_type, step, ctx, qualifier=qualifier, record_id=record_id)
    if res.rule is None or p.user.id not in res.users:
        return False
    return not can_act or sod_problem(db, p, project.id, res.rule, ctx) is None


# ---- pending steps from open steps (Q-RPM-10, -11) ----------------------------------------------


def pending_from_open(
    db: Session, p: Principal, project: Project, steps: Iterable[reg.OpenStep]
) -> list[reg.PendingStep]:
    gs = _Grants(db)
    out = []
    for o in steps:
        ctx = Ctx(o.site_id, o.engagement_id, o.requesters)
        res = resolve(
            db,
            project,
            o.step.record_type,
            o.step.step,
            ctx,
            qualifier=o.qualifier,
            record_id=o.step.record_id,
            grants=gs,
        )
        if res.rule is None or p.user.id not in res.users:
            continue
        if sod_problem(db, p, project.id, res.rule, ctx) is None:
            out.append(o.step)
    return out


def without_rp(db: Session, project: Project) -> list[reg.OpenStep]:
    """Open steps whose resolved set is empty (no row, or nobody resolves)."""
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    gs = _Grants(db)
    out = []
    for fn in reg.OPEN_STEPS.values():
        for o in fn(db, project):
            res = resolve(
                db,
                project,
                o.step.record_type,
                o.step.step,
                Ctx(o.site_id, o.engagement_id, o.requesters),
                qualifier=o.qualifier,
                record_id=o.step.record_id,
                grants=gs,
            )
            if not res.users:
                out.append(o)
    return out


# ---- positions and holders (§A.4.1) -------------------------------------------------------------


def _position_read(db: Session, pos: QPosition) -> dict[str, Any]:
    holders = list(
        db.scalars(
            select(QPositionHolder)
            .where(QPositionHolder.position_id == pos.id)
            .order_by(QPositionHolder.valid_from)
        )
    )
    users = {
        u.id: u for u in db.scalars(select(User).where(User.id.in_([h.user_id for h in holders])))
    }
    return {
        "id": pos.id,
        "code": pos.code,
        "name_en": pos.name_en,
        "name_ar": pos.name_ar,
        "profile": pos.profile,
        "active": pos.active,
        "holders": [
            {
                "id": h.id,
                "user": {
                    "id": h.user_id,
                    "full_name_en": users[h.user_id].full_name_en if h.user_id in users else "—",
                    "full_name_ar": users[h.user_id].full_name_ar if h.user_id in users else None,
                },
                "valid_from": h.valid_from,
                "valid_to": h.valid_to,
            }
            for h in holders
        ],
    }


def list_positions(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    if (
        p.grant(project.id, C.quality_view) is None
        and p.grant(project.id, C.quality_settings) is None
    ):
        raise forbidden_error()
    rows = db.scalars(
        select(QPosition).where(QPosition.project_id == project.id).order_by(QPosition.code)
    )
    return [_position_read(db, r) for r in rows]


def _settings_writer(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    return project


def create_position(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    import re  # noqa: PLC0415

    project = _settings_writer(db, p, project_id)
    code = str(body["code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]{2,20}", code):
        raise qc.field_err("code", "Code: 2–20 capital letters, digits or _.", "الرمز غير صالح.")
    if db.scalar(
        select(QPosition.id).where(QPosition.project_id == project.id, QPosition.code == code)
    ):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("code", "A position with this code exists on the project.")
    pos = QPosition(
        project_id=project.id,
        code=code,
        name_en=body["name_en"],
        name_ar=body["name_ar"],
        profile=QProfileScope(body.get("profile") or "both"),
        active=True,
        created_by_user_id=p.user.id,
    )
    db.add(pos)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_position,
        entity_id=pos.id,
        project_id=project.id,
        after={"code": code},
    )
    return _position_read(db, pos)


def update_position(
    db: Session, p: Principal, position_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    pos = db.get(QPosition, position_id)
    if pos is None:
        from app.core.errors import not_found  # noqa: PLC0415

        raise not_found("Position")
    project = _settings_writer(db, p, pos.project_id)
    before = {k: getattr(pos, k) for k in ("name_en", "name_ar", "profile", "active")}
    for k in ("name_en", "name_ar", "active"):
        if body.get(k) is not None:
            setattr(pos, k, body[k])
    if body.get("profile") is not None:
        pos.profile = QProfileScope(body["profile"])
    pos.updated_by_user_id = p.user.id
    db.flush()
    after = {k: getattr(pos, k) for k in before}
    b, a = audit.diff(before, after)
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_position,
            entity_id=pos.id,
            project_id=project.id,
            before=b,
            after=a,
        )
    return _position_read(db, pos)


def add_holder(
    db: Session, p: Principal, position_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    from app.core.errors import not_found  # noqa: PLC0415
    from app.services.hse_common import user_roles  # noqa: PLC0415

    pos = db.get(QPosition, position_id)
    if pos is None:
        raise not_found("Position")
    project = _settings_writer(db, p, pos.project_id)
    uid = uuid.UUID(str(body["user_id"]))
    if qc.active_user(db, uid) is None or not user_roles(db, uid, project.id):
        raise qc.field_err(
            "user_id",
            "The holder must be an active user with a role on this project (invite external "
            "people as responsible_person first, Q-RPM-08).",
            "يجب أن يكون الشاغل مستخدماً نشطاً له دور في المشروع.",
        )
    vf = body.get("valid_from") or qc.project_day(project)
    vt = body.get("valid_to")
    if vt is not None and vt < vf:
        raise qc.field_err("valid_to", "valid_to must be on or after valid_from.")
    h = QPositionHolder(
        position_id=pos.id, user_id=uid, valid_from=vf, valid_to=vt, created_by_user_id=p.user.id
    )
    db.add(h)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.q_position,
        entity_id=pos.id,
        project_id=project.id,
        details={"holder_added": str(uid), "valid_from": str(vf)},
    )
    return _position_read(db, pos)


def end_holder(
    db: Session, p: Principal, holder_id: uuid.UUID, valid_to: date | None
) -> dict[str, Any]:
    from app.core.errors import not_found  # noqa: PLC0415

    h = db.get(QPositionHolder, holder_id)
    pos = db.get(QPosition, h.position_id) if h else None
    if h is None or pos is None:
        raise not_found("Position holder")
    project = _settings_writer(db, p, pos.project_id)
    h.valid_to = valid_to or qc.project_day(project)
    h.valid_to = max(h.valid_to, h.valid_from)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.q_position,
        entity_id=pos.id,
        project_id=project.id,
        details={"holder_ended": str(h.user_id), "valid_to": str(h.valid_to)},
    )
    return _position_read(db, pos)


# ---- matrix rows (§A.4.3) -----------------------------------------------------------------------


def rule_read(r: QRpRule) -> dict[str, Any]:
    sd = step_def(r.record_type, r.step)
    rt = RECORD_TYPES.get(QRecordType(r.record_type))
    return {
        "id": r.id,
        "record_type": r.record_type,
        "step": r.step,
        "qualifier": r.qualifier,
        "record_id": r.record_id,
        "assignee_kind": r.assignee_kind,
        "assignee": r.assignee,
        "self_approval_allowed": r.self_approval_allowed,
        "own_tree_allowed": r.own_tree_allowed,
        "paper_allowed": r.paper_allowed,
        "active": r.active,
        "reason": r.reason,
        "part": rt.part if rt else None,
        "profile": rt.profile if rt else None,
        "capability": sd.capability if sd else None,
        "step_en": sd.en if sd else r.step,
        "step_ar": sd.ar if sd else r.step,
    }


def list_rules(
    db: Session, p: Principal, project_id: uuid.UUID, record_type: str | None = None
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    if (
        p.grant(project.id, C.quality_view) is None
        and p.grant(project.id, C.quality_settings) is None
    ):
        raise forbidden_error()
    stmt = select(QRpRule).where(QRpRule.project_id == project.id, QRpRule.record_id.is_(None))
    if record_type:
        stmt = stmt.where(QRpRule.record_type == record_type)
    rows = db.scalars(stmt.order_by(QRpRule.record_type, QRpRule.step, QRpRule.qualifier))
    return [rule_read(r) for r in rows]


def _check_assignee(db: Session, project: Project, kind: QAssigneeKind, value: str) -> str:
    if kind == QAssigneeKind.role:
        try:
            Role(value)
        except ValueError as exc:
            raise qc.field_err("assignee", "Unknown role.", "دور غير معروف.") from exc
        return value
    if kind == QAssigneeKind.position:
        if not db.scalar(
            select(QPosition.id).where(QPosition.project_id == project.id, QPosition.code == value)
        ):
            raise qc.field_err("assignee", "Unknown position on this project.", "منصب غير معروف.")
        return value
    try:
        uid = uuid.UUID(value)
    except ValueError as exc:
        raise qc.field_err("assignee", "A user id is required.", "معرف المستخدم مطلوب.") from exc
    if qc.active_user(db, uid) is None:
        raise qc.field_err("assignee", "The user is not active.", "المستخدم غير نشط.")
    return str(uid)


def create_rule(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = _settings_writer(db, p, project_id)
    rt = QRecordType(body["record_type"])
    sd: StepDef | None = step_def(rt, body["step"])
    if sd is None:
        raise qc.field_err("step", "This record type has no such step.", "خطوة غير معروفة.")
    kind = QAssigneeKind(body["assignee_kind"])
    r = QRpRule(
        project_id=project.id,
        record_type=rt.value,
        step=sd.code,
        qualifier=body.get("qualifier") or None,
        assignee_kind=kind,
        assignee=_check_assignee(db, project, kind, str(body["assignee"])),
        self_approval_allowed=bool(body.get("self_approval_allowed", False)),
        own_tree_allowed=bool(body.get("own_tree_allowed", False)),
        paper_allowed=bool(body.get("paper_allowed", True)),
        active=True,
        created_by_user_id=p.user.id,
    )
    # one active general row per (type, step, qualifier): the new row replaces the old one
    for old in db.scalars(
        select(QRpRule).where(
            QRpRule.project_id == project.id,
            QRpRule.record_type == r.record_type,
            QRpRule.step == r.step,
            QRpRule.record_id.is_(None),
            QRpRule.active.is_(True),
        )
    ):
        if old.qualifier == r.qualifier:
            old.active = False
    db.add(r)
    db.flush()
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.q_rp_rule,
        entity_id=r.id,
        project_id=project.id,
        after=rule_read(r),
    )
    return rule_read(r)


def update_rule(
    db: Session, p: Principal, rule_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    from app.core.errors import not_found  # noqa: PLC0415

    r = db.get(QRpRule, rule_id)
    if r is None or r.record_id is not None:
        raise not_found("Matrix row")
    project = _settings_writer(db, p, r.project_id)
    before = rule_read(r)
    if body.get("assignee_kind") is not None or body.get("assignee") is not None:
        kind = QAssigneeKind(body.get("assignee_kind") or r.assignee_kind)
        r.assignee_kind = kind
        r.assignee = _check_assignee(db, project, kind, str(body.get("assignee") or r.assignee))
    for k in ("self_approval_allowed", "own_tree_allowed", "paper_allowed", "active"):
        if body.get(k) is not None:
            setattr(r, k, bool(body[k]))
    r.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(before, rule_read(r))
    if a:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.q_rp_rule,
            entity_id=r.id,
            project_id=project.id,
            before=b,
            after=a,
        )
    return rule_read(r)


def reassign(
    db: Session,
    p: Principal,
    project: Project,
    record_type: QRecordType,
    record_id: uuid.UUID,
    step: str,
    kind: QAssigneeKind,
    assignee: str,
    why: str | None,
) -> QRpRule:
    """Q-RPM-09: the HSE Manager or a 239 holder re-assigns one pending step on one record
    (reason ≥ 20, audited). They never sign in the resolved person's place."""
    qc.writable(project, p)
    if not p.is_manager and p.grant(project.id, C.quality_settings) is None:
        raise forbidden_error("Re-assigning a step needs capability 239 or the HSE Manager.")
    if step_def(record_type, step) is None:
        raise qc.field_err("step", "This record type has no such step.", "خطوة غير معروفة.")
    text = qc.reason(why, 20)
    for old in db.scalars(
        select(QRpRule).where(
            QRpRule.record_id == record_id, QRpRule.step == step, QRpRule.active.is_(True)
        )
    ):
        old.active = False
    base = effective_rule(db, project.id, record_type, step)
    r = QRpRule(
        project_id=project.id,
        record_type=record_type.value,
        step=step,
        record_id=record_id,
        assignee_kind=kind,
        assignee=_check_assignee(db, project, kind, assignee),
        self_approval_allowed=base.self_approval_allowed if base else False,
        own_tree_allowed=base.own_tree_allowed if base else False,
        paper_allowed=base.paper_allowed if base else True,
        active=True,
        reason=text,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    from app.core.quality.common import entity_type_value  # noqa: PLC0415

    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType(entity_type_value(record_type)),
        entity_id=record_id,
        project_id=project.id,
        details={"step_reassigned": step, "to": f"{kind.value}:{r.assignee}", "reason": text},
    )
    return r


def quality_role_users(db: Session, project: Project) -> list[uuid.UUID]:
    return sorted({a.user_id for role in QUALITY_ROLES for a in qc.role_holders(db, project, role)})
