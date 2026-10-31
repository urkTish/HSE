"""Tables of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Part B, §3.3): `q_itps`, `q_itp_points`, `q_irs`, `q_ir_rounds`, `q_ir_comments`,
`q_floor_plans`, `q_punch_items`, `q_dossiers`, `q_asbuilt_items`.

Foreign keys point only to Q1's own tables, Q0's shared tables and earlier phases; records of other
wave-2 parts (MIR, test requests, pours, documents) are reached through `q_links` or a
`(record_type, record_id)` pair (§3.4)."""

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.quality.common import QDiscipline, QNcrCategory
from app.core.quality.q1 import (
    QApprovalCode,
    QAsbuiltStatus,
    QDossierStatus,
    QIrCommentStatus,
    QIrResult,
    QIrStatus,
    QItpStatus,
    QPlanStatus,
    QPointType,
    QPunchCategory,
    QPunchRaisedDuring,
    QPunchStatus,
    QVerifyingRecord,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col

INTS = ARRAY(Integer)

__all__ = [
    "QAsbuiltItem",
    "QDossier",
    "QFloorPlan",
    "QIr",
    "QIrComment",
    "QIrRound",
    "QItp",
    "QItpPoint",
    "QPunchItem",
]


class QItp(Audited, Base):
    """§B.3.1 one revision of an Inspection and Test Plan. Revisions of one plan share
    `family_id` and, once numbered, `itp_no` (the revision is shown as `… Rev.n`, Q-NUM-04)."""

    __tablename__ = "q_itps"
    __table_args__ = (
        UniqueConstraint("family_id", "revision"),
        Index("ix_q_itps_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    itp_no: Mapped[str | None] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    title_en: Mapped[str] = mapped_column(String(150), default="")
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    discipline: Mapped[QDiscipline] = enum_col(QDiscipline)
    work_package_en: Mapped[str | None] = mapped_column(String(150))
    work_package_ar: Mapped[str | None] = mapped_column(String(150))
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    system_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    spec_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    code_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    method_statement_ref: Mapped[str | None] = mapped_column(String(120))
    change_note: Mapped[str | None] = mapped_column(String(500))
    approval_code: Mapped[QApprovalCode | None] = enum_col(QApprovalCode, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(String(2000))
    prepared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QItpStatus] = enum_col(QItpStatus, default=QItpStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(2000))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QItpPoint(Audited, Base):
    """§B.3.1 one point of one ITP revision. Point identity across revisions is `seq`
    (Q-ITP-05)."""

    __tablename__ = "q_itp_points"
    __table_args__ = (UniqueConstraint("itp_id", "seq"),)

    itp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_itps.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    activity_en: Mapped[str] = mapped_column(String(200), default="")
    activity_ar: Mapped[str] = mapped_column(String(200), default="")
    characteristic_en: Mapped[str] = mapped_column(String(300), default="")
    characteristic_ar: Mapped[str] = mapped_column(String(300), default="")
    point_type: Mapped[QPointType] = enum_col(QPointType)
    criteria_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    acceptance_text_en: Mapped[str | None] = mapped_column(String(500))
    acceptance_text_ar: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(120))
    verifying_record: Mapped[QVerifyingRecord] = enum_col(
        QVerifyingRecord, default=QVerifyingRecord.ir
    )
    checklist_template_code: Mapped[str | None] = mapped_column(String(8))
    test_type_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    frequency_text: Mapped[str | None] = mapped_column(String(120))
    frequency_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    frequency_unit: Mapped[str | None] = mapped_column(String(20))
    # Q-RPM-02 point override {assignee_kind, assignee}; copied as a record row at IR submit
    rp_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notice_hours: Mapped[int | None] = mapped_column(Integer)
    competence_code: Mapped[str | None] = mapped_column(String(40))


class QIr(Audited, Base):
    """§B.4.1 Inspection Request. Numbered at submit (Q-NUM-03); pins the ITP revision current at
    submission (Q-ITP-04)."""

    __tablename__ = "q_irs"
    __table_args__ = (
        UniqueConstraint("project_id", "ir_no"),
        Index("ix_q_irs_project_status", "project_id", "status"),
        Index("ix_q_irs_hold", "itp_family_id", "location_key"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ir_no: Mapped[str | None] = mapped_column(String(40))
    itp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_itps.id"), index=True)
    itp_family_id: Mapped[uuid.UUID] = mapped_column()
    itp_revision: Mapped[int] = mapped_column(Integer)
    point_seqs: Mapped[list[int]] = mapped_column(INTS, default=list)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    governing_type: Mapped[QPointType] = enum_col(QPointType)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    location_ref: Mapped[str] = mapped_column(String(120))
    location_key: Mapped[str] = mapped_column(String(160))
    extent: Mapped[str | None] = mapped_column(String(150))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    self_check_done: Mapped[bool] = mapped_column(Boolean, default=False)
    self_check_note: Mapped[str | None] = mapped_column(String(500))
    self_check_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checklist_responses.id")
    )
    responsible_set: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    short_notice: Mapped[bool] = mapped_column(Boolean, default=False)
    short_notice_reason: Mapped[str | None] = mapped_column(String(1000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_date: Mapped[date | None] = mapped_column(Date)
    reblocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QIrStatus] = enum_col(QIrStatus, default=QIrStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(2000))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QIrRound(Audited, Base):
    """§B.4.1 one inspection round. `responses` maps an ITP point seq to its 6d checklist response
    (owner type `q_ir_round`); photos are `q_ir_round` attachments of the round."""

    __tablename__ = "q_ir_rounds"
    __table_args__ = (UniqueConstraint("ir_id", "round_no"),)

    ir_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_irs.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    round_no: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reschedules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_date: Mapped[date | None] = mapped_column(Date)
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    responses: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    measurements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    result: Mapped[QIrResult | None] = enum_col(QIrResult, nullable=True)
    review_result: Mapped[QIrResult | None] = enum_col(QIrResult, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_category: Mapped[QNcrCategory | None] = enum_col(QNcrCategory, nullable=True)
    comment: Mapped[str | None] = mapped_column(String(2000))
    signoff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_signoffs.id"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    waived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_comments_before_next_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_note: Mapped[str | None] = mapped_column(String(1000))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Q-IR-14: an offline round whose hold or M&TE check failed at sync waits for confirmation
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recorded_offline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class QIrComment(Audited, Base):
    """§B.4.1 a comment of an approved-with-comments round (Q-IR-11)."""

    __tablename__ = "q_ir_comments"

    ir_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_irs.id"), index=True)
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_ir_rounds.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    text_en: Mapped[str | None] = mapped_column(String(1000))
    text_ar: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[QIrCommentStatus] = enum_col(QIrCommentStatus, default=QIrCommentStatus.open)
    due_on: Mapped[date | None] = mapped_column(Date)
    response_text: Mapped[str | None] = mapped_column(String(1000))
    responded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_comment: Mapped[str | None] = mapped_column(String(1000))


class QFloorPlan(Audited, Base):
    """§B.6 a plan image of a zone and level; revisions share `family_id`."""

    __tablename__ = "q_floor_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    level_label: Mapped[str] = mapped_column(String(60))
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150))
    revision: Mapped[str] = mapped_column(String(20), default="0")
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    status: Mapped[QPlanStatus] = enum_col(QPlanStatus, default=QPlanStatus.current)


class QPunchItem(Audited, Base):
    """§B.5 punch item (numbered at raise; there is no draft)."""

    __tablename__ = "q_punch_items"
    __table_args__ = (
        UniqueConstraint("project_id", "punch_no"),
        Index("ix_q_punch_items_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    punch_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    location_ref: Mapped[str] = mapped_column(String(120))
    discipline: Mapped[QDiscipline] = enum_col(QDiscipline)
    description_en: Mapped[str | None] = mapped_column(String(500))
    description_ar: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[QPunchCategory] = enum_col(QPunchCategory)
    raised_during: Mapped[QPunchRaisedDuring] = enum_col(QPunchRaisedDuring)
    responsible_engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raised_date: Mapped[date] = mapped_column(Date)
    target_date: Mapped[date] = mapped_column(Date)
    photo_before_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    photo_after_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    floor_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_floor_plans.id"))
    pin_x_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pin_y_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pin_check: Mapped[bool] = mapped_column(Boolean, default=False)
    walkdown_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checklist_responses.id")
    )
    ready_note: Mapped[str | None] = mapped_column(String(1000))
    ready_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_date: Mapped[date | None] = mapped_column(Date)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QPunchStatus] = enum_col(QPunchStatus, default=QPunchStatus.open)
    status_reason: Mapped[str | None] = mapped_column(String(2000))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QDossier(Audited, Base):
    """§B.7 handover dossier; a revision after acceptance shares `family_id` and the number."""

    __tablename__ = "q_dossiers"
    __table_args__ = (UniqueConstraint("family_id", "revision"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    dossier_no: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    system_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    sections: Mapped[list[str]] = mapped_column(STRS, default=list)
    compiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compiled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    index_en_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    index_ar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    package_sha256: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[QDossierStatus] = enum_col(QDossierStatus, default=QDossierStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(2000))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QAsbuiltItem(Audited, Base):
    """§B.7 one as-built drawing of a dossier."""

    __tablename__ = "q_asbuilt_items"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_dossiers.id"), index=True)
    drawing_no: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    revision: Mapped[str] = mapped_column(String(20))
    drawing_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[QAsbuiltStatus] = enum_col(QAsbuiltStatus, default=QAsbuiltStatus.submitted)
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
