"""Plug-in registries of the Quality module (spec 8-quality §3.2).

Q0 defines every registry here; each part registers its providers from its own package in the
`register()` function of `app/services/quality/q<n>/__init__.py`, which
`app.services.quality.ensure_registered()` calls once. Nothing outside a part's own files changes
when a part plugs in.

| Registry | Key | Used by |
|---|---|---|
| `NCR_SOURCES` | `QNcrSourceType` | NCR create from a source (Q-NCR-02) and close (Q-NCR-15) |
| `RECORD_TYPES` | `QRecordType` | sign-offs, links, M&TE usage, "Awaiting me", Q-RPM-07 |
| `PENDING_STEPS` | part code | "Awaiting my sign-off" (Q-RPM-11) |
| `ATTACHMENT_OWNERS` | `AttachmentOwner` | `attachments._owner` quality branch |
| `CRITERIA_EVALUATORS` | rule code | criteria library kind `rule` (Q-CRT-01) |
| `HOLD_CHECKS` | `"itp_point"` | Q2 pours (Q-TST-12); provided by Q1 |
| `COMPETENCE` | — | Q1 / Q3 / Q4 competence checks; provided by Q2 |
| `DOSSIER_SECTIONS` | section code | Q1 dossier engine |
| `JOBS` | job code | `quality_daily` / `quality_alerts` / `quality_weekly` / `quality_monthly` |
| `DATASETS` | dataset code | 6g export dataset registry (`scorecard/datasets.py`) |
| `SEEDS` | part code | `app.seed_quality.seed_quality_data` |
| `SUPPLIER_GATES` | — | supplier pending_approval → approved (Q-SHR-01); provided by Q4 |
| `NCR_TABS` / `HOME_TILES` | — | extra NCR read sections and Quality home counts |

Providers receive plain arguments (session, principal, ids) and return the small dataclasses
below, so the registry never imports a part."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QDetectionStage,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QRecordType,
    QVerdict,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import Project
    from app.models.quality import QNcr, QSupplier
    from app.services.permissions import Principal


@dataclass(frozen=True)
class Blocker:
    """One reason a transition cannot happen (returned in `detail.meta.blockers`)."""

    code: str
    detail_en: str
    detail_ar: str


# ---- NCR sources (list NS) ---------------------------------------------------------------------


@dataclass(frozen=True)
class SourceInfo:
    """What a source adapter fills on a new NCR (Q-NCR-02). The user may edit all but the
    source and `item_key`."""

    ref: str | None
    title: str | None = None
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    item_key: str | None = None
    detection_stage: QDetectionStage | None = None
    requirement_en: str | None = None
    requirement_ar: str | None = None
    finding_en: str | None = None
    finding_ar: str | None = None
    proposed_class: QNcrClass | None = None  # Q-NCR-04: class computed by the source
    location_ref: str | None = None
    quantity: Any = None
    unit: str | None = None
    lot_refs: tuple[str, ...] = ()
    record_type: QRecordType | None = None  # for the `raised_from` link (Q-NCR-02)


@dataclass
class NcrSource:
    resolve: Callable[[Session, Project, uuid.UUID], SourceInfo]
    on_ncr_status: Callable[[Session, QNcr, QNcrStatus], None] | None = None
    close_check: Callable[[Session, QNcr], list[Blocker]] | None = None


NCR_SOURCES: dict[QNcrSourceType, NcrSource] = {}


# ---- record types (list QRT) -------------------------------------------------------------------


def _none(*_a: Any) -> Any:
    return None


def _false(*_a: Any) -> bool:
    return False


def _empty(*_a: Any) -> set[uuid.UUID]:
    return set()


@dataclass
class RecordTypeAdapter:
    """How the shared services see a record of one type (§3.2 `RECORD_TYPES`)."""

    get: Callable[[Session, uuid.UUID], Any]
    project_id: Callable[[Any], uuid.UUID]
    scope: Callable[[Session, Principal, Any], bool]  # may the principal read it
    ref: Callable[[Any], str]
    link_path: Callable[[Any], str]
    title: Callable[[Any], str] = lambda _r: ""
    site_id: Callable[[Any], uuid.UUID | None] = _none
    # Q-RPM-07: the record's responsible engagement (own field or the §A.4.3 chain)
    engagement: Callable[[Session, Any], uuid.UUID | None] = _none
    # Q-RPM-06: users who created, requested, last submitted or recorded the result decided
    requesters: Callable[[Session, Any, str], set[uuid.UUID]] = _empty
    voided: Callable[[Any], bool] = _false
    record_date: Callable[[Any], date | None] = _none


RECORD_TYPES: dict[QRecordType, RecordTypeAdapter] = {}


# ---- pending steps ("Awaiting my sign-off") -----------------------------------------------------


@dataclass(frozen=True)
class PendingStep:
    record_type: QRecordType
    record_id: uuid.UUID
    project_id: uuid.UUID
    ref: str
    title: str
    step: str
    waiting_since: datetime
    link_path: str
    part: str = "Q0"


PENDING_STEPS: dict[str, Callable[[Session, Principal, uuid.UUID], list[PendingStep]]] = {}


@dataclass(frozen=True)
class OpenStep:
    """A step waiting for a responsible person on one record, with what resolution needs
    (Q-RPM-03). Parts that register `OPEN_STEPS` get "Awaiting me" and "steps without a
    responsible person" (Q-RPM-10) for free through `rpm.pending_from_open`."""

    step: PendingStep
    qualifier: str | None = None
    site_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    requesters: frozenset[uuid.UUID] = frozenset()


OPEN_STEPS: dict[str, Callable[[Session, Project], list[OpenStep]]] = {}


# ---- attachments ------------------------------------------------------------------------------

AttachmentOwnerFn = Callable[["Session", "Principal", uuid.UUID, bool], tuple[uuid.UUID, bool]]
ATTACHMENT_OWNERS: dict[AttachmentOwner, AttachmentOwnerFn] = {}


# ---- criteria evaluators (Q-CRT-01 kind `rule`) ------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    verdict: QVerdict
    reason_en: str = ""
    reason_ar: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


CRITERIA_EVALUATORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], Verdict]] = {}


# ---- hold points (Q1 → Q2) ----------------------------------------------------------------------

# released(db, itp_point_id, location_key) → True / False / None (unknown)
HOLD_CHECKS: dict[str, Callable[[Session, uuid.UUID, str | None], bool | None]] = {}


# ---- competence (Q2 → Q1, Q3, Q4) ----------------------------------------------------------------


@dataclass(frozen=True)
class CompetenceVerdict:
    met: bool | None  # None = not configured (no provider or no requirement)
    code: str = "COMPETENCE_NOT_CONFIGURED"
    detail_en: str = "Competence checks are not configured."
    detail_ar: str = "فحوص الكفاءة غير مهيأة."


def _no_competence(
    _db: Session, _user_id: uuid.UUID, _requirement: str, _at: date
) -> CompetenceVerdict:
    return CompetenceVerdict(None)


COMPETENCE: list[Callable[[Session, uuid.UUID, str, date], CompetenceVerdict]] = [_no_competence]


def competence_check(
    db: Session, user_id: uuid.UUID, requirement: str, at: date
) -> CompetenceVerdict:
    """The registered provider's verdict (Q2 replaces `COMPETENCE[0]`)."""
    return COMPETENCE[0](db, user_id, requirement, at)


# ---- handover dossier sections (Q1 engine) ------------------------------------------------------


@dataclass
class DossierSection:
    items: Callable[[Session, Any], list[Any]]
    blockers: Callable[[Session, Any], list[Blocker]] = lambda _db, _d: []
    title_en: str = ""
    title_ar: str = ""


DOSSIER_SECTIONS: dict[str, DossierSection] = {}


# ---- jobs (§4) -----------------------------------------------------------------------------------

JOB_SLOTS = ("quality_daily", "quality_alerts", "quality_weekly", "quality_monthly")


@dataclass
class JobDef:
    slot: str  # one of JOB_SLOTS
    run: Callable[[Session, datetime], dict[str, Any]]
    part: str = "Q0"


JOBS: dict[str, JobDef] = {}


# ---- export datasets, seeds, supplier gates, home tiles --------------------------------------

DATASETS: dict[str, Any] = {}  # 6g `Dataset` rows (app.services.scorecard.datasets)
SEEDS: dict[str, Callable[[Session], None]] = {}
SUPPLIER_GATES: list[Callable[[Session, QSupplier, str], list[Blocker]]] = []


@dataclass(frozen=True)
class HomeCount:
    code: str
    label_en: str
    label_ar: str
    value: int
    href: str | None = None
    tone: str = "neutral"


# extra counts on the Quality home (Q-NAV, §E.7 band): fn(db, principal, project) → counts
HOME_TILES: dict[str, Callable[[Session, Principal, Project], list[HomeCount]]] = {}
# extra read-only sections on the NCR page: fn(db, principal, ncr) → {title_en, title_ar, rows}
NCR_TABS: dict[str, Callable[[Session, Principal, QNcr], dict[str, Any]]] = {}


def register_record_type(rt: QRecordType, adapter: RecordTypeAdapter) -> None:
    RECORD_TYPES[rt] = adapter


def register_ncr_source(st: QNcrSourceType, source: NcrSource) -> None:
    NCR_SOURCES[st] = source


def register_job(code: str, job: JobDef) -> None:
    JOBS[code] = job
