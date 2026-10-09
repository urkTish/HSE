"""Helpers for Phase 6d tests (6d-field-assurance Appendix A world, clock 2026-10-06 10:00 Riyadh).
Tests use the ``field_seed`` fixture (Phase 0-6c template + the 6d seed, cloned per test) and
``clock``. Service calls take a Principal from ``P(db, "noura.qahtani")``."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import ChecklistTemplate, FieldAudit, Inspection, StopWorkOrder, ToolboxTopic
from app.seed_field import PNG, _answers
from app.services.field import library
from tests.cert_helpers import API, P, expect, project, worker
from tests.heat_helpers import eng, err, local, notified, tick, uid, zone
from tests.train_helpers import kpi

__all__ = [
    "API",
    "PNG",
    "P",
    "answers",
    "audit",
    "body",
    "eng",
    "err",
    "expect",
    "ins",
    "kpi",
    "local",
    "notified",
    "order",
    "project",
    "stop_fields",
    "submit",
    "tick",
    "topic",
    "tpl",
    "uid",
    "worker",
    "zone",
]


def tpl(db: Session, code: str) -> ChecklistTemplate:
    t = library.published(db, code)
    assert t is not None, code
    return t


def topic(db: Session, code: str) -> ToolboxTopic:
    t = db.scalar(
        select(ToolboxTopic)
        .where(ToolboxTopic.topic_code == code)
        .order_by(ToolboxTopic.version.desc())
    )
    assert t is not None, code
    return t


def ins(db: Session, ref: str) -> Inspection:
    x = db.scalar(select(Inspection).where(Inspection.ref == ref))
    assert x is not None, ref
    return x


def audit(db: Session, no: str) -> FieldAudit:
    x = db.scalar(select(FieldAudit).where(FieldAudit.audit_no == no))
    assert x is not None, no
    return x


def order(db: Session, no: str) -> StopWorkOrder:
    x = db.scalar(select(StopWorkOrder).where(StopWorkOrder.order_no == no))
    assert x is not None, no
    return x


def answers(
    db: Session, code: str, nc: set[str] | None = None, *, airside: bool = False, **values: Any
) -> list[dict[str, Any]]:
    """Every item answered compliant (na where allowed by the seed rule) except `nc`; `values`
    override single items: answers(db, "GSI", GSI_21={"answer": "na"})."""
    v = {k.replace("_", "-"): x for k, x in values.items()}
    return _answers(tpl(db, code), nc or set(), airside=airside, values=v)


def body(
    db: Session,
    code: str = "GSI",
    *,
    nc: set[str] | None = None,
    site: str | None = "S-LAND",
    zone_code: str | None = "Z-PIERB",
    eng_code: str | None = "NAJD",
    pcode: str = "ANIA-EXP",
    completed: datetime | None = None,
    stop: dict[str, Any] | None = None,
    answer_list: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    from tests.emer_helpers import site as site_of

    done = completed or now() - timedelta(minutes=5)
    airside = zone_code is not None and zone(db, zone_code).zone_type.value == "airside"
    out: dict[str, Any] = {
        "client_uuid": str(uuid.uuid4()),
        "template_code": code,
        "started_at": (done - timedelta(minutes=30)).isoformat(),
        "completed_at": done.isoformat(),
        "answers": answer_list if answer_list is not None else answers(db, code, nc,
                                                                       airside=airside),
    }  # fmt: skip
    if site:
        out["site_id"] = str(site_of(db, site).id)
    if zone_code:
        out["zone_id"] = str(zone(db, zone_code).id)
    if eng_code:
        out["engagement_id"] = str(eng(db, pcode, eng_code).id)
    if stop is not None:
        out["stop_work"] = stop
    out.update(extra)
    return out


def submit(db: Session, who: str, b: dict[str, Any], pcode: str = "ANIA-EXP") -> Any:
    from app.schemas.field import SubmissionCreate
    from app.services.field import execution

    return execution.submit(
        db, P(db, who), project(db, pcode).id, SubmissionCreate.model_validate(b)
    )


def stop_fields(at: datetime | None = None, permits: list[str] | None = None) -> dict[str, Any]:
    return {
        "activity_en": "Formwork striking at an open slab edge (TEST)",
        "instructed_role": "supervisor",
        "instructed_at": (at or now() - timedelta(minutes=4)).isoformat(),
        "permit_ids": permits or [],
    }
