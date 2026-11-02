"""Tables of package Q4: document control, transmittals, processes and the quality audit
programme, management reviews, supplier evaluations and scores, KPI targets, SPC charts and the
monthly work value behind COPQ % (spec 8-quality Part E, §3.3 Q4 row). Quality audits themselves
are 6d `field_audits` rows with `domain = quality` (columns added there, §E.2.1)."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.quality.common import QProfileScope
from app.core.quality.q4 import (
    QDocType,
    QMrvStatus,
    QProgrammeStatus,
    QProgrammeSubject,
    QResponseCode,
    QRevStatus,
    QRisk,
    QScorePeriod,
    QScoreStatus,
    QSevKind,
    QSevMethod,
    QSevRecommendation,
    QSevStatus,
    QSpcBaseline,
    QSpcSource,
    QSpcType,
    QTransmittalItemKind,
    QTransmittalMethod,
    QTransmittalPurpose,
    QTransmittalStatus,
    QTransmittalTo,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col

MONEY = Numeric(16, 2)
SCORE = Numeric(6, 2)

__all__ = [
    "QAuditProgrammeLine",
    "QDocAck",
    "QDocDistribution",
    "QDocument",
    "QDocumentRevision",
    "QKpiTarget",
    "QManagementReview",
    "QProcess",
    "QSpcChart",
    "QSupplierEvaluation",
    "QSupplierScore",
    "QTransmittal",
    "QTransmittalItem",
    "QWorkValue",
]


# ---- documents (§E.1.2) -------------------------------------------------------------------------


class QDocument(Audited, Base):
    """A controlled document; its status is the current revision's (sys)."""

    __tablename__ = "q_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "doc_no"),
        Index("ix_q_documents_project_type", "project_id", "doc_type"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    doc_no: Mapped[str] = mapped_column(String(60))
    doc_type: Mapped[QDocType] = enum_col(QDocType)
    title_en: Mapped[str] = mapped_column(String(200))
    title_ar: Mapped[str] = mapped_column(String(200), default="")
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.both)
    discipline: Mapped[str | None] = mapped_column(String(40))
    process_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_processes.id"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column()  # latest approved
    review_due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[QRevStatus] = enum_col(QRevStatus, default=QRevStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QDocumentRevision(Audited, Base):
    """§E.1.2 revision with its workflow (draft → for review → approved → superseded)."""

    __tablename__ = "q_document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "rev_code"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_documents.id"), index=True)
    rev_code: Mapped[str] = mapped_column(String(8))
    rev_index: Mapped[int] = mapped_column(Integer)  # creation order
    status: Mapped[QRevStatus] = enum_col(QRevStatus, default=QRevStatus.draft)
    file_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    source_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    change_summary: Mapped[str | None] = mapped_column(String(2000))
    effective_date: Mapped[date | None] = mapped_column(Date)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_date: Mapped[date | None] = mapped_column(Date)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_comment: Mapped[str | None] = mapped_column(String(2000))
    ack_due_on: Mapped[date | None] = mapped_column(Date)


class QDocDistribution(Audited, Base):
    """§E.1.2 distribution of a document: roles, positions, engagements, users."""

    __tablename__ = "q_doc_distribution"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_documents.id"), unique=True)
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    positions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    engagement_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    user_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    ack_required: Mapped[bool] = mapped_column(Boolean, default=False)


class QDocAck(Base):
    """Read-and-acknowledge task of one member for one revision (Q-DOC-05); `acked_at` set on
    acknowledgement."""

    __tablename__ = "q_doc_acks"
    __table_args__ = (UniqueConstraint("revision_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_document_revisions.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    due_on: Mapped[date] = mapped_column(Date)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)


class QTransmittal(Audited, Base):
    """Q-DOC-07 transmittal with its cover sheet."""

    __tablename__ = "q_transmittals"
    __table_args__ = (Index("ix_q_transmittals_project", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    trm_no: Mapped[str | None] = mapped_column(String(40))
    to_kind: Mapped[QTransmittalTo] = enum_col(QTransmittalTo)
    to_engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    to_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    to_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    to_name: Mapped[str | None] = mapped_column(String(200))
    to_email: Mapped[str | None] = mapped_column(String(200))
    purpose: Mapped[QTransmittalPurpose] = enum_col(QTransmittalPurpose)
    method: Mapped[QTransmittalMethod] = enum_col(QTransmittalMethod)
    subject: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(2000))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_due_on: Mapped[date | None] = mapped_column(Date)
    response_received_on: Mapped[date | None] = mapped_column(Date)
    response_name: Mapped[str | None] = mapped_column(String(200))
    cover_en_id: Mapped[uuid.UUID | None] = mapped_column()
    cover_ar_id: Mapped[uuid.UUID | None] = mapped_column()
    outbox_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[QTransmittalStatus] = enum_col(
        QTransmittalStatus, default=QTransmittalStatus.draft
    )
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QTransmittalItem(Base):
    __tablename__ = "q_transmittal_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transmittal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_transmittals.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[QTransmittalItemKind] = enum_col(QTransmittalItemKind)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_document_revisions.id"))
    record_type: Mapped[str | None] = mapped_column(String(40))
    record_id: Mapped[uuid.UUID | None] = mapped_column()
    ref: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200), default="")
    response_code: Mapped[QResponseCode | None] = enum_col(QResponseCode, nullable=True)
    response_note: Mapped[str | None] = mapped_column(String(1000))


# ---- processes, programme, management review (§E.2) -------------------------------------------


class QProcess(Audited, Base):
    __tablename__ = "q_processes"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str] = mapped_column(String(20))
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150), default="")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.both)
    risk: Mapped[QRisk] = enum_col(QRisk, default=QRisk.medium)
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QAuditProgrammeLine(Audited, Base):
    """Q-AUD-06 one planned audit of the year's programme."""

    __tablename__ = "q_audit_programme_lines"
    __table_args__ = (Index("ix_q_programme_project_year", "project_id", "year"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    year: Mapped[int] = mapped_column(Integer)
    subject_kind: Mapped[QProgrammeSubject] = enum_col(QProgrammeSubject)
    process_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_processes.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    clause_set: Mapped[str | None] = mapped_column(String(100))
    risk: Mapped[QRisk] = enum_col(QRisk, default=QRisk.medium)
    planned_month: Mapped[int] = mapped_column(Integer)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("field_audits.id"))
    status: Mapped[QProgrammeStatus] = enum_col(QProgrammeStatus, default=QProgrammeStatus.planned)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    auto: Mapped[bool] = mapped_column(Boolean, default=False)  # generated from the risk
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QManagementReview(Audited, Base):
    """§E.2.2 management review with frozen KPI snapshot (Q-MRV-02)."""

    __tablename__ = "q_management_reviews"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    mrv_no: Mapped[str | None] = mapped_column(String(40))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    held_on: Mapped[date | None] = mapped_column(Date)
    chair_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    attendee_user_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    external_attendees: Mapped[list[str]] = mapped_column(JSONB, default=list)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    kpi_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    outputs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    minutes_en_id: Mapped[uuid.UUID | None] = mapped_column()
    minutes_ar_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[QMrvStatus] = enum_col(QMrvStatus, default=QMrvStatus.draft)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---- suppliers (§E.3) ----------------------------------------------------------------------------


class QSupplierEvaluation(Audited, Base):
    __tablename__ = "q_supplier_evaluations"
    __table_args__ = (Index("ix_q_sev_supplier", "supplier_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    sev_no: Mapped[str | None] = mapped_column(String(40))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_suppliers.id"))
    kind: Mapped[QSevKind] = enum_col(QSevKind)
    method: Mapped[QSevMethod] = enum_col(QSevMethod)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("field_audits.id"))
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    total: Mapped[Decimal | None] = mapped_column(SCORE)
    recommendation: Mapped[QSevRecommendation | None] = enum_col(QSevRecommendation, nullable=True)
    conditions: Mapped[str | None] = mapped_column(String(1000))
    evaluated_at: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_date: Mapped[date | None] = mapped_column(Date)
    next_evaluation_due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[QSevStatus] = enum_col(QSevStatus, default=QSevStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))


class QSupplierScore(Base):
    """Q-SUP-03 scorecard of one supplier for one period (org-wide, all projects)."""

    __tablename__ = "q_supplier_scores"
    __table_args__ = (UniqueConstraint("supplier_id", "period_start"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_suppliers.id"))
    period_kind: Mapped[QScorePeriod] = enum_col(QScorePeriod)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))  # 1 dp (Q-SUP-03)
    band: Mapped[str | None] = mapped_column(String(1))
    recommendation: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[QScoreStatus] = enum_col(QScoreStatus, default=QScoreStatus.provisional)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- KPI targets, SPC charts, work value -----------------------------------------------------


class QKpiTarget(Audited, Base):
    """Quality objectives (ISO 9001 6.2): the target in force is the latest valid_from ≤ day."""

    __tablename__ = "q_kpi_targets"
    __table_args__ = (UniqueConstraint("project_id", "kpi_id", "valid_from"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    kpi_id: Mapped[str] = mapped_column(String(8))
    target: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    valid_from: Mapped[date] = mapped_column(Date)


class QSpcChart(Audited, Base):
    __tablename__ = "q_spc_charts"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str] = mapped_column(String(30))
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    chart_type: Mapped[QSpcType] = enum_col(QSpcType)
    source: Mapped[QSpcSource] = enum_col(QSpcSource)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    subgroup_size: Mapped[int | None] = mapped_column(Integer)
    baseline: Mapped[QSpcBaseline] = enum_col(QSpcBaseline, default=QSpcBaseline.rolling)
    baseline_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    lsl: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    usl: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    criterion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_criteria.id"))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    signals_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QWorkValue(Audited, Base):
    """Q-SIX-01 value of work done (or revenue) per project and month (SAR), for COPQ %."""

    __tablename__ = "q_work_value"
    __table_args__ = (UniqueConstraint("project_id", "month"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    month: Mapped[date] = mapped_column(Date)  # first day of the month
    value_sar: Mapped[Decimal] = mapped_column(MONEY)
