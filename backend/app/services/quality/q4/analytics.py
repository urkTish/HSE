"""KPI page, quality objectives (KPI targets) and the monthly work value behind COPQ % (spec
8-quality §E.1.1, §E.4, §E.6, §E.7). Targets and work value are edited by 239 holders."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType
from app.kpi import quality as qk
from app.kpi import quality_views as qv
from app.models.quality.q4 import QKpiTarget, QWorkValue
from app.services import audit
from app.services.permissions import Principal
from app.services.quality.q4 import base as b

C = b.C


def kpis(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    start: date | None,
    end: date | None,
    flt: qk.QFilter | None = None,
) -> dict[str, Any]:
    """GET /quality/kpis: default period = the last complete month before today."""
    project = b.project(db, p, project_id)
    today = b.today(project)
    if end is None:
        end = today.replace(day=1) - timedelta(days=1)
    if start is None:
        start = end.replace(day=1)
    return qv.page(db, p, project, start, end, today, flt)


def list_targets(db: Session, p: Principal, project_id: uuid.UUID) -> list[QKpiTarget]:
    b.viewer(db, p, project_id)
    return list(
        db.scalars(
            select(QKpiTarget)
            .where(QKpiTarget.project_id == project_id)
            .order_by(QKpiTarget.kpi_id, QKpiTarget.valid_from)
        )
    )


def set_target(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> QKpiTarget:
    project, _g = b.writer(db, p, project_id, C.quality_settings)
    row = db.scalar(
        select(QKpiTarget).where(
            QKpiTarget.project_id == project.id,
            QKpiTarget.kpi_id == body["kpi_id"],
            QKpiTarget.valid_from == body["valid_from"],
        )
    )
    if row is None:
        row = QKpiTarget(
            id=uuid.uuid4(),
            project_id=project.id,
            kpi_id=body["kpi_id"],
            valid_from=body["valid_from"],
            created_by_user_id=p.user.id,
        )
        db.add(row)
    row.target = body["target"]
    row.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.q_settings,
        entity_id=project.id,
        project_id=project.id,
        after={
            "kpi_target": row.kpi_id,
            "target": str(row.target),
            "valid_from": row.valid_from.isoformat(),
        },
    )
    return row


def list_work_value(db: Session, p: Principal, project_id: uuid.UUID) -> list[QWorkValue]:
    b.project(db, p, project_id)
    p.require(project_id, C.quality_settings)
    return list(
        db.scalars(
            select(QWorkValue).where(QWorkValue.project_id == project_id).order_by(QWorkValue.month)
        )
    )


def set_work_value(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> QWorkValue:
    project, _g = b.writer(db, p, project_id, C.quality_settings)
    month = body["month"].replace(day=1)
    row = db.scalar(
        select(QWorkValue).where(QWorkValue.project_id == project.id, QWorkValue.month == month)
    )
    if row is None:
        row = QWorkValue(
            id=uuid.uuid4(), project_id=project.id, month=month, created_by_user_id=p.user.id
        )
        db.add(row)
    row.value_sar = body["value_sar"]
    row.updated_by_user_id = p.user.id
    row.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.q_settings,
        entity_id=project.id,
        project_id=project.id,
        after={"work_value": month.isoformat(), "value_sar": str(row.value_sar)},
    )
    return row
