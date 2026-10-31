"""Customers of a project (spec 8-quality §A.8.3). Read 238; edit 239 or 245. Contact details are
personal (P8-2, Q-CMP-02): shown only to 245 holders and omitted for everyone else."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import not_found
from app.core.quality.common import QCustomerKind, QCustomerStatus
from app.models.quality import QCustomer
from app.services import audit
from app.services.common import duplicate
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc

C = Capability
CONTACT = ("contact_name", "contact_mobile", "contact_email")


def read(c: QCustomer, contacts: bool) -> dict[str, Any]:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "code": c.code,
        "name_en": c.name_en,
        "name_ar": c.name_ar,
        "kind": c.kind,
        "owner_release_approval": c.owner_release_approval,
        "status": c.status,
        **{k: (getattr(c, k) if contacts else None) for k in CONTACT},
        "contacts_visible": contacts,
    }


def _contacts(p: Principal, project_id: uuid.UUID) -> bool:
    return p.grant(project_id, C.complaint_manage) is not None


def list_customers(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    if p.grant(project.id, C.quality_view) is None and not _contacts(p, project.id):
        raise forbidden_error()
    rows = db.scalars(
        select(QCustomer).where(QCustomer.project_id == project.id).order_by(QCustomer.code)
    )
    return [read(c, _contacts(p, project.id)) for c in rows]


def _editor(p: Principal, project_id: uuid.UUID) -> None:
    if (
        p.grant(project_id, C.quality_settings) is None
        and p.grant(project_id, C.complaint_manage) is None
    ):
        p.require(project_id, C.quality_settings)


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _editor(p, project.id)
    qc.require_profile(db, project)
    code = str(body["code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,12}", code):
        raise qc.field_err("code", "Code: 2–12 capital letters, digits or -.")
    if db.scalar(
        select(QCustomer.id).where(QCustomer.project_id == project.id, QCustomer.code == code)
    ):
        raise duplicate("code", "A customer with this code exists on the project.")
    c = QCustomer(
        project_id=project.id,
        code=code,
        name_en=body["name_en"],
        name_ar=body["name_ar"],
        kind=QCustomerKind(body["kind"]),
        owner_release_approval=bool(body.get("owner_release_approval", False)),
        status=QCustomerStatus.active,
        created_by_user_id=p.user.id,
        **{k: body.get(k) for k in CONTACT},
    )
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_customer,
        entity_id=c.id,
        project_id=project.id,
        after={"code": c.code},
    )
    return read(c, _contacts(p, project.id))


def update(
    db: Session, p: Principal, customer_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    c = db.get(QCustomer, customer_id)
    if c is None or not p.can_see_project(c.project_id):
        raise not_found("Customer")
    project = qc.get_project(db, p, c.project_id)
    qc.writable(project, p)
    _editor(p, project.id)
    before = read(c, True)
    for k in ("name_en", "name_ar", "owner_release_approval", *CONTACT):
        if k in body and body[k] is not None:
            setattr(c, k, body[k])
    if body.get("kind") is not None:
        c.kind = QCustomerKind(body["kind"])
    if body.get("status") is not None:
        c.status = QCustomerStatus(body["status"])
    c.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(before, read(c, True))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_customer,
            entity_id=c.id,
            project_id=project.id,
            before=b,
            after={k: v for k, v in a.items() if k not in CONTACT},
        )
    return read(c, _contacts(p, project.id))
