"""Contractors and project engagements."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ContractorCategory, ContractorStatus
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col


class Contractor(UUIDPk, TimestampMixin, Base):
    __tablename__ = "contractors"

    legal_name_en: Mapped[str] = mapped_column(String(200))
    legal_name_ar: Mapped[str] = mapped_column(String(200))
    legal_name_en_norm: Mapped[str] = mapped_column(String(200), unique=True)
    legal_name_ar_norm: Mapped[str] = mapped_column(String(200), unique=True)
    short_code: Mapped[str] = mapped_column(String(10), unique=True)
    cr_number: Mapped[str] = mapped_column(String(10), unique=True)
    cr_expiry_date: Mapped[date | None] = mapped_column(Date)
    vat_number: Mapped[str | None] = mapped_column(String(15))
    contractor_category: Mapped[ContractorCategory] = enum_col(ContractorCategory)
    primary_contact_name: Mapped[str] = mapped_column(String(120))
    primary_contact_mobile: Mapped[str] = mapped_column(String(16))
    primary_contact_email: Mapped[str] = mapped_column(String(254))
    status: Mapped[ContractorStatus] = enum_col(ContractorStatus, default=ContractorStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", use_alter=True)
    )
    cr_alerts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ProjectEngagement(UUIDPk, TimestampMixin, Base):
    __tablename__ = "project_engagements"
    __table_args__ = (
        UniqueConstraint("project_id", "contractor_id", name="uq_engagement_project_contractor"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    contractor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contractors.id"), index=True)
    tier: Mapped[int] = mapped_column(Integer)
    parent_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    root_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    scope_of_work_en: Mapped[str] = mapped_column(String(500))
    scope_of_work_ar: Mapped[str] = mapped_column(String(500))
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), default=list)
    mobilisation_date: Mapped[date] = mapped_column(Date)
    demobilisation_date: Mapped[date | None] = mapped_column(Date)
    parent_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)

    contractor: Mapped[Contractor] = relationship(lazy="joined")
