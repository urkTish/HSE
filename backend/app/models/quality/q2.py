"""Tables of package Q2 materials, testing and lab, welding, calibration, competence (spec
8-quality Part C, §3.3): MARs, MIRs, quarantine, test types, test requests and specimens, pours,
WPS / PQR / welders / WPQs / weld log, calibrations, out-of-tolerance reviews and items,
competence requirements, and the manual M&TE status override (Q-CAL-02).

Q0 tables (projects, suppliers, M&TE, NCRs, criteria) are the base and may be referenced by
foreign key; records of the other wave-2 parts (Q1 IRs / ITP points, Q3 receipts / monitoring
points) are referenced only by `(record_type, record_id)` or `q_links` (§3.4)."""

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
from app.core.quality.q2 import (
    QAcceptReject,
    QCalKind,
    QCalRecordStatus,
    QCompetencePolicy,
    QCompetenceState,
    QEvaluationMode,
    QJointType,
    QMarStatus,
    QMaterialCategory,
    QMirResult,
    QMirStatus,
    QMteOverride,
    QNdtMethod,
    QNdtSelection,
    QOotStatus,
    QPourStatus,
    QPqrStatus,
    QQuarantineStatus,
    QTestStatus,
    QTestTypeStatus,
    QTestVerdict,
    QWelderStatus,
    QWeldProcess,
    QWeldStandard,
    QWeldStatus,
    QWpqMethod,
    QWpqStatus,
    QWpsStatus,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col

QTY = Numeric(14, 3)
VAL = Numeric(18, 6)

__all__ = [
    "QCalibration",
    "QCompetenceCell",
    "QCompetenceReq",
    "QMar",
    "QMir",
    "QMteCalOverride",
    "QOotItem",
    "QOotReview",
    "QPour",
    "QPqr",
    "QQuarantineItem",
    "QTestRequest",
    "QTestSpecimen",
    "QTestType",
    "QWeld",
    "QWelder",
    "QWpq",
    "QWps",
]


# ---- materials (§C.3) --------------------------------------------------------------------------


class QMar(Audited, Base):
    """§C.3.1 one revision of a Material Approval Request (revisions share `mar_no`)."""

    __tablename__ = "q_mars"
    __table_args__ = (Index("ix_q_mars_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    mar_no: Mapped[str | None] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    root_id: Mapped[uuid.UUID | None] = mapped_column()  # the first revision's id
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    title_en: Mapped[str] = mapped_column(String(200))
    title_ar: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[QMaterialCategory] = enum_col(QMaterialCategory)
    spec_section: Mapped[str | None] = mapped_column(String(60))
    manufacturer: Mapped[str | None] = mapped_column(String(150))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    country_of_origin: Mapped[str | None] = mapped_column(String(60))
    brand_model: Mapped[str | None] = mapped_column(String(150))
    compliance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    deviations_note: Mapped[str | None] = mapped_column(String(2000))
    with_deviations: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_ref: Mapped[str | None] = mapped_column(String(60))
    approval_code: Mapped[str | None] = mapped_column(String(1))
    decision_comment: Mapped[str | None] = mapped_column(String(2000))
    deviations_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QMarStatus] = enum_col(QMarStatus, default=QMarStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QMir(Audited, Base):
    """§C.3.2 Material Inspection Request on delivery."""

    __tablename__ = "q_mirs"
    __table_args__ = (Index("ix_q_mirs_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    mir_no: Mapped[str | None] = mapped_column(String(40))
    mar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mars.id"))
    mar_revision: Mapped[int | None] = mapped_column(Integer)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    category: Mapped[QMaterialCategory] = enum_col(QMaterialCategory)
    material_description: Mapped[str] = mapped_column(String(200))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    delivery_note_no: Mapped[str | None] = mapped_column(String(60))
    po_no: Mapped[str | None] = mapped_column(String(60))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10))
    lot_numbers: Mapped[list[str]] = mapped_column(JSONB, default=list)  # tag heats / lots
    cert_heat_numbers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    storage_zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    # §C.3.2 / §A.7: the delivery checklist (6d response, owner type q_mir, type mir_inspection)
    checklist_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checklist_responses.id")
    )
    accepted_qty: Mapped[Decimal | None] = mapped_column(QTY)
    rejected_qty: Mapped[Decimal | None] = mapped_column(QTY)
    result: Mapped[QMirResult | None] = enum_col(QMirResult, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(String(2000))
    heat_mismatch: Mapped[list[str]] = mapped_column(JSONB, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QMirStatus] = enum_col(QMirStatus, default=QMirStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))


class QQuarantineItem(Audited, Base):
    """§C.3.3 quarantined material (red tag `QTN`)."""

    __tablename__ = "q_quarantine_items"
    __table_args__ = (Index("ix_q_quarantine_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    tag_no: Mapped[str] = mapped_column(String(40))
    material_description: Mapped[str] = mapped_column(String(200))
    mir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mirs.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    location_ref: Mapped[str | None] = mapped_column(String(120))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    quarantined_on: Mapped[date] = mapped_column(Date)
    return_note_no: Mapped[str | None] = mapped_column(String(60))
    disposal_note: Mapped[str | None] = mapped_column(String(1000))
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QQuarantineStatus] = enum_col(
        QQuarantineStatus, default=QQuarantineStatus.quarantined
    )


# ---- testing (§C.2) ------------------------------------------------------------------------------


class QTestType(Audited, Base):
    """§C.2.1 one version of a test type (org-wide; `project_ids` narrows a project version)."""

    __tablename__ = "q_test_types"
    __table_args__ = (UniqueConstraint("code", "version"),)

    code: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150), default="")
    discipline: Mapped[str] = mapped_column(String(10))
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.construction)
    standard_ref: Mapped[str | None] = mapped_column(String(120))
    specimen_plan: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    result_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    evaluation: Mapped[QEvaluationMode] = enum_col(QEvaluationMode, default=QEvaluationMode.fields)
    criterion_code: Mapped[str | None] = mapped_column(String(20))
    field_criteria: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    acceptance_age_days: Mapped[int | None] = mapped_column(Integer)
    ncr_class_on_fail: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    competence_code: Mapped[str | None] = mapped_column(String(20))
    project_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[QTestTypeStatus] = enum_col(QTestTypeStatus, default=QTestTypeStatus.draft)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QPour(Audited, Base):
    """Q-TST-11 concrete pour (construction)."""

    __tablename__ = "q_pours"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    pour_no: Mapped[str] = mapped_column(String(40))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    element: Mapped[str] = mapped_column(String(150))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    location_ref: Mapped[str | None] = mapped_column(String(120))
    mar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mars.id"))
    grade: Mapped[str] = mapped_column(String(20))
    fc_mpa: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    volume_m3: Mapped[Decimal] = mapped_column(QTY)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    planned_on: Mapped[date | None] = mapped_column(Date)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ambient_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    # Q1 records by id only (§3.4): the pre-pour hold IR and its ITP point
    pre_pour_ir_id: Mapped[uuid.UUID | None] = mapped_column()
    itp_point_id: Mapped[uuid.UUID | None] = mapped_column()
    quality_engineer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    mix_key: Mapped[str] = mapped_column(String(80), default="")
    sets_required: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[QPourStatus] = enum_col(QPourStatus, default=QPourStatus.planned)
    status_reason: Mapped[str | None] = mapped_column(String(1000))


class QTestRequest(Audited, Base):
    """§C.2.2 test request; results are versioned (Q-TST-09): `history` keeps every earlier
    version, the row holds the current one."""

    __tablename__ = "q_test_requests"
    __table_args__ = (
        Index("ix_q_test_requests_project_status", "project_id", "status"),
        Index("ix_q_test_requests_mix", "project_id", "mix_key"),
        Index("ix_q_test_requests_verdict", "project_id", "verdict"),
        Index("ix_q_test_requests_pour", "pour_id"),
        Index("ix_q_test_requests_lab", "lab_supplier_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    test_no: Mapped[str] = mapped_column(String(40))
    test_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_test_types.id"))
    test_type_code: Mapped[str] = mapped_column(String(16))
    criterion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_criteria.id"))
    field_criterion_ids: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    location_ref: Mapped[str] = mapped_column(String(120))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    lab_supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_suppliers.id"))
    pour_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_pours.id"))
    mir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mirs.id"))
    retest_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_test_requests.id"))
    mix_key: Mapped[str] = mapped_column(String(80), default="")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sampled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cast_date: Mapped[date | None] = mapped_column(Date)
    sampled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sample_ref: Mapped[str | None] = mapped_column(String(40))
    mte_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    delivered_to_lab_on: Mapped[date | None] = mapped_column(Date)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    report_no: Mapped[str | None] = mapped_column(String(60))
    tested_by_name: Mapped[str | None] = mapped_column(String(120))
    verdict: Mapped[QTestVerdict] = enum_col(QTestVerdict, default=QTestVerdict.pending)
    verdict_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_version: Mapped[int] = mapped_column(Integer, default=0)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    results_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    results_entered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ncr_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[QTestStatus] = enum_col(QTestStatus, default=QTestStatus.requested)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QTestSpecimen(Base):
    """§C.2.2 one specimen of a test request; due_on = cast date + age (Q-TST-03)."""

    __tablename__ = "q_test_specimens"
    __table_args__ = (Index("ix_q_test_specimens_due", "due_on", "tested_on"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    test_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("q_test_requests.id", ondelete="CASCADE"), index=True
    )
    specimen_ref: Mapped[str] = mapped_column(String(40))
    age_days: Mapped[int | None] = mapped_column(Integer)
    due_on: Mapped[date | None] = mapped_column(Date)
    tested_on: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    spare: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- welding (§C.6) ----------------------------------------------------------------------------


class QWps(Audited, Base):
    __tablename__ = "q_wps"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    wps_no: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    standard: Mapped[QWeldStandard] = enum_col(QWeldStandard)
    processes: Mapped[list[str]] = mapped_column(STRS, default=list)
    joint_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    base_material_group: Mapped[str | None] = mapped_column(String(60))
    thickness_min_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    thickness_max_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    diameter_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    diameter_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    positions: Mapped[list[str]] = mapped_column(STRS, default=list)
    filler_class: Mapped[str | None] = mapped_column(String(40))
    f_no: Mapped[str | None] = mapped_column(String(10))
    a_no: Mapped[str | None] = mapped_column(String(10))
    preheat_min_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    interpass_max_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    pwht: Mapped[str | None] = mapped_column(String(200))
    gas: Mapped[str | None] = mapped_column(String(80))
    prequalified: Mapped[bool] = mapped_column(Boolean, default=False)
    pqr_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QWpsStatus] = enum_col(QWpsStatus, default=QWpsStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))


class QPqr(Audited, Base):
    __tablename__ = "q_pqrs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    pqr_no: Mapped[str] = mapped_column(String(40))
    standard: Mapped[QWeldStandard] = enum_col(QWeldStandard)
    process: Mapped[QWeldProcess] = enum_col(QWeldProcess)
    test_date: Mapped[date] = mapped_column(Date)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    lab_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    certificate_no: Mapped[str | None] = mapped_column(String(60))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QPqrStatus] = enum_col(QPqrStatus, default=QPqrStatus.draft)


class QWelder(Audited, Base):
    """A welder of the project: a Phase 2 worker with a stamp (no ID number copied, P2-7)."""

    __tablename__ = "q_welders"
    __table_args__ = (UniqueConstraint("project_id", "stamp"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    stamp: Mapped[str] = mapped_column(String(10))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    status: Mapped[QWelderStatus] = enum_col(QWelderStatus, default=QWelderStatus.active)


class QWpq(Audited, Base):
    __tablename__ = "q_wpqs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    wpq_no: Mapped[str | None] = mapped_column(String(40))
    welder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_welders.id"), index=True)
    standard: Mapped[QWeldStandard] = enum_col(QWeldStandard)
    process: Mapped[QWeldProcess] = enum_col(QWeldProcess)
    test_wps_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_wps.id"))
    test_date: Mapped[date] = mapped_column(Date)
    coupon_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    coupon_diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    coupon_position: Mapped[str | None] = mapped_column(String(4))
    positions: Mapped[list[str]] = mapped_column(STRS, default=list)
    thickness_min_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    thickness_max_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    diameter_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    f_no: Mapped[str | None] = mapped_column(String(10))
    test_method: Mapped[QWpqMethod] = enum_col(QWpqMethod)
    result: Mapped[QAcceptReject] = enum_col(QAcceptReject, default=QAcceptReject.accept)
    examiner_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    personnel_certificate_id: Mapped[uuid.UUID | None] = mapped_column()
    last_use: Mapped[date | None] = mapped_column(Date)
    continuity_until: Mapped[date | None] = mapped_column(Date)
    revalidation_due: Mapped[date | None] = mapped_column(Date)
    confirmations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QWpqStatus] = enum_col(QWpqStatus, default=QWpqStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    alerts_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)


class QWeld(Audited, Base):
    """§C.6 one weld joint of the weld log; NDT lot = (lot_code, ndt_method)."""

    __tablename__ = "q_welds"
    __table_args__ = (
        UniqueConstraint("project_id", "joint_id"),
        Index("ix_q_welds_lot", "project_id", "lot_code"),
        Index("ix_q_welds_welder_ids", "welder_ids", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    joint_id: Mapped[str] = mapped_column(String(30))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    drawing_ref: Mapped[str | None] = mapped_column(String(60))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    system_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_systems.id"))
    wps_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_wps.id"))
    process: Mapped[QWeldProcess] = enum_col(QWeldProcess)
    position: Mapped[str] = mapped_column(String(4))
    joint_type: Mapped[QJointType] = enum_col(QJointType)
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    thickness_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    length_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    welders: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    welder_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    welded_on: Mapped[date] = mapped_column(Date)
    visual_result: Mapped[QAcceptReject | None] = enum_col(QAcceptReject, nullable=True)
    visual_defect: Mapped[str | None] = mapped_column(String(120))
    lot_code: Mapped[str | None] = mapped_column(String(40))
    ndt_method: Mapped[QNdtMethod | None] = enum_col(QNdtMethod, nullable=True)
    ndt_required_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    selected_for_ndt: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_reason: Mapped[QNdtSelection | None] = enum_col(QNdtSelection, nullable=True)
    selected_from_id: Mapped[uuid.UUID | None] = mapped_column()  # progressive parent weld
    ndt_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    repair_count: Mapped[int] = mapped_column(Integer, default=0)
    override_reason: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[QWeldStatus] = enum_col(QWeldStatus, default=QWeldStatus.welded)
    status_reason: Mapped[str | None] = mapped_column(String(1000))


# ---- calibration (§C.4) -------------------------------------------------------------------------


class QCalibration(Audited, Base):
    __tablename__ = "q_calibrations"
    __table_args__ = (Index("ix_q_calibrations_mte_date", "mte_id", "cal_date"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    cal_no: Mapped[str | None] = mapped_column(String(40))
    mte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_mte_items.id"))
    kind: Mapped[QCalKind] = enum_col(QCalKind, default=QCalKind.calibration)
    cal_date: Mapped[date] = mapped_column(Date)
    provider_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    in_house: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_mte_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mte_items.id"))
    certificate_no: Mapped[str | None] = mapped_column(String(60))
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    as_found_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    as_left_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    max_found_error: Mapped[Decimal | None] = mapped_column(VAL)
    traceability: Mapped[str | None] = mapped_column(String(300))
    uncertainty: Mapped[str | None] = mapped_column(String(80))
    verification_note: Mapped[str | None] = mapped_column(String(1000))
    next_due: Mapped[date | None] = mapped_column(Date)
    decision_comment: Mapped[str | None] = mapped_column(String(1000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QCalRecordStatus] = enum_col(QCalRecordStatus, default=QCalRecordStatus.draft)


class QMteCalOverride(Base):
    """Q-CAL-02 manual `out_of_service` / `limited_use` with its reason (one per instrument)."""

    __tablename__ = "q_mte_cal_overrides"

    mte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_mte_items.id"), primary_key=True)
    status: Mapped[QMteOverride] = enum_col(QMteOverride)
    reason: Mapped[str] = mapped_column(String(500))
    set_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QOotReview(Audited, Base):
    """Q-CAL-04 out-of-tolerance impact review."""

    __tablename__ = "q_oot_reviews"
    __table_args__ = (Index("ix_q_oot_reviews_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    oot_no: Mapped[str] = mapped_column(String(40))
    mte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_mte_items.id"))
    calibration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_calibrations.id"))
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    error_abs: Mapped[Decimal] = mapped_column(VAL)
    due_on: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[QOotStatus] = enum_col(QOotStatus, default=QOotStatus.open)


class QOotItem(Base):
    """One measurement made with the instrument in the review period, with its decision."""

    __tablename__ = "q_oot_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("q_oot_reviews.id", ondelete="CASCADE"), index=True
    )
    usage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mte_usage.id"))
    record_type: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[uuid.UUID] = mapped_column()
    ref: Mapped[str | None] = mapped_column(String(60))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value: Mapped[Decimal | None] = mapped_column(VAL)
    limit_low: Mapped[Decimal | None] = mapped_column(VAL)
    limit_high: Mapped[Decimal | None] = mapped_column(VAL)
    margin: Mapped[Decimal | None] = mapped_column(VAL)
    proposed: Mapped[str | None] = mapped_column(String(20))
    decision: Mapped[str | None] = mapped_column(String(20))
    justification: Mapped[str | None] = mapped_column(String(1000))
    recheck_record_type: Mapped[str | None] = mapped_column(String(40))
    recheck_record_id: Mapped[uuid.UUID | None] = mapped_column()
    recheck_ref: Mapped[str | None] = mapped_column(String(60))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- competence (§C.5) --------------------------------------------------------------------------


class QCompetenceReq(Audited, Base):
    """Q-CPT requirement row (org-wide library): evidence through the Phase 2 hook providers."""

    __tablename__ = "q_competence_reqs"

    code: Mapped[str] = mapped_column(String(20), unique=True)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    applies_to: Mapped[list[str]] = mapped_column(STRS, default=list)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    any_of: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    all_of: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    policy: Mapped[QCompetencePolicy] = enum_col(
        QCompetencePolicy, default=QCompetencePolicy.inherit
    )
    profile: Mapped[QProfileScope] = enum_col(QProfileScope, default=QProfileScope.both)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QCompetenceCell(Base):
    """Q-CPT-03 matrix snapshot for the export (246): one row per project, person and requirement,
    rebuilt by the daily job, the seed and every requirement change (D-344)."""

    __tablename__ = "q_competence_cells"
    __table_args__ = (UniqueConstraint("project_id", "holder_user_id", "requirement_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    holder_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requirement_code: Mapped[str] = mapped_column(String(20))
    requirement_title: Mapped[str] = mapped_column(String(150))
    state: Mapped[QCompetenceState] = enum_col(QCompetenceState)
    valid_until: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(60))
    as_of: Mapped[date] = mapped_column(Date)
