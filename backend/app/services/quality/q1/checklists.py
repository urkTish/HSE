"""Quality checklists of Part B on the 6d engine (spec 8-quality Q-CHK-01…03): IR rounds use
templates of `quality_type` `ir_inspection` (owner type `q_ir_round`), punch walkdowns
`punch_walkdown` (owner type `q_punch_walkdown`). Answers are scored by
`app.services.field.scoring.evaluate` and stored as `checklist_responses` with
`execution.store_answers`, as 7b does. Quality responses never create 6d findings or CAs."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_date, now
from app.core.field_enums import (
    ResponseOwnerType,
    ResponseResult,
    TemplateKind,
    VersionStatus,
)
from app.models.field import ChecklistResponse, ChecklistTemplate
from app.services.quality import common as qc


def template_for(
    db: Session, code: str, quality_type: str, at: datetime | None = None
) -> ChecklistTemplate | None:
    """The version of a quality template Published at `at` (TPL-4), else the latest Published."""
    rows = list(
        db.scalars(
            select(ChecklistTemplate)
            .where(
                ChecklistTemplate.template_code == code,
                ChecklistTemplate.kind == TemplateKind.quality,
                ChecklistTemplate.quality_type == quality_type,
                ChecklistTemplate.status.in_([VersionStatus.published, VersionStatus.superseded]),
            )
            .order_by(ChecklistTemplate.version.desc())
        )
    )
    when = at or now()
    for t in rows:
        if (
            t.published_at
            and t.published_at <= when
            and (t.superseded_at is None or t.superseded_at > when)
        ):
            return t
    pub = [t for t in rows if t.status == VersionStatus.published]
    return pub[0] if pub else None


def record(
    db: Session,
    user_id: uuid.UUID,
    project: Any,
    owner_type: ResponseOwnerType,
    t: ChecklistTemplate,
    answers: list[dict[str, Any]],
    *,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    completed_at: datetime,
    photo_ids: list[uuid.UUID] | None = None,
    fld: str = "answers",
    client_uuid: uuid.UUID | None = None,
) -> tuple[ChecklistResponse, Any]:
    """Score and store one response (EXE-2 completeness: every shown scored item answered)."""
    from app.services.field import execution, scoring  # noqa: PLC0415

    raw = []
    for a in answers:
        x = dict(a)
        x.pop("photos", None)  # photos belong to the Quality record, not to 6d `field_photo`
        if photo_ids:
            x["photo_ids"] = [str(i) for i in photo_ids]
        raw.append(x)
    try:
        sc = scoring.evaluate(t.items, raw, airside=True, require_all=True)
    except Exception as exc:  # re-label the field path so the client sees which point
        from app.core.errors import ApiError  # noqa: PLC0415

        if isinstance(exc, ApiError) and exc.errors:
            for e in exc.errors:
                e.loc = ["body", fld, *[x for x in e.loc if x != "body"]]
        raise
    pct = sc.pct
    r = ChecklistResponse(
        project_id=project.id,
        client_uuid=client_uuid or uuid.uuid4(),
        owner_type=owner_type,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        inspection_type=None,
        site_id=site_id,
        zone_id=zone_id,
        engagement_id=engagement_id,
        airside=False,
        started_at=completed_at,
        completed_at=completed_at,
        completed_date=local_date(completed_at, qc.tz(project)),
        received_at=now(),
        inspector_id=user_id,
        answers=[],
        applicable_count=sc.applicable_count,
        compliant_count=sc.compliant_count,
        applicable_weight=sc.applicable_weight,
        earned_weight=sc.earned_weight,
        score_pct=scoring.q(pct) if pct is not None else None,
        critical_fail_count=sc.critical_fails,
        result=ResponseResult.fail if sc.critical_fails else ResponseResult.pass_,
        submitted=True,
        created_by_user_id=user_id,
    )
    db.add(r)
    db.flush()
    by_code = {a["item_code"]: (i, _Ans(a)) for i, a in enumerate(answers)}
    warnings: list[dict[str, Any]] = []
    r.answers = execution.store_answers(db, user_id, r, sc, by_code, warnings)
    r.warnings = warnings
    db.flush()
    return r, sc


class _Ans:
    """Attribute view of an answer dict for `execution.store_answers` (photos stay with Q1)."""

    def __init__(self, a: dict[str, Any]) -> None:
        self.answer = a.get("answer")
        nv = a.get("numeric_value")
        self.numeric_value = Decimal(str(nv)) if nv is not None else None
        self.count_value = a.get("count_value")
        self.note = a.get("note")
        self.photos: list[Any] = []
        self.equipment_ref = a.get("equipment_ref")


def response_read(db: Session, rid: uuid.UUID | str | None) -> dict[str, Any] | None:
    if not rid:
        return None
    r = db.get(ChecklistResponse, uuid.UUID(str(rid)))
    if r is None:
        return None
    t = db.get(ChecklistTemplate, r.template_id)
    texts = {it["item_code"]: it for it in (t.items if t else [])}
    return {
        "id": r.id,
        "template_code": r.template_code,
        "template_version": r.template_version,
        "title_en": t.title_en if t else r.template_code,
        "title_ar": t.title_ar if t else r.template_code,
        "applicable_count": r.applicable_count,
        "compliant_count": r.compliant_count,
        "score_pct": str(r.score_pct) if r.score_pct is not None else None,
        "critical_fail_count": r.critical_fail_count,
        "result": r.result,
        "answers": [
            {
                "item_code": a["item_code"],
                "text_en": texts.get(a["item_code"], {}).get("text_en"),
                "text_ar": texts.get(a["item_code"], {}).get("text_ar"),
                "answer": a.get("answer"),
                "numeric_value": a.get("numeric_value"),
                "note": a.get("note"),
                "compliant": a.get("compliant"),
                "critical": a.get("critical"),
            }
            for a in r.answers or []
        ],
    }
