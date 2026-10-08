"""Derived facts of one permit (zones and profiles, lift, gas requirement and limits, high-risk
conditions, mandatory roles / documents / hazards), computed from the stored permit."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ptw_enums import DocumentType, Hazard, PermitType, PtwCrewRole
from app.models import Permit, PermitTypeConfig, PtwSettings, Zone
from app.services import hse_settings
from app.services.ptw import common, rules


@dataclass
class Facts:
    permit: Permit
    settings: PtwSettings
    zones: list[Zone]
    zone_facts: list[rules.ZoneFacts]
    sections: dict[str, dict[str, Any]]
    lift: rules.Lift | None
    gas_types: list[str]
    interval: int | None
    limits: rules.Limits
    high_risk_reasons: list[str]
    roles: list[PtwCrewRole]
    documents: list[DocumentType]
    hazards: list[Hazard]

    @property
    def types(self) -> list[str]:
        return list(self.permit.work_types or [])

    def has(self, t: PermitType) -> bool:
        return t.value in (self.permit.work_types or [])

    def sec(self, t: PermitType) -> dict[str, Any]:
        return self.sections.get(t.value) or {}

    @property
    def gas_required(self) -> bool:
        return bool(self.gas_types)

    @property
    def critical(self) -> bool:
        return bool(self.lift and self.lift.critical)

    @property
    def airside(self) -> bool:
        return any(z.airside for z in self.zone_facts)

    @property
    def movement_area(self) -> bool:
        return any(z.in_movement_area for z in self.zone_facts)


def extra_hazards(db: Session, project_id: Any) -> dict[str, list[str]]:
    return {
        c.type.value: list(c.extra_hazards or [])
        for c in db.scalars(
            select(PermitTypeConfig).where(PermitTypeConfig.project_id == project_id)
        )
    }


def compute(db: Session, p: Permit) -> Facts:
    s = common.settings(db, p.project_id)
    zones = common.permit_zones(db, p)
    zf = common.zone_facts(db, zones)
    sections = dict(p.sections or {})
    types = list(p.work_types or [])
    lift = (
        rules.lift(
            sections[PermitType.lifting.value],
            zf,
            s.critical_lift_capacity_pct,
            s.critical_lift_weight_t,
        )
        if PermitType.lifting.value in types and sections.get(PermitType.lifting.value)
        else None
    )
    gas_types = rules.gas_types(
        types, sections, zf, p.flammables_in_use, s.ex_protective_system_depth_m
    )
    interval = rules.retest_interval(gas_types, s.gas_retest_interval_minutes)
    limits = rules.gas_limits(types, s.gas_limits)
    critical = bool(lift and lift.critical)
    hs = hse_settings.get(db, p.project_id)
    return Facts(
        permit=p,
        settings=s,
        zones=zones,
        zone_facts=zf,
        sections=sections,
        lift=lift,
        gas_types=gas_types,
        interval=interval,
        limits=limits,
        high_risk_reasons=rules.high_risk_reasons(
            types, sections, zf, critical, s.ex_protective_system_depth_m
        ),
        roles=rules.mandatory_roles(types, sections),
        documents=rules.mandatory_documents(types, sections, critical, s.ex_pe_design_depth_m),
        hazards=rules.mandatory_hazards(
            types,
            sections,
            p.exposure,
            rules.permit_dates(p.valid_from_at, p.valid_to_at),
            (hs.heat_season_start, hs.heat_season_end),
            extra_hazards(db, p.project_id),
        ),
    )
