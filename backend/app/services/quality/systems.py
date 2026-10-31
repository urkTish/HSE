"""Systems register (spec 8-quality §A.8.1): construction only — creating or reactivating a
system on a project with the logistics profile gives 409 PROFILE_INACTIVE (Q-PRF-04); existing
systems stay readable. Read 238, edit 239."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import not_found
from app.core.quality.common import QActiveStatus, QDiscipline, QProfileScope
from app.models import Zone
from app.models.quality import QSystem
from app.services import audit
from app.services.common import duplicate
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc

C = Capability


def read(s: QSystem) -> dict[str, Any]:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "code": s.code,
        "name_en": s.name_en,
        "name_ar": s.name_ar,
        "discipline": s.discipline,
        "parent_id": s.parent_id,
        "zone_ids": list(s.zone_ids or []),
        "status": s.status,
    }


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if p.grant(project_id, C.quality_view) is None and p.grant(project_id, C.ncr_raise) is None:
        raise forbidden_error()


def list_systems(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    rows = db.scalars(
        select(QSystem).where(QSystem.project_id == project.id).order_by(QSystem.code)
    )
    return [read(s) for s in rows]


def get_system(db: Session, p: Principal, system_id: uuid.UUID) -> QSystem:
    s = db.get(QSystem, system_id)
    if s is None or not p.can_see_project(s.project_id):
        raise deny(db, p, EntityType.q_system, system_id, s.project_id if s else None, "System")
    _view(p, s.project_id)
    return s


def _depth(db: Session, parent_id: uuid.UUID | None) -> int:
    d = 0
    while parent_id is not None and d < 5:
        parent = db.get(QSystem, parent_id)
        parent_id = parent.parent_id if parent else None
        d += 1
    return d


def _validate(db: Session, project_id: uuid.UUID, s: QSystem) -> None:
    if s.parent_id is not None:
        parent = db.get(QSystem, s.parent_id)
        if parent is None or parent.project_id != project_id or parent.id == s.id:
            raise qc.field_err("parent_id", "The parent system is not on this project.")
        if _depth(db, s.parent_id) >= 3:
            raise qc.field_err("parent_id", "Systems nest at most 3 levels.")
    for zid in s.zone_ids or []:
        z = db.get(Zone, zid)
        if z is None or z.project_id != project_id:
            raise qc.field_err("zone_ids", "Every zone must belong to the project.")


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    qc.ensure_profile_for(db, project, QProfileScope.construction, "Systems")
    code = str(body["code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,20}", code):
        raise qc.field_err("code", "Code: 2–20 capital letters, digits or -.")
    if db.scalar(select(QSystem.id).where(QSystem.project_id == project.id, QSystem.code == code)):
        raise duplicate("code", "A system with this code exists on the project.")
    s = QSystem(
        project_id=project.id,
        code=code,
        name_en=body["name_en"],
        name_ar=body["name_ar"],
        discipline=QDiscipline(body["discipline"]),
        parent_id=body.get("parent_id"),
        zone_ids=list(body.get("zone_ids") or []),
        status=QActiveStatus.active,
        created_by_user_id=p.user.id,
    )
    _validate(db, project.id, s)
    db.add(s)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_system,
        entity_id=s.id,
        project_id=project.id,
        after=read(s),
    )
    return read(s)


def update(db: Session, p: Principal, system_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    s = db.get(QSystem, system_id)
    if s is None:
        raise not_found("System")
    project = qc.get_project(db, p, s.project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    before = read(s)
    for k in ("name_en", "name_ar", "parent_id"):
        if k in body and (body[k] is not None or k == "parent_id"):
            setattr(s, k, body[k])
    if body.get("discipline") is not None:
        s.discipline = QDiscipline(body["discipline"])
    if body.get("zone_ids") is not None:
        s.zone_ids = list(body["zone_ids"])
    if body.get("status") is not None:
        new = QActiveStatus(body["status"])
        if new == QActiveStatus.active and s.status != QActiveStatus.active:
            qc.ensure_profile_for(db, project, QProfileScope.construction, "Systems")
        s.status = new
    _validate(db, project.id, s)
    s.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(before, read(s))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_system,
            entity_id=s.id,
            project_id=project.id,
            before=b,
            after=a,
        )
    return read(s)
