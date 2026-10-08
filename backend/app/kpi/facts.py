"""In-memory inputs of the KPI engine.

The loader (``app.kpi.data``) fills these from aggregated SQL for one role scope; the engine
(``app.kpi.engine``) is pure and is unit-tested by building facts directly (W1-W8).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.hse_enums import CaseCategory, CaStatus, ControlLevel, PermanentDisability
from app.kpi.cases import CaseDates

UUID = uuid.UUID


@dataclass(frozen=True, slots=True)
class WfFact:
    """Workforce returns aggregated per date × engagement × site × zone (all shifts)."""

    d: date
    eng: UUID
    site: UUID
    zone: UUID | None
    mh: Decimal
    hc: int
    tbt: int = 0
    tbt_att: int = 0
    ind: int = 0
    trn: Decimal = Decimal(0)
    reported: bool = True
    project: UUID | None = None
    ids: tuple[UUID, ...] = ()  # return ids (drill-down only)
    shift: str = "all"


@dataclass(frozen=True, slots=True)
class IndFact:
    """v1.1 K-38: a passed general_site induction record (dates ≥ induction_register_from)."""

    d: date
    eng: UUID | None
    site: UUID | None
    project: UUID


@dataclass(frozen=True, slots=True)
class CaseFact:
    id: UUID
    incident_id: UUID
    incident_ref: str
    d: date
    eng: UUID | None
    site: UUID
    zone: UUID | None
    category: CaseCategory
    dates: CaseDates
    eligible: bool = True
    provisional: bool = False
    fatal: bool = False
    permanent: PermanentDisability = PermanentDisability.none
    cap: int = 180
    fatality_charge: int = 0
    project: UUID | None = None
    # analysis attributes (breakdowns, T9); never identity
    hour: int | None = None
    shift: str | None = None
    activity: str | None = None
    mechanism: str | None = None
    agency: str | None = None
    body_part: str | None = None
    nature: str | None = None
    trade: str | None = None
    age_band: str | None = None
    nationality: str | None = None
    days_on_site: int | None = None
    ptw_involved: bool | None = None
    root_causes: tuple[str, ...] = ()
    person_no: int = 1


@dataclass(frozen=True, slots=True)
class EventFact:
    """A counted incident (status ∉ {draft, voided}, work related)."""

    id: UUID
    ref: str
    d: date
    eng: UUID | None
    site: UUID
    zone: UUID | None
    types: frozenset[str]
    hipo: bool = False
    late: bool = False
    pd_cost: Decimal = Decimal(0)
    project: UUID | None = None
    hour: int | None = None
    shift: str | None = None
    activity: str | None = None
    ptw_involved: bool | None = None
    root_causes: tuple[str, ...] = ()
    airside_flags: tuple[str, ...] = ()
    title: str = ""


@dataclass(frozen=True, slots=True)
class ObsFact:
    """Observations aggregated by date × engagement × site × zone × type × status."""

    d: date
    eng: UUID
    site: UUID
    zone: UUID | None
    obs_type: str
    safe: bool
    closed_date: date | None = None
    n: int = 1
    category: str | None = None
    risk: str | None = None
    project: UUID | None = None
    ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class InspFact:
    id: UUID
    planned: date | None  # None = unplanned
    completed: date | None
    cancelled: bool
    eng: UUID | None
    site: UUID
    zone: UUID | None
    grace: int = 2
    inspection_type: str | None = None
    project: UUID | None = None


@dataclass(frozen=True, slots=True)
class CaFact:
    id: UUID
    created: date
    due: date
    status: CaStatus
    control: ControlLevel
    eng: UUID
    site: UUID
    zone: UUID | None
    completed: date | None = None
    verified: date | None = None
    cancelled: date | None = None
    priority: str = "medium"
    source_type: str = "other"
    project: UUID | None = None


@dataclass(frozen=True, slots=True)
class MeetingFact:
    id: UUID
    planned: date
    held: date | None
    invited: int
    attended: int | None
    eng: UUID | None = None
    project: UUID | None = None


@dataclass(frozen=True, slots=True)
class EngFact:
    id: UUID
    code: str
    name_en: str
    name_ar: str
    tier: int
    parent: UUID | None
    site_ids: frozenset[UUID]
    mobilisation: date
    demobilisation: date | None = None
    contractor_id: UUID | None = None
    project: UUID | None = None


@dataclass(frozen=True, slots=True)
class ZoneFact:
    id: UUID
    site: UUID
    zone_type: str
    airside_area: str | None = None
    code: str = ""


@dataclass
class Facts:
    wf: list[WfFact] = field(default_factory=list)
    inds: list[IndFact] = field(default_factory=list)
    cases: list[CaseFact] = field(default_factory=list)
    events: list[EventFact] = field(default_factory=list)
    obs: list[ObsFact] = field(default_factory=list)
    insp: list[InspFact] = field(default_factory=list)
    cas: list[CaFact] = field(default_factory=list)
    meetings: list[MeetingFact] = field(default_factory=list)
    engagements: dict[UUID, EngFact] = field(default_factory=dict)
    zones: dict[UUID, ZoneFact] = field(default_factory=dict)
    project_start: date | None = None
    # app.kpi.access_facts.AccessFacts (2-access-permits §6.8), loaded on first use so Phase 1
    # requests never pay for the access registers / gate log.
    access_loader: Any = None
    _access: Any = None

    @property
    def access(self) -> Any:
        if self._access is None and self.access_loader is not None:
            self._access = self.access_loader()
            self.access_loader = None
        return self._access

    @access.setter
    def access(self, value: Any) -> None:
        self._access = value

    # app.kpi.ptw_facts.PtwFacts (3-ptw §6.11), loaded on first use like the access facts.
    ptw_loader: Any = None
    _ptw: Any = None

    @property
    def ptw(self) -> Any:
        if self._ptw is None and self.ptw_loader is not None:
            self._ptw = self.ptw_loader()
            self.ptw_loader = None
        return self._ptw

    @ptw.setter
    def ptw(self, value: Any) -> None:
        self._ptw = value

    # app.kpi.cert_facts.CertFacts (4-third-party-cert §6.7), loaded on first use.
    cert_loader: Any = None
    _cert: Any = None

    @property
    def cert(self) -> Any:
        if self._cert is None and self.cert_loader is not None:
            self._cert = self.cert_loader()
            self.cert_loader = None
        return self._cert

    @cert.setter
    def cert(self, value: Any) -> None:
        self._cert = value

    def sort(self) -> "Facts":
        self.wf.sort(key=lambda r: r.d)
        self.inds.sort(key=lambda r: r.d)
        self.cases.sort(key=lambda r: r.d)
        self.events.sort(key=lambda r: r.d)
        self.obs.sort(key=lambda r: r.d)
        return self

    # ---- engagement tree ----------------------------------------------------------------
    def descendants(self, eng_id: UUID) -> set[UUID]:
        children: dict[UUID, list[UUID]] = {}
        for e in self.engagements.values():
            if e.parent is not None:
                children.setdefault(e.parent, []).append(e.id)
        out = {eng_id}
        stack = [eng_id]
        while stack:
            for c in children.get(stack.pop(), []):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out

    def root_of(self, eng_id: UUID | None) -> UUID | None:
        """Tier-1 ancestor (the contractor tree an engagement belongs to)."""
        cur = self.engagements.get(eng_id) if eng_id else None
        seen: set[UUID] = set()
        while cur is not None and cur.parent is not None and cur.id not in seen:
            seen.add(cur.id)
            nxt = self.engagements.get(cur.parent)
            if nxt is None:
                break
            cur = nxt
        return cur.id if cur else None


@dataclass(frozen=True)
class Filter:
    """User filters applied on top of the loaded (role-scoped) facts. ``None`` = no filter."""

    sites: frozenset[UUID] | None = None
    zones: frozenset[UUID] | None = None
    zone_type: str | None = None
    engs: frozenset[UUID] | None = None

    @property
    def zone_filtered(self) -> bool:
        return self.zones is not None or self.zone_type is not None

    def site_ok(self, site: UUID) -> bool:
        return self.sites is None or site in self.sites

    def eng_ok(self, eng: UUID | None) -> bool:
        return self.engs is None or (eng is not None and eng in self.engs)

    def zone_ok(self, zone: UUID | None, zones: dict[UUID, ZoneFact]) -> bool:
        if not self.zone_filtered:
            return True
        if zone is None:
            return False
        if self.zones is not None and zone not in self.zones:
            return False
        if self.zone_type is not None:
            z = zones.get(zone)
            return z is not None and z.zone_type == self.zone_type
        return True
