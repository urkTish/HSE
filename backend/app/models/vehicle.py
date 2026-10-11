"""Option 7a table (spec 7a-vehicle-accident-details §3.2): the vehicles involved in a Phase 1
incident. The incident-level fields (road type, journey purpose, Najm / police report, third-party
damage, recorded-not-counted) are columns of `incidents`; report files are attachments with owner
`incident_accident_report`."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.access_enums import LicenceClass, LicenceIssuer, PlateType
from app.core.vehicle_enums import (
    VehCategory,
    VehDamage,
    VehDocState,
    VehDriverKind,
    VehLicenceCheck,
    VehOwnership,
    VehRole,
    VehSeatBelt,
    VehSpeedSource,
)
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col


class IncidentVehicle(UUIDPk, TimestampMixin, Base):
    """§3.2 المركبة المتورطة: 1–10 per incident (V1, V2 …)."""

    __tablename__ = "incident_vehicles"
    __table_args__ = (
        UniqueConstraint("incident_id", "seq", name="uq_incident_vehicle_seq"),
        Index("ix_incident_vehicle_project_date", "project_id", "occurred_date"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    occurred_date: Mapped[date] = mapped_column(Date)  # copy of the incident's local date
    seq: Mapped[int] = mapped_column(Integer)
    ownership: Mapped[VehOwnership] = enum_col(VehOwnership)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"), index=True)
    plate_type: Mapped[PlateType | None] = enum_col(PlateType, nullable=True)
    plate_letters_ar: Mapped[str | None] = mapped_column(String(5))
    plate_letters_en: Mapped[str | None] = mapped_column(String(3))
    plate_digits: Mapped[str | None] = mapped_column(String(4))
    category: Mapped[VehCategory | None] = enum_col(VehCategory, nullable=True)
    make_model: Mapped[str | None] = mapped_column(String(60))
    role: Mapped[VehRole] = enum_col(VehRole)
    damage: Mapped[VehDamage | None] = enum_col(VehDamage, nullable=True)
    damage_cost_sar: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    doc_istimara: Mapped[VehDocState | None] = enum_col(VehDocState, nullable=True)
    doc_insurance: Mapped[VehDocState | None] = enum_col(VehDocState, nullable=True)
    doc_mvpi: Mapped[VehDocState | None] = enum_col(VehDocState, nullable=True)
    insurer: Mapped[str | None] = mapped_column(String(80))
    policy_no: Mapped[str | None] = mapped_column(String(40))
    seat_belt: Mapped[VehSeatBelt | None] = enum_col(VehSeatBelt, nullable=True)
    speed_kmh: Mapped[int | None] = mapped_column(Integer)
    speed_limit_kmh: Mapped[int | None] = mapped_column(Integer)
    speed_source: Mapped[VehSpeedSource | None] = enum_col(VehSpeedSource, nullable=True)
    driver_kind: Mapped[VehDriverKind | None] = enum_col(VehDriverKind, nullable=True)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"), index=True)
    external_driver_name: Mapped[str | None] = mapped_column(String(120))
    licence_issuer: Mapped[LicenceIssuer | None] = enum_col(LicenceIssuer, nullable=True)
    licence_class: Mapped[LicenceClass | None] = enum_col(LicenceClass, nullable=True)
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    licence_no: Mapped[str | None] = mapped_column(String(30))  # GCC / international only
    licence_prefilled_from_adp: Mapped[bool] = mapped_column(Boolean, default=False)
    licence_check: Mapped[VehLicenceCheck | None] = enum_col(VehLicenceCheck, nullable=True)
    hours_on_duty: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    driver_case_no: Mapped[int | None] = mapped_column(Integer)
    adp_offence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("airside_offences.id"))
    prompt_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)

    incident: Mapped[Any] = relationship("Incident", lazy="select", viewonly=True)

    @property
    def label(self) -> str:
        return f"V{self.seq}"

    # 6g dataset `incident_vehicles` reads these incident fields per row (VA-15: no files)
    @property
    def incident_ref(self) -> str:
        return str(self.incident.ref) if self.incident is not None else ""

    @property
    def road_type(self) -> Any:
        return self.incident.road_type if self.incident is not None else None

    @property
    def report_no(self) -> str | None:
        return self.incident.report_no if self.incident is not None else None

    @property
    def recorded_not_counted(self) -> bool:
        return bool(self.incident.recorded_not_counted) if self.incident is not None else False
