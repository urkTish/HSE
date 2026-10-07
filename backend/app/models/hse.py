"""Phase 1 tables (spec 1-dashboard §3): workforce, incidents, observations, inspections,
corrective actions, meetings, attachments, settings, reference lists, AI."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.hse_enums import (
    Activity,
    AgeBand,
    Agency,
    AttachmentOwner,
    BodyPart,
    BodySide,
    CaPriority,
    CaseCategory,
    CaSourceType,
    CaStatus,
    ClassificationStatus,
    ControlLevel,
    DangerousOccurrenceCategory,
    EnvCategory,
    EnvReached,
    ExtensionStatus,
    ExternalBody,
    GroundingResult,
    IdType,
    ImportMode,
    ImportStatus,
    IncidentShift,
    IncidentStatus,
    IncidentType,
    InjuryNature,
    InspectionAssigneeRole,
    InspectionFrequency,
    InspectionStatus,
    InspectionType,
    InvestigationLevel,
    InvestigationMethod,
    Mechanism,
    MeetingType,
    MonthlyReportStatus,
    NotWorkRelatedReason,
    ObservationCategory,
    ObservationStatus,
    ObservationType,
    PermanentDisability,
    PersonType,
    PrivacyCaseReason,
    RiskRating,
    ScanStatus,
    Shift,
    Trade,
    TreatedAt,
    Weekday,
    WorkforceSource,
    WorkforceStatus,
)
from app.core.hse_enums import AssetType as PdAssetType
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col

UUIDS = ARRAY(PG_UUID(as_uuid=True))
STRS = ARRAY(String(40))


# ---- settings, reference lists, preferences ------------------------------------------------------


class HseSettings(Base):
    """§3.10 (one row per project)."""

    __tablename__ = "project_hse_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    lost_days_cap: Mapped[int] = mapped_column(Integer, default=180)
    fatality_lost_days_charge: Mapped[int] = mapped_column(Integer, default=0)
    include_commuting_in_rates: Mapped[bool] = mapped_column(Boolean, default=False)
    include_non_contractor_cases_in_rates: Mapped[bool] = mapped_column(Boolean, default=False)
    max_hours_per_person_day: Mapped[int] = mapped_column(Integer, default=16)
    warn_hours_per_person_day: Mapped[int] = mapped_column(Integer, default=12)
    daily_return_deadline: Mapped[time] = mapped_column(Time, default=time(10, 0))
    completeness_threshold_pct: Mapped[int] = mapped_column(Integer, default=95)
    inspection_grace_days: Mapped[int] = mapped_column(Integer, default=2)
    ca_due_days: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    ca_max_extensions: Mapped[int] = mapped_column(Integer, default=2)
    new_starter_days: Mapped[int] = mapped_column(Integer, default=30)
    heat_season_start: Mapped[str] = mapped_column(String(5), default="06-01")
    heat_season_end: Mapped[str] = mapped_column(String(5), default="09-30")
    low_exposure_hours: Mapped[int] = mapped_column(Integer, default=200_000)
    leading_warning_drop_pct: Mapped[int] = mapped_column(Integer, default=20)
    leading_warning_rise_pct: Mapped[int] = mapped_column(Integer, default=25)
    kpi_targets: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    month_lock_day: Mapped[int] = mapped_column(Integer, default=10)
    injury_identity_retention_years: Mapped[int] = mapped_column(Integer, default=10)
    induction_register_from: Mapped[date | None] = mapped_column(Date)  # v1.1 K-38 (KA-2)
    ai_requested: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_approved_on: Mapped[date | None] = mapped_column(Date)
    ai_approver_name: Mapped[str | None] = mapped_column(String(120))
    ai_approver_organisation: Mapped[str | None] = mapped_column(String(150))
    ai_approval_reference: Mapped[str | None] = mapped_column(String(80))
    ai_approval_notes: Mapped[str | None] = mapped_column(String(500))
    ai_approval_recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ai_approval_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    @property
    def ai_enabled(self) -> bool:
        return self.ai_requested and self.ai_approved_on is not None


class ReferenceItem(Base):
    """§3.11 labels (codes immutable)."""

    __tablename__ = "reference_items"

    list_name: Mapped[str] = mapped_column(String(40), primary_key=True)
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    label_en: Mapped[str] = mapped_column(String(120))
    label_ar: Mapped[str] = mapped_column(String(120))
    group: Mapped[str | None] = mapped_column(String(40))
    description_en: Mapped[str | None] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int | None] = mapped_column(Integer)  # Phase 2 OFF list
    immediate_suspension: Mapped[bool] = mapped_column(Boolean, default=False)


class DashboardPreference(Base):
    __tablename__ = "dashboard_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PeriodLock(Base):
    """Month lock state per project (§4.1) and restatement marker (W-10, I-9)."""

    __tablename__ = "period_locks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)  # first day of month
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    restated: Mapped[bool] = mapped_column(Boolean, default=False)
    restated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unlock_reason: Mapped[str | None] = mapped_column(String(500))


# ---- workforce -----------------------------------------------------------------------------------


class WorkforceImportBatch(UUIDPk, Base):
    __tablename__ = "workforce_import_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    mode: Mapped[ImportMode] = enum_col(ImportMode)
    status: Mapped[ImportStatus] = enum_col(ImportStatus)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    file_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkforceReturn(UUIDPk, TimestampMixin, Base):
    __tablename__ = "workforce_returns"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "work_date",
            "site_id",
            "zone_id",
            "engagement_id",
            "shift",
            name="uq_workforce_return_key",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_workforce_project_date", "project_id", "work_date"),
        Index("ix_workforce_engagement_date", "engagement_id", "work_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    work_date: Mapped[date] = mapped_column(Date)
    shift: Mapped[Shift] = enum_col(Shift)
    no_work: Mapped[bool] = mapped_column(Boolean, default=False)
    headcount: Mapped[int] = mapped_column(Integer)
    man_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    toolbox_talks: Mapped[int] = mapped_column(Integer, default=0)
    toolbox_attendees: Mapped[int] = mapped_column(Integer, default=0)
    inductions: Mapped[int] = mapped_column(Integer, default=0)
    training_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal(0))
    remarks: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[WorkforceSource] = enum_col(WorkforceSource, default=WorkforceSource.manual)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workforce_import_batches.id")
    )
    status: Mapped[WorkforceStatus] = enum_col(WorkforceStatus, default=WorkforceStatus.draft)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- incidents -----------------------------------------------------------------------------------


class Incident(UUIDPk, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq", name="uq_incident_seq"),
        Index("ix_incident_project_date", "project_id", "occurred_date"),
        Index("ix_incident_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ref: Mapped[str] = mapped_column(String(40), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    location_detail: Mapped[str | None] = mapped_column(String(200))
    responsible_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_date: Mapped[date] = mapped_column(Date)  # project-local date (K-R2)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    shift: Mapped[IncidentShift | None] = enum_col(IncidentShift, nullable=True)
    incident_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    primary_type: Mapped[IncidentType] = enum_col(IncidentType)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    immediate_actions: Mapped[str | None] = mapped_column(Text)
    activity: Mapped[Activity | None] = enum_col(Activity, nullable=True)
    work_related: Mapped[bool] = mapped_column(Boolean, default=True)
    not_work_related_reason: Mapped[NotWorkRelatedReason | None] = enum_col(
        NotWorkRelatedReason, nullable=True
    )
    work_related_rationale: Mapped[str | None] = mapped_column(String(500))
    actual_severity: Mapped[int | None] = mapped_column(Integer)
    potential_severity: Mapped[int | None] = mapped_column(Integer)
    ambient_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    airside_flags: Mapped[list[str]] = mapped_column(STRS, default=list)
    pd_asset_type: Mapped[PdAssetType | None] = enum_col(PdAssetType, nullable=True)
    pd_estimated_cost_sar: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    env_category: Mapped[EnvCategory | None] = enum_col(EnvCategory, nullable=True)
    env_substance: Mapped[str | None] = mapped_column(String(100))
    env_quantity_l: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    env_contained: Mapped[bool | None] = mapped_column(Boolean)
    env_reached: Mapped[EnvReached | None] = enum_col(EnvReached, nullable=True)
    do_category: Mapped[DangerousOccurrenceCategory | None] = enum_col(
        DangerousOccurrenceCategory, nullable=True
    )
    status: Mapped[IncidentStatus] = enum_col(IncidentStatus, default=IncidentStatus.draft)
    void_reason: Mapped[str | None] = mapped_column(String(1000))
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    higher_control_justification: Mapped[str | None] = mapped_column(String(1000))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def hipo(self) -> bool:
        return (self.potential_severity or 0) >= 4

    @property
    def late_report(self) -> bool:
        return (
            self.reported_at is not None
            and (self.reported_at - self.occurred_at).total_seconds() > 24 * 3600
        )


class ExternalNotification(Base):
    __tablename__ = "incident_external_notifications"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    body: Mapped[ExternalBody] = enum_col(ExternalBody, primary_key=True)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reference_no: Mapped[str | None] = mapped_column(String(60))
    notified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class InjuryCase(UUIDPk, TimestampMixin, Base):
    __tablename__ = "injury_cases"
    __table_args__ = (UniqueConstraint("incident_id", "person_no", name="uq_case_person_no"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    person_no: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workers.id"), index=True
    )  # v1.1 (Phase 2 worker register)
    person_type: Mapped[PersonType] = enum_col(PersonType)
    employer_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    person_name: Mapped[str] = mapped_column(String(120))
    id_type: Mapped[IdType | None] = enum_col(IdType, nullable=True)
    id_number_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    id_number_masked: Mapped[str | None] = mapped_column(String(20))
    employee_no: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str | None] = mapped_column(String(2))
    trade: Mapped[Trade] = enum_col(Trade)
    age_band: Mapped[AgeBand | None] = enum_col(AgeBand, nullable=True)
    site_start_date: Mapped[date | None] = mapped_column(Date)
    hours_into_shift: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    illness: Mapped[bool] = mapped_column(Boolean, default=False)
    body_part: Mapped[BodyPart] = enum_col(BodyPart)
    body_side: Mapped[BodySide | None] = enum_col(BodySide, nullable=True)
    nature: Mapped[InjuryNature] = enum_col(InjuryNature)
    mechanism: Mapped[Mechanism] = enum_col(Mechanism)
    agency: Mapped[Agency] = enum_col(Agency)
    treatments: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list)
    loss_of_consciousness: Mapped[bool] = mapped_column(Boolean, default=False)
    treated_at: Mapped[TreatedAt] = enum_col(TreatedAt)
    fatal: Mapped[bool] = mapped_column(Boolean, default=False)
    date_of_death: Mapped[date | None] = mapped_column(Date)
    away_start_date: Mapped[date | None] = mapped_column(Date)
    rtw_date: Mapped[date | None] = mapped_column(Date)
    restricted_start: Mapped[date | None] = mapped_column(Date)
    restricted_end: Mapped[date | None] = mapped_column(Date)
    transfer_start: Mapped[date | None] = mapped_column(Date)
    transfer_end: Mapped[date | None] = mapped_column(Date)
    permanent_disability: Mapped[PermanentDisability] = enum_col(
        PermanentDisability, default=PermanentDisability.none
    )
    commuting: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_case: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_reason: Mapped[PrivacyCaseReason | None] = enum_col(PrivacyCaseReason, nullable=True)
    medical_notes: Mapped[str | None] = mapped_column(Text)
    gosi_case_ref: Mapped[str | None] = mapped_column(String(30))
    derived_category: Mapped[CaseCategory] = enum_col(CaseCategory)
    confirmed_category: Mapped[CaseCategory | None] = enum_col(CaseCategory, nullable=True)
    classification_status: Mapped[ClassificationStatus] = enum_col(
        ClassificationStatus, default=ClassificationStatus.provisional
    )
    override_justification: Mapped[str | None] = mapped_column(String(1000))
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_open_alert_on: Mapped[date | None] = mapped_column(Date)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def category(self) -> CaseCategory:
        return self.confirmed_category or self.derived_category


class Investigation(Base):
    __tablename__ = "investigations"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    level: Mapped[InvestigationLevel] = enum_col(InvestigationLevel)
    lead_investigator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    team_member_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    method: Mapped[InvestigationMethod | None] = enum_col(InvestigationMethod, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    extensions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    preliminary_report: Mapped[str | None] = mapped_column(Text)
    preliminary_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence_of_events: Mapped[str | None] = mapped_column(Text)
    immediate_causes: Mapped[str | None] = mapped_column(Text)
    root_causes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    ptw_involved: Mapped[bool | None] = mapped_column(Boolean)
    ptw_ref: Mapped[str | None] = mapped_column(String(40))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_comment: Mapped[str | None] = mapped_column(String(1000))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- observations --------------------------------------------------------------------------------


class Observation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq", name="uq_observation_seq"),
        Index("ix_observation_project_date", "project_id", "observed_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ref: Mapped[str] = mapped_column(String(40), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_date: Mapped[date] = mapped_column(Date)
    observer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    observed_engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    obs_type: Mapped[ObservationType] = enum_col(ObservationType)
    category: Mapped[ObservationCategory] = enum_col(ObservationCategory)
    risk_rating: Mapped[RiskRating | None] = enum_col(RiskRating, nullable=True)
    description: Mapped[str] = mapped_column(String(1000))
    stop_work_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    immediate_action: Mapped[str | None] = mapped_column(String(500))
    closed_on_spot: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[ObservationStatus] = enum_col(ObservationStatus)
    closure_comment: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_date: Mapped[date | None] = mapped_column(Date)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    no_ca_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- inspections ---------------------------------------------------------------------------------


class InspectionPlan(UUIDPk, TimestampMixin, Base):
    __tablename__ = "inspection_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    inspection_type: Mapped[InspectionType] = enum_col(InspectionType)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    frequency: Mapped[InspectionFrequency] = enum_col(InspectionFrequency)
    weekday: Mapped[Weekday | None] = enum_col(Weekday, nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    assignee_role: Mapped[InspectionAssigneeRole] = enum_col(InspectionAssigneeRole)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    generated_until: Mapped[date | None] = mapped_column(Date)


class Inspection(UUIDPk, TimestampMixin, Base):
    __tablename__ = "inspections"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq", name="uq_inspection_seq"),
        UniqueConstraint("plan_id", "planned_date", name="uq_inspection_plan_date"),
        Index("ix_inspection_project_planned", "project_id", "planned_date"),
        Index("ix_inspection_project_completed", "project_id", "completed_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ref: Mapped[str] = mapped_column(String(40), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inspection_plans.id"))
    inspection_type: Mapped[InspectionType] = enum_col(InspectionType)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    assignee_role: Mapped[InspectionAssigneeRole | None] = enum_col(
        InspectionAssigneeRole, nullable=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    planned_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[date | None] = mapped_column(Date)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    items_checked: Mapped[int | None] = mapped_column(Integer)
    items_compliant: Mapped[int | None] = mapped_column(Integer)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[InspectionStatus] = enum_col(InspectionStatus)
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    missed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- corrective actions --------------------------------------------------------------------------


class CorrectiveAction(UUIDPk, TimestampMixin, Base):
    __tablename__ = "corrective_actions"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq", name="uq_ca_seq"),
        Index("ix_ca_project_due", "project_id", "due_date"),
        Index("ix_ca_project_status", "project_id", "status"),
        Index("ix_ca_source", "source_type", "source_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    ref: Mapped[str] = mapped_column(String(40), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[CaSourceType] = enum_col(CaSourceType)
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    ai_recommendation_id: Mapped[str | None] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    responsible_engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    control_level: Mapped[ControlLevel] = enum_col(ControlLevel)
    priority: Mapped[CaPriority] = enum_col(CaPriority)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    verifier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    original_due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[CaStatus] = enum_col(CaStatus, default=CaStatus.open)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[date | None] = mapped_column(Date)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_date: Mapped[date | None] = mapped_column(Date)
    verification_comment: Mapped[str | None] = mapped_column(String(1000))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_date: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class CaExtension(UUIDPk, Base):
    __tablename__ = "ca_extensions"

    ca_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("corrective_actions.id"), index=True)
    new_due_date: Mapped[date] = mapped_column(Date)
    previous_due_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[ExtensionStatus] = enum_col(ExtensionStatus)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(String(500))


# ---- meetings, attachments -----------------------------------------------------------------------


class HseMeeting(UUIDPk, TimestampMixin, Base):
    __tablename__ = "hse_meetings"
    __table_args__ = (Index("ix_meeting_project_planned", "project_id", "planned_date"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    meeting_type: Mapped[MeetingType] = enum_col(MeetingType)
    title: Mapped[str | None] = mapped_column(String(150))
    planned_date: Mapped[date] = mapped_column(Date)
    held_date: Mapped[date | None] = mapped_column(Date)
    invited_count: Mapped[int] = mapped_column(Integer)
    attended_count: Mapped[int | None] = mapped_column(Integer)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class Attachment(UUIDPk, Base):
    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachment_owner", "owner_type", "owner_id"),)

    owner_type: Mapped[AttachmentOwner] = enum_col(AttachmentOwner)
    owner_id: Mapped[uuid.UUID] = mapped_column()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_bucket: Mapped[str] = mapped_column(String(40))
    storage_key: Mapped[str] = mapped_column(String(300))
    scan_status: Mapped[ScanStatus] = enum_col(ScanStatus)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- AI ------------------------------------------------------------------------------------------


class AiAnswerRecord(UUIDPk, Base):
    __tablename__ = "ai_answers"
    __table_args__ = (Index("ix_ai_answer_cache", "cache_key"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    cache_key: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    grounding: Mapped[GroundingResult] = enum_col(GroundingResult)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiLog(UUIDPk, Base):
    """AI-16 log; no names, IDs or medical data are ever stored here."""

    __tablename__ = "ai_logs"
    __table_args__ = (Index("ix_ai_log_user_created", "user_id", "created_at"),)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(20))
    question_masked: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    answer_excerpt: Mapped[str | None] = mapped_column(Text)
    grounding: Mapped[GroundingResult] = enum_col(GroundingResult)
    grounding_failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(40))
    cached: Mapped[bool] = mapped_column(Boolean, default=False)


class AiInsightCache(Base):
    __tablename__ = "ai_insight_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MonthlyReport(UUIDPk, Base):
    __tablename__ = "monthly_reports"
    __table_args__ = (Index("ix_monthly_report_project_month", "project_id", "month"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[MonthlyReportStatus] = enum_col(MonthlyReportStatus)
    model: Mapped[str | None] = mapped_column(String(60))
    error_code: Mapped[str | None] = mapped_column(String(40))
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    data_hash: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobMark(Base):
    """Idempotency marks for scheduled alerts (e.g. 'daily_return_missing:<eng>:<site>:<date>')."""

    __tablename__ = "job_marks"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
