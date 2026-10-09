"""6f follow-up band and action panel (spec 6f §8.1 item 2, §8.2)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.followup_enums import (
    FuActionKind,
    FuChangeStatus,
    FuCheckStatus,
    FuDistributionStatus,
    FuLessonStatus,
    FuLinkKind,
    FuPackStatus,
    FuRuleSource,
    FuStage,
)
from app.core.followup_enums import FuRequirementStatus as RS  # noqa: N814
from app.models import (
    FuDistribution,
    FuEffectivenessCheck,
    FuLesson,
    FuLessonLink,
    FuPack,
    FuRequirement,
    Incident,
)
from app.schemas.followup import FuActionItem, FuActionPanel, FuBand
from app.services.followup import common as fc
from app.services.followup import requirements as rq
from app.services.permissions import Principal

C = fc.C


def _reqs(
    db: Session, p: Principal, project_id: uuid.UUID
) -> list[tuple[FuRequirement, Incident, RS]]:
    g = fc.view_grant(db, p, project_id)
    rows = list(db.scalars(select(FuRequirement).where(FuRequirement.project_id == project_id)))
    subs = rq._valid_subs(db, [r.id for r in rows])
    t = now()
    out = []
    for r in rows:
        inc = db.get(Incident, r.incident_id)
        if inc is not None and rq.scope_ok(g, inc, r):
            out.append((r, inc, rq.status_of(r, subs.get(r.id, []), t)))
    return out


def _draft_packs(db: Session, reqs: list[FuRequirement]) -> list[FuPack]:
    ids = [r.id for r in reqs]
    if not ids:
        return []
    return list(
        db.scalars(
            select(FuPack)
            .where(FuPack.requirement_id.in_(ids), FuPack.status == FuPackStatus.draft)
            .order_by(FuPack.pack_no)
        )
    )


def _lessons_due(db: Session, project_id: uuid.UUID, until_days: int | None) -> list[FuLesson]:
    today = fc.local_day()
    out = []
    for ls in db.scalars(
        select(FuLesson)
        .where(
            FuLesson.source_project_id == project_id,
            FuLesson.required.is_(True),
            FuLesson.status.in_([FuLessonStatus.draft, FuLessonStatus.in_review]),
            FuLesson.publish_due_on.is_not(None),
        )
        .order_by(FuLesson.publish_due_on, FuLesson.lesson_no)
    ):
        due = ls.publish_due_on
        assert due is not None  # noqa: S101
        if (until_days is None and due < today) or (
            until_days is not None and due <= today + timedelta(days=until_days)
        ):
            out.append(ls)
    return out


def _overdue_sorted(
    rows: list[tuple[FuRequirement, Incident, RS]],
) -> list[tuple[FuRequirement, Incident, RS]]:
    od = [x for x in rows if x[2] == RS.overdue]
    return sorted(od, key=lambda x: (x[0].source != FuRuleSource.statutory, x[0].due_at))


def band(db: Session, p: Principal, project_id: uuid.UUID) -> FuBand:
    rows = _reqs(db, p, project_id)
    t = now()
    soon = [
        x
        for x in rows
        if x[0].stage == FuStage.verbal and x[2] == RS.due and x[0].due_at <= t + timedelta(hours=1)
    ]
    soon.sort(key=lambda x: x[0].due_at)
    show_packs = not fc.is_viewer(p, project_id)
    return FuBand(
        verbal_due_next_hour=[rq.to_read(db, r) for r, _i, _s in soon],
        overdue=[rq.to_read(db, r) for r, _i, _s in _overdue_sorted(rows)],
        packs_awaiting_approval=len(_draft_packs(db, [r for r, _i, _s in rows]))
        if show_packs
        else 0,
        lessons_publish_due_soon=[ls.lesson_no for ls in _lessons_due(db, project_id, 3)],
    )


def action_panel(db: Session, p: Principal, project_id: uuid.UUID) -> FuActionPanel:
    rows = _reqs(db, p, project_id)
    today = fc.local_day()
    g = p.grant(project_id, C.followup_view)
    items: list[FuActionItem] = []

    def add(kind: FuActionKind, refs: list[str]) -> None:
        if refs:
            items.append(FuActionItem(kind=kind, count=len(refs), refs=refs))

    add(
        FuActionKind.requirements_overdue,
        [f"{i.ref} {r.rule_code}" for r, i, _s in _overdue_sorted(rows)],
    )
    if not fc.is_viewer(p, project_id):
        add(
            FuActionKind.packs_awaiting_approval,
            [k.pack_no for k in _draft_packs(db, [r for r, _i, _s in rows])],
        )
    add(
        FuActionKind.lessons_past_publish_due,
        [x.lesson_no for x in _lessons_due(db, project_id, None)],
    )
    acks = []
    for it in db.scalars(
        select(FuDistribution)
        .where(
            FuDistribution.project_id == project_id,
            FuDistribution.status == FuDistributionStatus.pending,
            FuDistribution.ack_due_on < today,
        )
        .order_by(FuDistribution.ack_due_on)
    ):
        if g is None or g.covers_engagement(it.engagement_id):
            ls = db.get(FuLesson, it.lesson_id)
            acks.append(f"{ls.lesson_no if ls else ''} {fc.eng_code(db, it.engagement_id) or ''}")
    add(FuActionKind.acknowledgements_overdue, acks)
    checks = []
    for ch in db.scalars(
        select(FuEffectivenessCheck)
        .where(
            FuEffectivenessCheck.project_id == project_id,
            FuEffectivenessCheck.status == FuCheckStatus.scheduled,
            FuEffectivenessCheck.due_on < today,
        )
        .order_by(FuEffectivenessCheck.due_on)
    ):
        ls = db.get(FuLesson, ch.lesson_id)
        checks.append(ls.lesson_no if ls else "")
    add(FuActionKind.effectiveness_checks_overdue, checks)
    if p.has_any(C.field_library_author) or p.has_any(C.field_library_publish):
        cut = now() - timedelta(days=30)
        add(
            FuActionKind.template_changes_open,
            [
                f"{k.ref} {k.item_code or 'new'}"
                for k in db.scalars(
                    select(FuLessonLink).where(
                        FuLessonLink.kind == FuLinkKind.template_change,
                        FuLessonLink.status == FuChangeStatus.open,
                        FuLessonLink.created_at < cut,
                    )
                )
            ],
        )
    return FuActionPanel(items=items)
