"""Projects, settings, sites, zones."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AirsideArea,
    DateFormatEn,
    DigitStyle,
    HijriCalendar,
    Language,
    ProjectStatus,
    ProjectType,
    SiteSide,
    SiteStatus,
    WeekStart,
    ZoneStatus,
    ZoneType,
)
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col


class Project(UUIDPk, TimestampMixin, Base):
    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(12), unique=True)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    project_type: Mapped[ProjectType] = enum_col(ProjectType)
    client_name_en: Mapped[str] = mapped_column(String(150))
    client_name_ar: Mapped[str] = mapped_column(String(150))
    city: Mapped[str] = mapped_column(String(80))
    start_date: Mapped[date] = mapped_column(Date)
    planned_end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ProjectStatus] = enum_col(ProjectStatus, default=ProjectStatus.planning)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    airport_icao: Mapped[str | None] = mapped_column(String(4))
    search_text: Mapped[str] = mapped_column(Text, default="")

    settings: Mapped["ProjectSettings"] = relationship(back_populates="project", uselist=False)

    @property
    def is_airport(self) -> bool:
        return self.project_type == ProjectType.airport


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    ltifr_base_hours: Mapped[int] = mapped_column(Integer, default=1_000_000)
    rate_base_hours: Mapped[int] = mapped_column(Integer, default=200_000)
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Riyadh")
    show_hijri: Mapped[bool] = mapped_column(Boolean, default=False)
    hijri_calendar: Mapped[HijriCalendar] = enum_col(
        HijriCalendar, default=HijriCalendar.umm_al_qura
    )
    default_language: Mapped[Language] = enum_col(Language, default=Language.en)
    week_start: Mapped[WeekStart] = enum_col(WeekStart, default=WeekStart.sunday)
    digits: Mapped[DigitStyle] = enum_col(DigitStyle, default=DigitStyle.western)
    date_format_en: Mapped[DateFormatEn] = enum_col(DateFormatEn, default=DateFormatEn.dd_mmm_yyyy)
    audit_retention_years: Mapped[int] = mapped_column(Integer, default=5)
    inactive_account_days: Mapped[int] = mapped_column(Integer, default=90)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    project: Mapped[Project] = relationship(back_populates="settings")


class Site(UUIDPk, TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_sites_project_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(12))
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    site_side: Mapped[SiteSide] = enum_col(SiteSide)
    gps_lat: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False))
    gps_lng: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False))
    status: Mapped[SiteStatus] = enum_col(SiteStatus, default=SiteStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship()


AIRSIDE_FIELDS = (
    "airside_area",
    "in_movement_area",
    "runway_ref",
    "security_restricted_area",
    "notam_required_for_works",
    "ols_height_limit_m_amsl",
    "max_equipment_height_m_agl",
    "escort_required",
    "adp_required",
    "fod_control_required",
    "works_safety_plan_ref",
)


class Zone(UUIDPk, TimestampMixin, Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("site_id", "code", name="uq_zones_site_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    zone_type: Mapped[ZoneType] = enum_col(ZoneType)
    status: Mapped[ZoneStatus] = enum_col(ZoneStatus, default=ZoneStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, default="")
    # Airside attributes (all null unless zone_type = airside)
    airside_area: Mapped[AirsideArea | None] = enum_col(AirsideArea, nullable=True)
    in_movement_area: Mapped[bool | None] = mapped_column(Boolean)
    runway_ref: Mapped[str | None] = mapped_column(String(10))
    security_restricted_area: Mapped[bool | None] = mapped_column(Boolean)
    notam_required_for_works: Mapped[bool | None] = mapped_column(Boolean)
    ols_height_limit_m_amsl: Mapped[float | None] = mapped_column(Numeric(7, 2, asdecimal=False))
    max_equipment_height_m_agl: Mapped[float | None] = mapped_column(Numeric(6, 2, asdecimal=False))
    escort_required: Mapped[bool | None] = mapped_column(Boolean)
    adp_required: Mapped[bool | None] = mapped_column(Boolean)
    fod_control_required: Mapped[bool | None] = mapped_column(Boolean)
    works_safety_plan_ref: Mapped[str | None] = mapped_column(String(40))

    site: Mapped[Site] = relationship()
