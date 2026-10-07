"""Shared query parameters for every KPI / dashboard endpoint (spec 1-dashboard D-2, K-R5,
K-R10, K-R11)."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from app.core.enums import ZoneType
from app.core.hse_enums import ComparisonKind, PeriodPreset


@dataclass(frozen=True)
class KpiQuery:
    project_ids: list[uuid.UUID]
    all_projects: bool
    site_ids: list[uuid.UUID]
    zone_ids: list[uuid.UUID]
    zone_type: ZoneType | None
    engagement_ids: list[uuid.UUID]
    include_subcontractors: bool
    tiers: list[int]
    period: PeriodPreset
    anchor: date | None
    start: date | None
    end: date | None
    as_of: date | None
    compare: list[ComparisonKind] = field(default_factory=list)
    gate_ids: list[uuid.UUID] = field(default_factory=list)


def kpi_query(
    project_id: Annotated[
        list[uuid.UUID] | None,
        Query(
            description="Project(s). Repeat for several. Required unless all_projects=true. "
            "Out-of-scope ids → 404."
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        Query(description="HSE Manager only: every project (K-R12 bases banner)."),
    ] = False,
    site_id: Annotated[list[uuid.UUID] | None, Query(description="Sites (multi).")] = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query(description="Zones (multi).")] = None,
    zone_type: Annotated[ZoneType | None, Query(description="airside / landside / other.")] = None,
    engagement_id: Annotated[
        list[uuid.UUID] | None,
        Query(description="Contractor engagement(s); roll-up per include_subcontractors."),
    ] = None,
    include_subcontractors: Annotated[
        bool, Query(description="K-R5: engagement + descendants (default) or this only.")
    ] = True,
    tier: Annotated[list[int] | None, Query(ge=1, le=3, description="Tier 1/2/3.")] = None,
    period: Annotated[PeriodPreset, Query(description="K-R10 preset.")] = PeriodPreset.month,
    anchor: Annotated[
        date | None,
        Query(
            description="A date inside the wanted day/week/month/quarter/year (default as_of). "
            "mtd/qtd/ytd/r12/itd end at as_of."
        ),
    ] = None,
    start: Annotated[date | None, Query(description="period=custom: first day.")] = None,
    end: Annotated[date | None, Query(description="period=custom: last day (inclusive).")] = None,
    as_of: Annotated[
        date | None, Query(description="Evaluation date; default today (project timezone).")
    ] = None,
    compare: Annotated[
        list[ComparisonKind] | None,
        Query(description="Comparisons to compute (K-R11). Default: previous."),
    ] = None,
    gate_id: Annotated[
        list[uuid.UUID] | None,
        Query(description="Gate(s): filters gate KPIs (K-52, K-53, K-53b) only."),
    ] = None,
) -> KpiQuery:
    return KpiQuery(
        project_ids=project_id or [],
        all_projects=all_projects,
        site_ids=site_id or [],
        zone_ids=zone_id or [],
        zone_type=zone_type,
        engagement_ids=engagement_id or [],
        include_subcontractors=include_subcontractors,
        tiers=tier or [],
        period=period,
        anchor=anchor,
        start=start,
        end=end,
        as_of=as_of,
        compare=[ComparisonKind.previous] if compare is None else compare,
        gate_ids=gate_id or [],
    )


KpiParams = Annotated[KpiQuery, Depends(kpi_query)]
