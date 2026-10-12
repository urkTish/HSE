"""Option 7b tables (spec 7b-fleet-driver v2.0, Prototype): project settings (§3.5), driver /
operator authorisations (§3.2), pre-use checks (§3.3, the answers live in a 6d checklist response
with owner type `vehicle_check`) and journey plans (§3.4). The site vehicle itself is the Phase 2
`vehicles` row with the §3.1 columns (BD7b-1)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access_enums import LicenceClass, LicenceIssuer
from app.core.site_vehicle_enums import (
    SiteVehAuthStatus,
    SiteVehCheckSource,
    SiteVehDriverGroup,
    SiteVehJourneyStatus,
    SiteVehLimitingFactor,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col


class SiteVehicleSettings(Base):
    """§3.5 (one row per project). `site_vehicles_from` is a column (null = 7b off on the
    project); the other keys live in `values`, merged over the defaults on read."""

    __tablename__ = "site_vehicle_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    site_vehicles_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class DriverAuthorisation(Audited, Base):
    """§3.2. One live (draft / active / suspended) authorisation per worker and project."""

    __tablename__ = "driver_authorisations"
    __table_args__ = (
        Index(
            "uq_driver_auth_live",
            "project_id",
            "worker_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'active', 'suspended')"),
        ),
        Index("ix_driver_auth_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    seq: Mapped[int] = mapped_column(Integer)
    auth_no: Mapped[str] = mapped_column(String(40), unique=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    groups: Mapped[list[str]] = mapped_column(STRS, default=list)
    # DA-2 (plant): the site plant this operator is authorised for; a vehicle linked to a
    # Phase 4 item adds the personnel_certificate hook with its EQC operator code (DECISIONS)
    plant_vehicle_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    licence_issuer: Mapped[LicenceIssuer | None] = enum_col(LicenceIssuer, nullable=True)
    licence_class: Mapped[LicenceClass | None] = enum_col(LicenceClass, nullable=True)
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    licence_prefilled_from_adp: Mapped[bool] = mapped_column(Boolean, default=False)
    assessment_date: Mapped[date] = mapped_column(Date)
    assessor: Mapped[str] = mapped_column(String(120))
    issued_on: Mapped[date] = mapped_column(Date)
    own_valid_until: Mapped[date] = mapped_column(Date)
    effective_valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[SiteVehLimitingFactor | None] = enum_col(
        SiteVehLimitingFactor, nullable=True
    )
    hook_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    hooks_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SiteVehAuthStatus] = enum_col(SiteVehAuthStatus, default=SiteVehAuthStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class VehicleCheck(Audited, Base):
    """§3.3 pre-use check. `check_no` = VPC-<project>-<yyyymmdd>-<nnnn> (per project and day).
    The defect hold of PU-3 lives on the failing check (hold_set … hold_cleared_at), so the
    readiness of any past day can be derived."""

    __tablename__ = "vehicle_checks"
    __table_args__ = (
        Index("ix_vehicle_check_vehicle_date", "vehicle_id", "check_date"),
        Index("ix_vehicle_check_project_date", "project_id", "check_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    check_no: Mapped[str] = mapped_column(String(48), unique=True)
    seq: Mapped[int] = mapped_column(Integer)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    driver_worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    driver_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    driver_group: Mapped[SiteVehDriverGroup | None] = enum_col(SiteVehDriverGroup, nullable=True)
    driver_authorised: Mapped[bool] = mapped_column(Boolean, default=False)
    authorisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("driver_authorisations.id")
    )
    check_date: Mapped[date] = mapped_column(Date)
    response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checklist_responses.id"))
    template_code: Mapped[str] = mapped_column(String(8))
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    critical_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[list[str]] = mapped_column(STRS, default=list)
    source: Mapped[SiteVehCheckSource] = enum_col(
        SiteVehCheckSource, default=SiteVehCheckSource.app
    )
    paper_photo_id: Mapped[uuid.UUID | None] = mapped_column()
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # PU-3 outcomes
    phase4_defect_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("equipment_defects.id"))
    hold_set: Mapped[bool] = mapped_column(Boolean, default=False)
    hold_cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_cleared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    hold_repair_note: Mapped[str | None] = mapped_column(String(1000))
    hold_cleared_by_check_id: Mapped[uuid.UUID | None] = mapped_column()
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class JourneyPlan(Audited, Base):
    """§3.4 (prototype): `plan_no` = JP-<project>-<yyyy>-<nnnn>. No check-ins, no escalation."""

    __tablename__ = "journey_plans"
    __table_args__ = (
        Index("ix_journey_plan_project_depart", "project_id", "planned_depart"),
        Index("uq_journey_plan_seq", "project_id", "year", "seq", unique=True),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    plan_no: Mapped[str] = mapped_column(String(40), unique=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    driver_worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    driver_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    driver_group: Mapped[SiteVehDriverGroup | None] = enum_col(SiteVehDriverGroup, nullable=True)
    driver_authorised: Mapped[bool] = mapped_column(Boolean, default=False)
    authorisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("driver_authorisations.id")
    )
    passengers: Mapped[int] = mapped_column(Integer, default=0)
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    distance_km: Mapped[int] = mapped_column(Integer)
    planned_depart: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_arrive: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    depart_date: Mapped[date] = mapped_column(Date)
    contact_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    hint_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[SiteVehJourneyStatus] = enum_col(
        SiteVehJourneyStatus, default=SiteVehJourneyStatus.planned
    )
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
