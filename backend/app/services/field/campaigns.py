"""Briefing campaigns (spec 6d-field-assurance §3.13, §4.5, CMP-1…CMP-4): draft, issue with pairs
fixed from the daily returns of the 14 days before issue, pair status (met / met on time from the
toolbox register), cancel, and the system close (due_date + 7 days)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import (
    CampaignAction,
    CampaignReason,
    CampaignStatus,
    TalkStatus,
    UnderstoodLanguage,
    VersionStatus,
)
from app.models import (
    BriefingCampaign,
    Incident,
    Site,
    TalkAttendance,
    ToolboxTalk,
    ToolboxTopic,
    WorkforceReturn,
)
from app.schemas.field import (
    CampaignCreate,
    CampaignPage,
    CampaignPair,
    CampaignRead,
    CampaignTransition,
    CampaignUpdate,
)
from app.schemas.hse_common import ApiWarning
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.field import common as fc
from app.services.hse_common import Refs, make_ref
from app.services.permissions import Principal

C = Capability
CS = CampaignStatus
COUNTED = (TalkStatus.delivered, TalkStatus.locked)


@dataclass
class PairState:
    engagement_id: uuid.UUID
    site_id: uuid.UUID
    met_on: date | None
    talk_no: str | None

    def on_time(self, due: date | None) -> bool:
        return self.met_on is not None and due is not None and self.met_on <= due


def pair_states(db: Session, c: BriefingCampaign) -> list[PairState]:
    """CMP-3: first briefed attendance (understood ≠ none) of a pair engagement's worker at a
    Delivered / Locked talk on the pair site with the campaign topic (any version), after issue."""
    out = []
    if not c.pairs or c.issued_at is None:
        return [
            PairState(uuid.UUID(x["engagement_id"]), uuid.UUID(x["site_id"]), None, None)
            for x in c.pairs or []
        ]
    T, A = ToolboxTalk, TalkAttendance  # noqa: N806
    rows = db.execute(
        select(A.engagement_id, T.site_id, T.delivered_date, T.talk_no)
        .join(T, T.id == A.talk_id)
        .where(
            T.project_id == c.project_id,
            T.status.in_(COUNTED),
            T.topic_codes.contains([c.topic_code]),
            T.delivered_at >= c.issued_at,
            A.understood_language != UnderstoodLanguage.none,
        )
        .order_by(T.delivered_at, T.talk_no)
    ).all()
    first: dict[tuple[uuid.UUID, uuid.UUID], tuple[date, str]] = {}
    for eng, site, d, no in rows:
        if eng is not None:
            first.setdefault((eng, site), (d, no))
    for x in c.pairs:
        k = (uuid.UUID(x["engagement_id"]), uuid.UUID(x["site_id"]))
        hit = first.get(k)
        out.append(PairState(k[0], k[1], hit[0] if hit else None, hit[1] if hit else None))
    return out


def campaign_read(db: Session, c: BriefingCampaign) -> CampaignRead:
    t = db.get(ToolboxTopic, c.topic_id)
    assert t is not None  # noqa: S101
    states = pair_states(db, c)
    refs = Refs(db).load(
        sites=[*c.site_ids, *[s.site_id for s in states]],
        engs=[s.engagement_id for s in states],
        users=[c.issued_by_user_id],
    )
    pairs = []
    for s in states:
        site = refs.site(s.site_id)
        assert site is not None  # noqa: S101
        pairs.append(
            CampaignPair(
                engagement=refs.eng(s.engagement_id),
                site=site,
                met=s.met_on is not None,
                met_on=s.met_on,
                on_time=s.on_time(c.due_date) if s.met_on else None,
                talk_no=s.talk_no,
            )
        )
    return CampaignRead(
        id=c.id,
        campaign_no=c.campaign_no,
        project_id=c.project_id,
        topic_id=c.topic_id,
        topic_code=c.topic_code,
        topic_version=t.version,
        topic_title_en=t.title_en,
        topic_title_ar=t.title_ar,
        reason=c.reason,
        reason_ref=c.reason_ref,
        message_en=c.message_en,
        message_ar=c.message_ar,
        sites=[s for s in (refs.site(x) for x in c.site_ids) if s is not None],
        pairs=pairs,
        met_count=sum(1 for s in states if s.met_on),
        issued_by=refs.user(c.issued_by_user_id),
        issued_at=c.issued_at,
        due_date=c.due_date,
        status=c.status,
        status_reason=c.status_reason,
        warnings=[ApiWarning(**w) for w in c.warnings or []],
    )


def _get(db: Session, p: Principal, campaign_id: uuid.UUID) -> BriefingCampaign:
    c = db.get(BriefingCampaign, campaign_id)
    if c is None or not p.can_see_project(c.project_id):
        raise not_found("Campaign")
    fc.view_grant(p, c.project_id)
    return c


def read_campaign(db: Session, p: Principal, campaign_id: uuid.UUID) -> CampaignRead:
    return campaign_read(db, _get(db, p, campaign_id))


def list_campaigns(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[CampaignStatus] | None,
    page: int,
    page_size: int,
) -> CampaignPage:
    fc.project(db, p, project_id)
    fc.view_grant(p, project_id)
    B = BriefingCampaign  # noqa: N806
    stmt = select(B).where(B.project_id == project_id)
    if statuses:
        stmt = stmt.where(B.status.in_(statuses))
    items, total = paginate(db, stmt.order_by(B.campaign_no.desc()), page, page_size)
    return CampaignPage(
        items=[campaign_read(db, c) for c in items], total=total, page=page, page_size=page_size
    )


def topic_ok(db: Session, topic_id: uuid.UUID) -> ToolboxTopic:
    """CMP-1 / TBT-2: a Published topic whose review is not overdue."""
    t = db.get(ToolboxTopic, topic_id)
    if t is None or t.status != VersionStatus.published:
        raise validation_error("topic_id", "Choose a Published topic.")
    if t.review_due_on is not None and t.review_due_on < fc.local_day():
        raise fc.err(
            422,
            ErrorCode.TOPIC_REVIEW_OVERDUE,
            f"{t.topic_code} is past its review date and cannot start a campaign.",
            "انتهى موعد مراجعة الموضوع ولا يمكن استخدامه في حملة.",
            field="topic_id",
        )
    return t


def _validate(db: Session, p: Principal, c: BriefingCampaign) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if c.reason == CampaignReason.incident:
        inc = (
            db.scalar(
                select(Incident).where(
                    Incident.project_id == c.project_id, Incident.ref == c.reason_ref
                )
            )
            if c.reason_ref
            else None
        )
        if inc is None:
            raise validation_error("reason_ref", "Give the Phase 1 incident ref (CMP-1).")
    if c.reason == CampaignReason.lesson:
        from app.services.followup.lessons import lesson_published_for  # noqa: PLC0415

        lesson_published_for(db, p, c.reason_ref)  # 6f LK-2
    if not ((c.message_en or "").strip() or (c.message_ar or "").strip()):
        raise validation_error("message_en", "Write the campaign message.")
    for k in ("message_en", "message_ar"):
        if fc.p18(getattr(c, k)):
            warnings.append(
                {"code": "POSSIBLE_ID_NUMBER", "field": k,
                 "message": "The message may contain an ID number (P1-8): remove it.",
                 "message_ar": "قد تحتوي الرسالة على رقم هوية: احذفه."}
            )  # fmt: skip
    for s in c.site_ids:
        site = db.get(Site, s)
        if site is None or site.project_id != c.project_id:
            raise validation_error("site_ids", "Sites of the project.")
    return warnings


def create_campaign(
    db: Session, p: Principal, project_id: uuid.UUID, body: CampaignCreate
) -> CampaignRead:
    proj = fc.project(db, p, project_id)
    ensure_open(proj)
    p.require(project_id, C.briefing_campaign_manage)
    t = topic_ok(db, body.topic_id)
    year = fc.local_day().year
    seq = fc.next_seq(db, BriefingCampaign, project_id, year)
    c = BriefingCampaign(
        campaign_no=make_ref("CMP", proj.code, year, seq, 3),
        year=year,
        seq=seq,
        project_id=project_id,
        topic_id=t.id,
        topic_code=t.topic_code,
        reason=body.reason,
        reason_ref=body.reason_ref,
        message_en=body.message_en,
        message_ar=body.message_ar,
        site_ids=list(dict.fromkeys(body.site_ids)),
        due_date=body.due_date,
        status=CS.draft,
        created_by_user_id=p.user.id,
    )
    c.warnings = _validate(db, p, c)
    db.add(c)
    db.flush()
    fc.record(db, p, AuditAction.create, EntityType.briefing_campaign, c, project_id)
    return campaign_read(db, c)


def update_campaign(
    db: Session, p: Principal, campaign_id: uuid.UUID, body: CampaignUpdate
) -> CampaignRead:
    c = _get(db, p, campaign_id)
    ensure_open(fc.project(db, p, c.project_id))
    p.require(c.project_id, C.briefing_campaign_manage)
    if c.status != CS.draft:
        raise invalid_transition("Campaign", c.status, c.status)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "site_ids" and v is None:
            continue
        setattr(c, k, v)
    c.warnings = _validate(db, p, c)
    c.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.update, EntityType.briefing_campaign, c, c.project_id)
    return campaign_read(db, c)


def fix_pairs(db: Session, c: BriefingCampaign, day: date) -> list[dict[str, str]]:
    """CMP-2: (engagement, site) with daily-return headcount > 0 on a campaign site in the 14 days
    before issue."""
    W = WorkforceReturn  # noqa: N806
    rows = db.execute(
        select(W.engagement_id, W.site_id)
        .where(
            W.project_id == c.project_id,
            W.site_id.in_(list(c.site_ids)),
            W.headcount > 0,
            W.work_date >= day - timedelta(days=14),
            W.work_date < day,
        )
        .distinct()
    ).all()
    return [
        {"engagement_id": str(e), "site_id": str(s)}
        for e, s in sorted(rows, key=lambda r: (str(r[1]), str(r[0])))
    ]


def transition_campaign(
    db: Session, p: Principal, campaign_id: uuid.UUID, body: CampaignTransition
) -> CampaignRead:
    c = _get(db, p, campaign_id)
    ensure_open(fc.project(db, p, c.project_id))
    p.require(c.project_id, C.briefing_campaign_manage)
    before = {"status": c.status.value}
    if body.action == CampaignAction.issue:
        if c.status != CS.draft:
            raise invalid_transition("Campaign", c.status, CS.issued)
        topic_ok(db, c.topic_id)
        c.warnings = _validate(db, p, c)
        day = fc.local_day()
        due = c.due_date or day + timedelta(
            days=int(fc.cfg(db, c.project_id)["campaign_default_days"])
        )
        if due < day + timedelta(days=1):
            raise validation_error("due_date", "Due at least one day after issue.")
        c.due_date = due
        c.issued_at = now()
        c.issued_by_user_id = p.user.id
        c.pairs = fix_pairs(db, c, day)
        c.status = CS.issued
        db.flush()
        issue_alert(db, c)
    else:
        if c.status not in (CS.draft, CS.issued):
            raise invalid_transition("Campaign", c.status, CS.cancelled)
        c.status_reason = fc.reason(body.reason, 10)
        c.status = CS.cancelled
    c.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.briefing_campaign, c, c.project_id,
              before=before)  # fmt: skip
    return campaign_read(db, c)


def _eng_reps(db: Session, c: BriefingCampaign, engs: set[uuid.UUID]) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for e in engs:
        out |= fc.reps(db, c.project_id, e)
    return out


def issue_alert(db: Session, c: BriefingCampaign) -> None:
    """CMP-4 at issue: reps of the pair engagements and the site engineers."""
    engs = {uuid.UUID(x["engagement_id"]) for x in c.pairs or []}
    people = _eng_reps(db, c, engs)
    for s in c.site_ids:
        people |= fc.site_engineers(db, c.project_id, s)
    fc.send(db, people, NotificationKind.briefing_campaign,
            f"Briefing campaign {c.campaign_no} ({c.topic_code}) due {c.due_date}",
            f"حملة توعية {c.campaign_no} ({c.topic_code}) مستحقة في {c.due_date}",
            c.project_id, EntityType.briefing_campaign, c.id, email=True)  # fmt: skip


def daily(db: Session, project_id: uuid.UUID, today: date) -> None:
    """CMP-4 reminders (due − 2 days: reps of unmet pairs; day after due: HSE Officers) and the
    §4.5 close at due_date + 7 days."""
    for c in db.scalars(
        select(BriefingCampaign).where(
            BriefingCampaign.project_id == project_id, BriefingCampaign.status == CS.issued
        )
    ):
        if c.due_date is None:
            continue
        # unmet as of the check: not briefed by min(today, due) (a later briefing is late, CMP-3)
        cutoff = min(today, c.due_date)
        unmet = [s for s in pair_states(db, c) if s.met_on is None or s.met_on > cutoff]
        if (
            unmet
            and today == c.due_date - timedelta(days=2)
            and fc.once(db, f"field:cmp:{c.id}:due2")
        ):
            fc.send(db, _eng_reps(db, c, {s.engagement_id for s in unmet}),
                    NotificationKind.briefing_campaign,
                    f"{c.campaign_no}: {len(unmet)} pair(s) not yet briefed, due {c.due_date}",
                    f"{c.campaign_no}: لم يكتمل التوعية لبعض المقاولين", c.project_id,
                    EntityType.briefing_campaign, c.id, email=True)  # fmt: skip
        if (
            unmet
            and today == c.due_date + timedelta(days=1)
            and fc.once(db, f"field:cmp:{c.id}:overdue")
        ):
            fc.send(db, fc.officers(db, project_id), NotificationKind.briefing_campaign,
                    f"{c.campaign_no} overdue: {len(unmet)} pair(s) unmet",
                    f"{c.campaign_no} متأخرة", c.project_id, EntityType.briefing_campaign,
                    c.id, email=True)  # fmt: skip
        if today > c.due_date + timedelta(days=7):
            c.status = CS.closed
            c.updated_at = now()
    db.flush()


def due_window(c: BriefingCampaign) -> datetime | None:
    return fc.day_start(c.due_date + timedelta(days=1)) if c.due_date else None
