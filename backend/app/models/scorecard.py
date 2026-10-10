"""Phase 6g tables (spec 6g-scorecard-reports §3): scorecard profiles and settings, engagement
scorecards and their lines, comments and disputes, watch-list entries, report packs with
distribution lists and deliveries, and the generic export jobs and subscriptions."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.scorecard_enums import (
    RpChannel,
    RpDeliveryStatus,
    RpLanguage,
    RpMemberKind,
    RpStatus,
    RpType,
    ScCardStatus,
    ScDisputeReason,
    ScGrade,
    ScLineStatus,
    ScProfileStatus,
    ScRankStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScResolution,
    ScScope,
    ScTrend,
    ScWatchDecision,
    ScWatchLevel,
    ScWatchProposal,
    ScWatchStatus,
    ScWindow,
    XpFormat,
    XpFrequency,
    XpJobStatus,
    XpPurpose,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col

EXACT = Numeric(24, 12)


class ScProfile(Audited, Base):
    """§3.1 profile version (project_id null = the organisation default `ORG`)."""

    __tablename__ = "sc_profiles"
    __table_args__ = (UniqueConstraint("profile_code", "version"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    profile_code: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    effective_from_month: Mapped[date] = mapped_column(Date)
    pillars: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    caps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    bands: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[ScProfileStatus] = enum_col(ScProfileStatus, default=ScProfileStatus.draft)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScSettings(Base):
    """§3.9 settings (one row per project); keys other than the columns live in `values`."""

    __tablename__ = "project_scorecard_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    scorecard_from_month: Mapped[date | None] = mapped_column(Date)
    source_live_from: Mapped[dict[str, str | None]] = mapped_column(JSONB, default=dict)
    sources_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sources_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id")
    )
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ScCard(Audited, Base):
    """§3.2 engagement scorecard (one per engagement × month × scope × revision)."""

    __tablename__ = "sc_cards"
    __table_args__ = (
        UniqueConstraint("engagement_id", "month", "scope", "revision"),
        Index("ix_sc_card_project_month", "project_id", "month"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    month: Mapped[date] = mapped_column(Date)  # first day of the month
    revision: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[ScScope] = enum_col(ScScope, default=ScScope.own)
    scorecard_no: Mapped[str] = mapped_column(String(80))
    profile_code: Mapped[str] = mapped_column(String(16))
    profile_version: Mapped[int] = mapped_column(Integer)
    month_man_hours: Mapped[Decimal] = mapped_column(EXACT)
    r12_man_hours: Mapped[Decimal] = mapped_column(EXACT)
    credibility_z: Mapped[Decimal] = mapped_column(EXACT)
    score: Mapped[Decimal | None] = mapped_column(EXACT)
    coverage_pct: Mapped[Decimal] = mapped_column(EXACT)
    band_grade: Mapped[ScGrade | None] = enum_col(ScGrade, nullable=True)
    grade: Mapped[ScGrade | None] = enum_col(ScGrade, nullable=True)
    caps_applied: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    pillars: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    trend_delta: Mapped[Decimal | None] = mapped_column(EXACT)
    trend_label: Mapped[ScTrend | None] = enum_col(ScTrend, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer)
    rank_of: Mapped[int | None] = mapped_column(Integer)
    rank_status: Mapped[ScRankStatus | None] = enum_col(ScRankStatus, nullable=True)
    commended: Mapped[bool] = mapped_column(Boolean, default=False)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    comment_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScCardStatus] = enum_col(ScCardStatus, default=ScCardStatus.issued)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reissue_reason: Mapped[str | None] = mapped_column(String(500))
    revised_since_final: Mapped[bool] = mapped_column(Boolean, default=False)
    recomputed_score: Mapped[Decimal | None] = mapped_column(EXACT)


class ScLine(UUIDPk, Base):
    """§3.3 one metric line of a card (frozen with the card)."""

    __tablename__ = "sc_lines"
    __table_args__ = (UniqueConstraint("card_id", "metric_code"),)

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sc_cards.id", ondelete="CASCADE"))
    metric_code: Mapped[str] = mapped_column(String(20))
    pillar_code: Mapped[str] = mapped_column(String(8))
    kpi_ref: Mapped[str] = mapped_column(String(12))
    window: Mapped[ScWindow] = enum_col(ScWindow)
    value: Mapped[Decimal | None] = mapped_column(EXACT)
    numerator: Mapped[Decimal | None] = mapped_column(EXACT)
    denominator: Mapped[Decimal | None] = mapped_column(EXACT)
    base: Mapped[int | None] = mapped_column(Integer)
    own_value: Mapped[Decimal | None] = mapped_column(EXACT)
    project_value: Mapped[Decimal | None] = mapped_column(EXACT)
    points: Mapped[Decimal | None] = mapped_column(EXACT)
    line_status: Mapped[ScLineStatus] = enum_col(ScLineStatus)
    original_weight: Mapped[Decimal] = mapped_column(EXACT)
    effective_weight: Mapped[Decimal] = mapped_column(EXACT)
    contribution: Mapped[Decimal] = mapped_column(EXACT)
    note: Mapped[str | None] = mapped_column(String(300))


class ScRemark(Audited, Base):
    """§3.4 comment or dispute on a card."""

    __tablename__ = "sc_remarks"

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sc_cards.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    target_code: Mapped[str | None] = mapped_column(String(20))
    kind: Mapped[ScRemarkKind] = enum_col(ScRemarkKind)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_code: Mapped[ScDisputeReason | None] = enum_col(ScDisputeReason, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    file_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    warnings: Mapped[list[str]] = mapped_column(STRS, default=list)
    raised_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[ScResolution | None] = enum_col(ScResolution, nullable=True)
    resolution_text: Mapped[str | None] = mapped_column(Text)
    corrected_record_ref: Mapped[str | None] = mapped_column(String(80))
    old_points: Mapped[Decimal | None] = mapped_column(EXACT)
    new_points: Mapped[Decimal | None] = mapped_column(EXACT)
    old_score: Mapped[Decimal | None] = mapped_column(EXACT)
    new_score: Mapped[Decimal | None] = mapped_column(EXACT)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScRemarkStatus] = enum_col(ScRemarkStatus, default=ScRemarkStatus.open)


class ScWatchEntry(Numbered, Audited, Base):
    """§3.5 watch-list entry."""

    __tablename__ = "sc_watch_entries"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    entry_no: Mapped[str] = mapped_column(String(40))
    level: Mapped[ScWatchLevel] = enum_col(ScWatchLevel, default=ScWatchLevel.watch)
    trigger_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    baseline_score: Mapped[Decimal | None] = mapped_column(EXACT)
    opened_month: Mapped[date] = mapped_column(Date)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opened_reason: Mapped[str | None] = mapped_column(String(500))
    proposal: Mapped[ScWatchProposal | None] = enum_col(ScWatchProposal, nullable=True)
    proposal_reason: Mapped[str | None] = mapped_column(String(300))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_ca_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("corrective_actions.id"))
    pip_ca_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    pip_due_on: Mapped[date | None] = mapped_column(Date)
    pip_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pip_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[ScWatchDecision | None] = enum_col(ScWatchDecision, nullable=True)
    decision_text: Mapped[str | None] = mapped_column(String(1000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contractor_status_ref: Mapped[str | None] = mapped_column(String(80))
    closed_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScWatchStatus] = enum_col(ScWatchStatus, default=ScWatchStatus.open)


class RpPack(Audited, Base):
    """§3.6 report pack revision."""

    __tablename__ = "rp_packs"
    __table_args__ = (
        UniqueConstraint("doc_no", "revision"),
        Index("ix_rp_pack_project_type", "project_id", "report_type"),
    )

    report_type: Mapped[RpType] = enum_col(RpType)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contractors.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    doc_no: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    files: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    with_names: Mapped[bool] = mapped_column(Boolean, default=False)
    scorecards_provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    provisional_reason: Mapped[str | None] = mapped_column(String(500))
    prepared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(String(500))
    reissue_reason: Mapped[str | None] = mapped_column(String(500))
    due_on: Mapped[date | None] = mapped_column(Date)
    revised_since_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by_revision: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[RpStatus] = enum_col(RpStatus, default=RpStatus.draft)


class RpRecipient(UUIDPk, Base):
    """§3.7 distribution-list member (per project × report type)."""

    __tablename__ = "rp_recipients"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    report_type: Mapped[RpType] = enum_col(RpType)
    kind: Mapped[RpMemberKind] = enum_col(RpMemberKind)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    display_name_en: Mapped[str | None] = mapped_column(String(120))
    display_name_ar: Mapped[str | None] = mapped_column(String(120))
    organisation: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    language: Mapped[RpLanguage] = enum_col(RpLanguage, default=RpLanguage.both)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RpDelivery(UUIDPk, Base):
    """§3.7 one send of a pack revision to one member."""

    __tablename__ = "rp_deliveries"

    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_packs.id"), index=True)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rp_recipients.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str | None] = mapped_column(String(254))
    channel: Mapped[RpChannel] = enum_col(RpChannel)
    attachments: Mapped[list[str]] = mapped_column(JSONB, default=list)
    subject: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[RpDeliveryStatus] = enum_col(RpDeliveryStatus, default=RpDeliveryStatus.sent)
    error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class XpJob(UUIDPk, Base):
    """§3.8 export job (also the subject of the `export` audit row)."""

    __tablename__ = "xp_jobs"
    __table_args__ = (UniqueConstraint("year", "seq"),)

    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    export_no: Mapped[str] = mapped_column(String(20))
    dataset: Mapped[str] = mapped_column(String(40))
    format: Mapped[XpFormat] = enum_col(XpFormat)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    columns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    purpose: Mapped[XpPurpose | None] = enum_col(XpPurpose, nullable=True)
    purpose_text: Mapped[str | None] = mapped_column(String(500))
    row_count: Mapped[int | None] = mapped_column(Integer)
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    sha256: Mapped[str | None] = mapped_column(String(64))
    contains_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    contains_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[XpJobStatus] = enum_col(XpJobStatus, default=XpJobStatus.queued)
    error: Mapped[str | None] = mapped_column(String(300))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("xp_subscriptions.id")
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class XpSubscription(UUIDPk, Base):
    """§3.8 subscription (no personal or sensitive column, SUBSCRIPTION_PERSONAL_DATA)."""

    __tablename__ = "xp_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    dataset: Mapped[str] = mapped_column(String(40))
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    columns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    format: Mapped[XpFormat] = enum_col(XpFormat)
    frequency: Mapped[XpFrequency] = enum_col(XpFrequency)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
