"""Phase 8 Quality, package Q0 tables (spec 8-quality Part A, §3.3): settings and the sector
profile, positions and the responsible-person matrix, numbering, the criteria library, the shared
registers (systems, suppliers, customers, M&TE, links, sign-offs), NCRs with their disposition
lines, costs and root-cause analysis, quality observations, quality alerts and customer
complaints. The 6d `checklist_templates` columns `quality_type` / `sector_profiles` live on the
6d model (`app.models.field`).

Cross-part references go through `q_links` or a `(record_type, record_id)` pair, never a foreign
key to another part's table (§3.4)."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.quality.common import (
    QAccreditationBody,
    QAccreditationStandard,
    QActiveStatus,
    QAlertSeverity,
    QAlertStatus,
    QAssigneeKind,
    QCalStatus,
    QCauseCategory,
    QComplaintChannel,
    QComplaintSeverity,
    QComplaintStatus,
    QCostType,
    QCriterionKind,
    QCriterionStatus,
    QCustomerKind,
    QCustomerStatus,
    QDetectionStage,
    QDiscipline,
    QDisposition,
    QJustified,
    QLinkKind,
    QMteCheckKind,
    QMteOwnerKind,
    QMteStatus,
    QMteType,
    QMteUseVerdict,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QNumberReset,
    QObservationStatus,
    QProfileScope,
    QRcaMethod,
    QSatisfaction,
    QSectorProfile,
    QSignoffChannel,
    QSupplierStatus,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col

MONEY = Numeric(14, 2)
QTY = Numeric(14, 3)


class QSettings(Base):
    """§A.3 one row per project. `values` is merged over the registry defaults on read."""

    __tablename__ = "q_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    sector_profile: Mapped[QSectorProfile | None] = enum_col(QSectorProfile, nullable=True)
    quality_start_date: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    profile_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defaults_seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class QPosition(Audited, Base):
    """§A.4.1 project title that is not a platform role (e.g. Consultant Resident Engineer)."""

    __tablename__ = "q_positions"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.both)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QPositionHolder(Audited, Base):
    """§A.4.1 holder of a position (holders may overlap: a deputy is a second holder)."""

    __tablename__ = "q_position_holders"

    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_positions.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class QRpRule(Audited, Base):
    """§A.4.3 responsible-person matrix row. A row with `record_id` is the re-assignment of one
    pending step on one record (Q-RPM-09), the most specific row there is (Q-RPM-02)."""

    __tablename__ = "q_rp_rules"
    __table_args__ = (Index("ix_q_rp_rules_lookup", "project_id", "record_type", "step"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    record_type: Mapped[str] = mapped_column(String(40))
    step: Mapped[str] = mapped_column(String(40))
    qualifier: Mapped[str | None] = mapped_column(String(40))
    record_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    assignee_kind: Mapped[QAssigneeKind] = enum_col(QAssigneeKind)
    assignee: Mapped[str] = mapped_column(String(64))
    self_approval_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    own_tree_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(String(500))


class QNumbering(Base):
    """Q-NUM-01 format per project and record type; `counters` holds the last sequence per
    counter key (`<year or all>|<discipline>|<prefix>`), locked FOR UPDATE on assignment."""

    __tablename__ = "q_numbering"
    __table_args__ = (UniqueConstraint("project_id", "record_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    record_type: Mapped[str] = mapped_column(String(40))
    format: Mapped[str] = mapped_column(String(60))
    reset: Mapped[QNumberReset] = enum_col(QNumberReset, default=QNumberReset.yearly)
    counters: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class QCriterion(Audited, Base):
    """§A.6 one version of an acceptance criterion (org-wide; `project_ids` narrows it)."""

    __tablename__ = "q_criteria"
    __table_args__ = (UniqueConstraint("code", "version"),)

    code: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.both)
    kind: Mapped[QCriterionKind] = enum_col(QCriterionKind)
    unit: Mapped[str | None] = mapped_column(String(20))
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    tol_minus: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    tol_plus: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    rule_code: Mapped[str | None] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reference: Mapped[str | None] = mapped_column(String(120))
    note_en: Mapped[str | None] = mapped_column(String(1000))
    note_ar: Mapped[str | None] = mapped_column(String(1000))
    project_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[QCriterionStatus] = enum_col(QCriterionStatus, default=QCriterionStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class QSystem(Audited, Base):
    """§A.8.1 system (construction register used by Q1 and Q2)."""

    __tablename__ = "q_systems"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    discipline: Mapped[QDiscipline] = enum_col(QDiscipline)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[QActiveStatus] = enum_col(QActiveStatus, default=QActiveStatus.active)


class QSupplier(Audited, Base):
    """§A.8.2 org-wide supplier master (like contractors)."""

    __tablename__ = "q_suppliers"

    supplier_code: Mapped[str] = mapped_column(String(12), unique=True)
    legal_name_en: Mapped[str] = mapped_column(String(200))
    legal_name_ar: Mapped[str] = mapped_column(String(200))
    legal_name_en_norm: Mapped[str] = mapped_column(String(200), unique=True)
    legal_name_ar_norm: Mapped[str] = mapped_column(String(200), unique=True)
    cr_number: Mapped[str | None] = mapped_column(String(10))
    vat_number: Mapped[str | None] = mapped_column(String(15))
    country: Mapped[str] = mapped_column(String(2), default="SA")
    categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contractors.id"))
    tpi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tpis.id"))
    scope_en: Mapped[str | None] = mapped_column(String(500))
    scope_ar: Mapped[str | None] = mapped_column(String(500))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_mobile: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[QSupplierStatus] = enum_col(QSupplierStatus, default=QSupplierStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_scope: Mapped[str | None] = mapped_column(String(1000))
    next_evaluation_due: Mapped[date | None] = mapped_column(Date)
    search_text: Mapped[str] = mapped_column(Text, default="")


class QSupplierAccreditation(Audited, Base):
    """§A.8.2 accreditation of a supplier (labs: Q-SHR-03)."""

    __tablename__ = "q_supplier_accreditations"

    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_suppliers.id"), index=True)
    body: Mapped[QAccreditationBody] = enum_col(QAccreditationBody)
    standard: Mapped[QAccreditationStandard] = enum_col(QAccreditationStandard)
    number: Mapped[str] = mapped_column(String(60))
    scope_text: Mapped[str | None] = mapped_column(String(1000))
    scope_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)


class QCustomer(Audited, Base):
    """§A.8.3 customer of a project (client, depositor, consignee, end user)."""

    __tablename__ = "q_customers"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(12))
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str] = mapped_column(String(200))
    kind: Mapped[QCustomerKind] = enum_col(QCustomerKind)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_mobile: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    owner_release_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[QCustomerStatus] = enum_col(QCustomerStatus, default=QCustomerStatus.active)


class QMteItem(Audited, Base):
    """§A.8.4 M&TE register. `cal_status`, `cal_due_on` and `last_calibration_id` are written
    by Q2 (Q-CAL-01/-02); until Q2 is installed `cal_status` stays `unknown`."""

    __tablename__ = "q_mte_items"
    __table_args__ = (
        UniqueConstraint("project_id", "mte_no"),
        Index(
            "uq_q_mte_items_serial",
            "project_id",
            "manufacturer",
            "serial_no",
            unique=True,
            postgresql_where=text("serial_no IS NOT NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    mte_no: Mapped[str] = mapped_column(String(40))
    mte_type: Mapped[QMteType] = enum_col(QMteType)
    description: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_no: Mapped[str | None] = mapped_column(String(80))
    range_text: Mapped[str | None] = mapped_column(String(80))
    resolution: Mapped[str | None] = mapped_column(String(40))
    tolerance_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    tolerance_unit: Mapped[str | None] = mapped_column(String(20))
    owner_kind: Mapped[QMteOwnerKind] = enum_col(QMteOwnerKind, default=QMteOwnerKind.own)
    owner_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    owner_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    custodian_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    check_kind: Mapped[QMteCheckKind] = enum_col(QMteCheckKind, default=QMteCheckKind.calibration)
    interval_months: Mapped[int | None] = mapped_column(Integer)
    cal_status: Mapped[QCalStatus] = enum_col(QCalStatus, default=QCalStatus.unknown)
    cal_status_reason: Mapped[str | None] = mapped_column(String(500))
    cal_due_on: Mapped[date | None] = mapped_column(Date)
    last_calibration_id: Mapped[uuid.UUID | None] = mapped_column()
    equipment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("equipment_items.id"))
    status: Mapped[QMteStatus] = enum_col(QMteStatus, default=QMteStatus.active)
    label_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QMteUsage(Base):
    """Q-SHR-04 one measurement made with an instrument (written by every part)."""

    __tablename__ = "q_mte_usage"
    __table_args__ = (Index("ix_q_mte_usage_mte_used", "mte_id", "used_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_mte_items.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    record_type: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[uuid.UUID] = mapped_column()
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verdict: Mapped[QMteUseVerdict] = enum_col(QMteUseVerdict)
    cal_status_at_use: Mapped[QCalStatus] = enum_col(QCalStatus)
    value_note: Mapped[str | None] = mapped_column(String(200))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QLink(Base):
    """§A.8.5 link between two Quality records (no foreign keys, never cascaded)."""

    __tablename__ = "q_links"
    __table_args__ = (
        Index("ix_q_links_from", "from_type", "from_id"),
        Index("ix_q_links_to", "to_type", "to_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    from_type: Mapped[str] = mapped_column(String(40))
    from_id: Mapped[uuid.UUID] = mapped_column()
    to_type: Mapped[str] = mapped_column(String(40))
    to_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[QLinkKind] = enum_col(QLinkKind)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QSignoff(Base):
    """Q-RPM-05 one responsible-person action. Append-only (no update or delete route)."""

    __tablename__ = "q_signoffs"
    __table_args__ = (Index("ix_q_signoffs_record", "record_type", "record_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    record_type: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[uuid.UUID] = mapped_column()
    step: Mapped[str] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(String(2000))
    signed_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signer_capacity: Mapped[str] = mapped_column(String(120))  # role or position at signing
    channel: Mapped[QSignoffChannel] = enum_col(QSignoffChannel, default=QSignoffChannel.in_app)
    external_name: Mapped[str | None] = mapped_column(String(120))
    external_organisation: Mapped[str | None] = mapped_column(String(150))
    external_position: Mapped[str | None] = mapped_column(String(120))
    external_signed_on: Mapped[date | None] = mapped_column(Date)
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_rp_rules.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QNcr(Audited, Base):
    """§A.9.1 Nonconformance Report. Numbered when it leaves Draft (Q-NUM-03)."""

    __tablename__ = "q_ncrs"
    __table_args__ = (
        UniqueConstraint("project_id", "ncr_no"),
        Index("ix_q_ncrs_project_status", "project_id", "status"),
        Index("ix_q_ncrs_repeat_key", "project_id", "category", "item_key"),
        Index("ix_q_ncrs_source", "source_type", "source_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ncr_no: Mapped[str | None] = mapped_column(String(40))
    profile: Mapped[QSectorProfile] = enum_col(QSectorProfile)
    source_type: Mapped[QNcrSourceType] = enum_col(QNcrSourceType, default=QNcrSourceType.manual)
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    source_ref: Mapped[str | None] = mapped_column(String(60))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    location_ref: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(150))
    requirement_en: Mapped[str | None] = mapped_column(String(1000))
    requirement_ar: Mapped[str | None] = mapped_column(String(1000))
    finding_en: Mapped[str | None] = mapped_column(String(2000))
    finding_ar: Mapped[str | None] = mapped_column(String(2000))
    category: Mapped[QNcrCategory | None] = enum_col(QNcrCategory, nullable=True)
    detection_stage: Mapped[QDetectionStage | None] = enum_col(QDetectionStage, nullable=True)
    classification: Mapped[QNcrClass | None] = enum_col(QNcrClass, nullable=True)
    responsible_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    item_key: Mapped[str | None] = mapped_column(String(80))
    quantity: Mapped[Decimal | None] = mapped_column(QTY)
    unit: Mapped[str | None] = mapped_column(String(10))
    lot_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    containment_en: Mapped[str | None] = mapped_column(String(1000))
    containment_ar: Mapped[str | None] = mapped_column(String(1000))
    containment_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    containment_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    no_product_affected: Mapped[bool] = mapped_column(Boolean, default=False)
    cause_category: Mapped[QCauseCategory | None] = enum_col(QCauseCategory, nullable=True)
    disposition_justification_en: Mapped[str | None] = mapped_column(String(2000))
    disposition_justification_ar: Mapped[str | None] = mapped_column(String(2000))
    disposition_proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposition_proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id")
    )
    disposition_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    implementation_note: Mapped[str | None] = mapped_column(String(1000))
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    implemented_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    supplier_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    repeat_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    target_close_date: Mapped[date | None] = mapped_column(Date)
    containment_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_date: Mapped[date | None] = mapped_column(Date)
    reopened_count: Mapped[int] = mapped_column(Integer, default=0)
    effectiveness: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    no_cost_reason: Mapped[str | None] = mapped_column(String(500))
    cost_gross_sar: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    cost_recovered_sar: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    status: Mapped[QNcrStatus] = enum_col(QNcrStatus, default=QNcrStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(2000))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    before_quality_start: Mapped[bool] = mapped_column(Boolean, default=False)
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QNcrLine(Audited, Base):
    """Q-NCR-11 disposition line."""

    __tablename__ = "q_ncr_lines"

    ncr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_ncrs.id"), index=True)
    disposition: Mapped[QDisposition] = enum_col(QDisposition)
    quantity: Mapped[Decimal | None] = mapped_column(QTY)
    note: Mapped[str | None] = mapped_column(String(1000))
    repair_procedure: Mapped[str | None] = mapped_column(String(300))
    return_ref: Mapped[str | None] = mapped_column(String(80))
    destruction_evidenced: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class QNcrCost(Audited, Base):
    """§A.9.6 cost line (rates in use are stored on the line, Q-COST-03)."""

    __tablename__ = "q_ncr_costs"

    ncr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_ncrs.id"), index=True)
    cost_type: Mapped[QCostType] = enum_col(QCostType)
    description: Mapped[str | None] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str | None] = mapped_column(String(10))
    rate_sar: Mapped[Decimal] = mapped_column(MONEY)
    amount_sar: Mapped[Decimal] = mapped_column(MONEY)
    recoverable: Mapped[bool] = mapped_column(Boolean, default=False)
    recovered_sar: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    entered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QNcrRca(Audited, Base):
    """Q-NCR-09 root-cause analysis of an NCR (method-specific `data`)."""

    __tablename__ = "q_ncr_rca"

    ncr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_ncrs.id"), unique=True)
    method: Mapped[QRcaMethod] = enum_col(QRcaMethod)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    root_cause: Mapped[str | None] = mapped_column(String(2000))
    cause_category: Mapped[QCauseCategory | None] = enum_col(QCauseCategory, nullable=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)


class QObservation(Audited, Base):
    """§A.10.1 quality observation (kept apart from the Phase 1 safety observations)."""

    __tablename__ = "q_observations"
    __table_args__ = (UniqueConstraint("project_id", "obs_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    obs_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    location_ref: Mapped[str | None] = mapped_column(String(120))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    category: Mapped[QNcrCategory] = enum_col(QNcrCategory)
    description: Mapped[str] = mapped_column(String(2000))
    suggested_action: Mapped[str | None] = mapped_column(String(1000))
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raised_date: Mapped[date] = mapped_column(Date)
    status: Mapped[QObservationStatus] = enum_col(
        QObservationStatus, default=QObservationStatus.open
    )
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))


class QAlert(Audited, Base):
    """§A.10.2 quality alert."""

    __tablename__ = "q_alerts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    alert_no: Mapped[str | None] = mapped_column(String(40))
    title_en: Mapped[str] = mapped_column(String(200))
    title_ar: Mapped[str] = mapped_column(String(200))
    message_en: Mapped[str] = mapped_column(String(2000))
    message_ar: Mapped[str] = mapped_column(String(2000))
    severity: Mapped[QAlertSeverity] = enum_col(QAlertSeverity)
    applies_to: Mapped[str | None] = mapped_column(String(1000))
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    supplier_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    lot_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    valid_until: Mapped[date | None] = mapped_column(Date)
    dist_roles: Mapped[list[str]] = mapped_column(STRS, default=list)
    dist_positions: Mapped[list[str]] = mapped_column(STRS, default=list)
    dist_engagement_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    dist_user_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    recipients: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    ack_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[QAlertStatus] = enum_col(QAlertStatus, default=QAlertStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QAlertAck(Base):
    """Q-OBS-04 one acknowledgement per member (idempotent)."""

    __tablename__ = "q_alert_acks"
    __table_args__ = (UniqueConstraint("alert_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_alerts.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    acked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QComplaint(Audited, Base):
    """§A.10.3 customer complaint."""

    __tablename__ = "q_complaints"
    __table_args__ = (UniqueConstraint("project_id", "complaint_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    complaint_no: Mapped[str] = mapped_column(String(40))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_customers.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[QComplaintChannel] = enum_col(QComplaintChannel)
    customer_reference: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[QNcrCategory] = enum_col(QNcrCategory)
    description: Mapped[str] = mapped_column(String(2000))
    product_refs: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[QComplaintSeverity] = enum_col(QComplaintSeverity)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_method: Mapped[str | None] = mapped_column(String(40))
    investigation_note: Mapped[str | None] = mapped_column(String(2000))
    justified: Mapped[QJustified | None] = enum_col(QJustified, nullable=True)
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    response_en: Mapped[str | None] = mapped_column(String(2000))
    response_ar: Mapped[str | None] = mapped_column(String(2000))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    satisfied: Mapped[QSatisfaction | None] = enum_col(QSatisfaction, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QComplaintStatus] = enum_col(QComplaintStatus, default=QComplaintStatus.received)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


__all__ = [
    "QAlert",
    "QAlertAck",
    "QComplaint",
    "QCriterion",
    "QCustomer",
    "QLink",
    "QMteItem",
    "QMteUsage",
    "QNcr",
    "QNcrCost",
    "QNcrLine",
    "QNcrRca",
    "QNumbering",
    "QObservation",
    "QPosition",
    "QPositionHolder",
    "QRpRule",
    "QSettings",
    "QSignoff",
    "QSupplier",
    "QSupplierAccreditation",
    "QSystem",
]
