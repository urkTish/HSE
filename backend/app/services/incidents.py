"""Incident register: create/edit, state machine §4.2, rules I-1…I-21, external notifications
(I-20), excluded-from-rates list (I-4, AC21). Injury cases and investigations live in
`injury_cases` / `investigations`."""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, any_, exists, false, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role, ZoneType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import (
    HIGHER_CONTROLS,
    AirsideFlag,
    CaseCategory,
    CaSourceType,
    CaStatus,
    ClassificationStatus,
    DangerousOccurrenceCategory,
    EnvReached,
    ExternalBody,
    IncidentStatus,
    IncidentType,
    InvestigationLevel,
    NotificationState,
    PermanentDisability,
    PersonType,
    RateExclusionReason,
    ReferenceList,
)
from app.models import (
    CorrectiveAction,
    ExternalNotification,
    HseSettings,
    Incident,
    InjuryCase,
    Investigation,
    Project,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.incidents import (
    DangerousOccurrenceRead,
    EnvironmentalRead,
    ExcludedCaseList,
    ExcludedCaseRow,
    ExternalNotificationRead,
    ExternalNotificationRecord,
    IncidentCreate,
    IncidentListItem,
    IncidentPage,
    IncidentRead,
    IncidentTransitionRequest,
    IncidentUpdate,
    InjuryCaseSummary,
    InvestigationSummary,
    LinkedCaSummary,
    PropertyDamageRead,
)
from app.services import audit, hse_settings, notify, projects
from app.services.common import ensure_open, invalid_transition, paginate, require_reason
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    contractor_reps,
    covers,
    id_warnings,
    make_ref,
    mark_restated,
    next_seq,
    notify_restated,
    project_role_users,
    project_today,
)
from app.services.permissions import Principal, deny, engagement_descendants, forbidden_error

ST = IncidentStatus
OPEN_CA = (CaStatus.open, CaStatus.in_progress, CaStatus.pending_verification)
DUE_DAYS = {InvestigationLevel.L1: 3, InvestigationLevel.L2: 7, InvestigationLevel.L3: 14}
LEVEL_RANK = {InvestigationLevel.L1: 1, InvestigationLevel.L2: 2, InvestigationLevel.L3: 3}
PD_L2_THRESHOLD = Decimal("50000")  # I-14 ASSUMPTION
GOSI_DAYS = 3  # I-20 VERIFY R5 (ASSUMPTION: 3 calendar days from occurrence)
L3_AIRSIDE = {
    AirsideFlag.runway_incursion,
    AirsideFlag.aircraft_involved,
    AirsideFlag.ols_infringement,
}
GACA_FLAGS = L3_AIRSIDE | {AirsideFlag.notam_breach}
RECORDABLE = {
    CaseCategory.FAT,
    CaseCategory.LTI,
    CaseCategory.RWC,
    CaseCategory.JTC,
    CaseCategory.MTC,
}
EDITABLE = (ST.draft, ST.reported, ST.under_investigation)
KPI_FIELDS = {
    "occurred_at",
    "site_id",
    "zone_id",
    "responsible_engagement_id",
    "incident_types",
    "primary_type",
    "work_related",
    "potential_severity",
    "actual_severity",
    "activity",
    "shift",
}


# ---- pure rules ----------------------------------------------------------------------------------


def tz_of(project: Project) -> ZoneInfo:
    return ZoneInfo(project.settings.timezone if project.settings else "Asia/Riyadh")


def local_date(project: Project, at: datetime) -> date:
    return at.astimezone(tz_of(project)).date()


def minimum_level(inc: Incident, cases: Iterable[InjuryCase]) -> InvestigationLevel:
    """I-14 (and I-13: HiPo ⇒ L3)."""
    cats = {c.category for c in cases}
    perm = any(c.permanent_disability != PermanentDisability.none for c in cases)
    flags = set(inc.airside_flags or [])
    types = set(inc.incident_types or [])
    if (
        cats & {CaseCategory.FAT, CaseCategory.LTI}
        or perm
        or IncidentType.dangerous_occurrence in types
        or inc.hipo
        or (
            IncidentType.environmental in types
            and inc.env_reached in (EnvReached.drain, EnvReached.water_body)
        )
        or flags & L3_AIRSIDE
    ):
        return InvestigationLevel.L3
    if (
        cats & {CaseCategory.RWC, CaseCategory.JTC, CaseCategory.MTC}
        or (inc.pd_estimated_cost_sar or Decimal(0)) >= PD_L2_THRESHOLD
        or flags
    ):
        return InvestigationLevel.L2
    return InvestigationLevel.L1


def exclusion_reasons(inc: Incident, case: InjuryCase | None, s: HseSettings) -> list[str]:
    """I-4: every reason a case (or a case-less event) is excluded from rates."""
    out: list[str] = []
    if inc.status == ST.draft:
        out.append(RateExclusionReason.incident_draft.value)
    if inc.status == ST.voided:
        out.append(RateExclusionReason.incident_voided.value)
    if not inc.work_related:
        out.append(RateExclusionReason.not_work_related.value)
    if case is not None:
        allowed = {PersonType.contractor_worker}
        if s.include_non_contractor_cases_in_rates:
            allowed.add(PersonType.client_pmc_staff)
        if case.person_type not in allowed:
            out.append(RateExclusionReason.non_contractor_person.value)
        if case.commuting and not s.include_commuting_in_rates:
            out.append(RateExclusionReason.commuting.value)
    return out


def open_lti(c: InjuryCase) -> bool:
    return c.category == CaseCategory.LTI and c.rtw_date is None and not c.fatal


@dataclass
class Required:
    body: ExternalBody
    reason: str
    due_at: datetime


def required_notifications(inc: Incident, cases: Sequence[InjuryCase]) -> list[Required]:
    """I-20 (deadlines ASSUMPTION/VERIFY). Draft and voided incidents require nothing."""
    if inc.status in (ST.draft, ST.voided):
        return []
    at = inc.occurred_at
    out: dict[ExternalBody, Required] = {}

    def need(body: ExternalBody, reason: str, due: datetime) -> None:
        if body not in out:
            out[body] = Required(body, reason, due)

    for c in sorted(cases, key=lambda x: x.person_no):
        cat = c.category
        if c.person_type == PersonType.contractor_worker and cat in RECORDABLE:
            need(
                ExternalBody.gosi,
                f"{cat.value} case P{c.person_no} (contractor worker)",
                at + timedelta(days=GOSI_DAYS),
            )
        if c.commuting:
            need(
                ExternalBody.gosi, f"Commuting case P{c.person_no}", at + timedelta(days=GOSI_DAYS)
            )
        if cat == CaseCategory.FAT or c.permanent_disability != PermanentDisability.none:
            what = "Fatality" if cat == CaseCategory.FAT else "Permanent disability"
            need(ExternalBody.mhrsd, f"{what} P{c.person_no}", at + timedelta(days=GOSI_DAYS))
        if cat == CaseCategory.FAT:
            need(ExternalBody.police, f"Fatality P{c.person_no}", at)
    if inc.do_category == DangerousOccurrenceCategory.fire_explosion:
        need(ExternalBody.civil_defense, "Fire/explosion dangerous occurrence", at)
    flags = {AirsideFlag(f) for f in inc.airside_flags or []} & GACA_FLAGS
    if flags:
        why = "Airside flag: " + ", ".join(sorted(f.value for f in flags))
        need(ExternalBody.gaca, why, at)
        need(ExternalBody.airport_operator, why, at)
    cats = {c.category for c in cases}
    client_why = None
    if CaseCategory.FAT in cats:
        client_why = "Fatality"
    elif CaseCategory.LTI in cats:
        client_why = "LTI case"
    elif IncidentType.dangerous_occurrence in (inc.incident_types or []):
        client_why = "Dangerous occurrence"
    elif inc.hipo:
        client_why = "HiPo incident"
    if client_why:
        need(ExternalBody.client, client_why, at + timedelta(hours=24))
    order = list(ExternalBody)
    return sorted(out.values(), key=lambda r: order.index(r.body))


def notification_reads(
    inc: Incident,
    cases: Sequence[InjuryCase],
    recorded: Sequence[ExternalNotification],
    refs: Refs,
    at: datetime | None = None,
) -> list[ExternalNotificationRead]:
    t = at or now()
    req = {r.body: r for r in required_notifications(inc, cases)}
    rec = {ExternalBody(n.body): n for n in recorded}
    out = []
    for body in ExternalBody:
        r, n = req.get(body), rec.get(body)
        if r is None and n is None:
            continue
        state = None
        if n is not None:
            state = NotificationState.done
        elif r is not None:
            state = NotificationState.overdue if t > r.due_at else NotificationState.due
        out.append(
            ExternalNotificationRead(
                body=body,
                required=r is not None,
                required_reason=r.reason if r else None,
                due_at=r.due_at if r else None,
                state=state,
                notified_at=n.notified_at if n else None,
                reference_no=n.reference_no if n else None,
                notified_by=refs.user(n.notified_by_user_id) if n else None,
            )
        )
    return out


def ca_overdue(ca: CorrectiveAction, day: date) -> bool:
    return ca.status in (CaStatus.open, CaStatus.in_progress) and day > ca.due_date


# ---- loading -------------------------------------------------------------------------------------


@dataclass
class Bundle:
    inc: Incident
    project: Project
    cases: list[InjuryCase]
    inv: Investigation | None
    recorded: list[ExternalNotification]
    cas: list[CorrectiveAction]


def load_cases(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[InjuryCase]]:
    out: dict[uuid.UUID, list[InjuryCase]] = defaultdict(list)
    if ids:
        for c in db.scalars(
            select(InjuryCase).where(InjuryCase.incident_id.in_(ids)).order_by(InjuryCase.person_no)
        ):
            out[c.incident_id].append(c)
    return out


def linked_cas(db: Session, incident_id: uuid.UUID) -> list[CorrectiveAction]:
    return list(
        db.scalars(
            select(CorrectiveAction)
            .where(
                CorrectiveAction.source_type == CaSourceType.incident,
                CorrectiveAction.source_id == incident_id,
            )
            .order_by(CorrectiveAction.seq)
        )
    )


def bundle(db: Session, inc: Incident) -> Bundle:
    project = db.get(Project, inc.project_id)
    assert project is not None  # noqa: S101
    return Bundle(
        inc=inc,
        project=project,
        cases=load_cases(db, [inc.id]).get(inc.id, []),
        inv=db.get(Investigation, inc.id),
        recorded=list(
            db.scalars(
                select(ExternalNotification).where(ExternalNotification.incident_id == inc.id)
            )
        ),
        cas=linked_cas(db, inc.id),
    )


# ---- visibility ----------------------------------------------------------------------------------


def _involved(p: Principal, inc: Incident, inv: Investigation | None) -> bool:
    uid = p.user.id
    if uid in (inc.created_by_user_id, inc.reported_by_user_id):
        return True
    return inv is not None and (
        uid == inv.lead_investigator_id or uid in (inv.team_member_ids or [])
    )


def can_view(
    p: Principal, inc: Incident, cases: Sequence[InjuryCase], inv: Investigation | None
) -> bool:
    if _involved(p, inc, inv):
        return True
    if inc.status == ST.draft and p.grant(inc.project_id, Capability.incident_classify) is None:
        return False
    g = p.grant(inc.project_id, Capability.incident_view)
    if g is None or not g.covers_site(inc.site_id):
        return False
    if g.engagement_ids is None:
        return True
    engs = {inc.responsible_engagement_id} | {c.employer_engagement_id for c in cases}
    return any(e is not None and e in g.engagement_ids for e in engs)


def get_incident(db: Session, p: Principal, incident_id: uuid.UUID) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise deny(db, p, EntityType.incident, incident_id, None, "Incident")
    cases = load_cases(db, [inc.id]).get(inc.id, [])
    if not can_view(p, inc, cases, db.get(Investigation, inc.id)):
        raise deny(db, p, EntityType.incident, incident_id, inc.project_id, "Incident")
    return inc


def scoped_query(db: Session, p: Principal, project: Project) -> Select[Any]:
    """Incidents of a project the caller may list (de-identified register, capability 31)."""
    stmt = select(Incident).where(Incident.project_id == project.id)
    uid = p.user.id
    own = or_(Incident.created_by_user_id == uid, Incident.reported_by_user_id == uid)
    inv_mine = exists().where(
        Investigation.incident_id == Incident.id,
        or_(Investigation.lead_investigator_id == uid, any_(Investigation.team_member_ids) == uid),
    )
    g = p.grant(project.id, Capability.incident_view)
    if g is None:
        return stmt.where(or_(own, inv_mine))
    conds: list[Any] = []
    if g.site_ids is not None:
        conds.append(Incident.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        conds.append(
            or_(
                Incident.responsible_engagement_id.in_(engs),
                exists().where(
                    InjuryCase.incident_id == Incident.id,
                    InjuryCase.employer_engagement_id.in_(engs),
                ),
            )
            if engs
            else false()
        )
    if p.grant(project.id, Capability.incident_classify) is None:
        conds.append(Incident.status != ST.draft)
    if conds:
        stmt = stmt.where(or_(and_(*conds), own, inv_mine))
    return stmt


# ---- read models ---------------------------------------------------------------------------------


def person_label(c: InjuryCase, refs: Refs, trades: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """P1-2: 'Person 1 · scaffolder · NAJD' (no name, no ID)."""
    eng = refs.eng(c.employer_engagement_id)
    who = eng.short_code if eng else c.person_type.value.replace("_", " ")
    trade_ar = trades.get(c.trade.value, ("", c.trade.value))[1]
    return (
        f"Person {c.person_no} · {c.trade.value.replace('_', ' ')} · {who}",
        f"الشخص {c.person_no} · {trade_ar} · {who}",
    )


def case_summary(
    c: InjuryCase, inc: Incident, s: HseSettings, refs: Refs, trades: dict[str, tuple[str, str]]
) -> InjuryCaseSummary:
    en, ar = person_label(c, refs, trades)
    reasons = exclusion_reasons(inc, c, s)
    return InjuryCaseSummary(
        id=c.id,
        case_no=f"{inc.ref}-P{c.person_no}",
        display_label=en,
        display_label_ar=ar,
        person_type=c.person_type,
        trade=c.trade,
        employer=refs.eng(c.employer_engagement_id),
        mechanism=c.mechanism,
        agency=c.agency,
        case_category=c.category,
        classification_status=c.classification_status,
        excluded_from_rates=bool(reasons),
        exclusion_reasons=[RateExclusionReason(r) for r in reasons],
        open_lti=open_lti(c),
    )


def allowed_transitions(p: Principal, b: Bundle) -> list[IncidentStatus]:
    out = []
    for to in IncidentStatus:
        try:
            _authorise(p, b, to)
        except ApiError:
            continue
        out.append(to)
    return out


def to_read(
    db: Session, p: Principal, b: Bundle, warnings: list[ApiWarning] | None = None
) -> IncidentRead:
    inc = b.inc
    s = hse_settings.get(db, inc.project_id)
    refs = Refs(db).load(
        sites=[inc.site_id],
        zones=[inc.zone_id],
        engs=[inc.responsible_engagement_id, *[c.employer_engagement_id for c in b.cases]],
        users=[
            inc.reported_by_user_id,
            b.inv.lead_investigator_id if b.inv else None,
            *[n.notified_by_user_id for n in b.recorded],
        ],
    )
    trades = hse_settings.labels(db, ReferenceList.trade)
    day = project_today(b.project)
    inv_sum = None
    if b.inv is not None:
        inv_sum = InvestigationSummary(
            level=b.inv.level,
            lead_investigator=refs.user(b.inv.lead_investigator_id),
            due_date=b.inv.due_date,
            overdue=investigation_overdue(inc, b.inv, day),
            submitted_at=b.inv.submitted_at,
            approved_at=b.inv.approved_at,
        )
    return IncidentRead(
        id=inc.id,
        ref=inc.ref,
        project_id=inc.project_id,
        site=refs.site(inc.site_id),
        zone=refs.zone(inc.zone_id),
        location_detail=inc.location_detail,
        responsible_engagement=refs.eng(inc.responsible_engagement_id),
        occurred_at=inc.occurred_at,
        reported_at=inc.reported_at,
        reported_by=refs.user(inc.reported_by_user_id),
        shift=inc.shift,
        incident_types=[IncidentType(t) for t in inc.incident_types],
        primary_type=inc.primary_type,
        title=inc.title,
        description=inc.description,
        immediate_actions=inc.immediate_actions,
        activity=inc.activity,
        work_related=inc.work_related,
        not_work_related_reason=inc.not_work_related_reason,
        work_related_rationale=inc.work_related_rationale,
        actual_severity=inc.actual_severity,
        potential_severity=inc.potential_severity,
        hipo=inc.hipo,
        late_report=inc.late_report,
        ambient_temp_c=inc.ambient_temp_c,
        airside_flags=[AirsideFlag(f) for f in inc.airside_flags],
        property_damage=(
            PropertyDamageRead(
                asset_type=inc.pd_asset_type,
                estimated_cost_sar=inc.pd_estimated_cost_sar or Decimal(0),
            )
            if inc.pd_asset_type
            else None
        ),
        environmental=(
            EnvironmentalRead(
                category=inc.env_category,
                substance=inc.env_substance,
                quantity_l=inc.env_quantity_l,
                contained=bool(inc.env_contained),
                reached=inc.env_reached or EnvReached.none,
            )
            if inc.env_category
            else None
        ),
        dangerous_occurrence=(
            DangerousOccurrenceRead(category=inc.do_category) if inc.do_category else None
        ),
        status=inc.status,
        void_reason=inc.void_reason,
        minimum_investigation_level=minimum_level(inc, b.cases),
        cases=[case_summary(c, inc, s, refs, trades) for c in b.cases],
        investigation=inv_sum,
        external_notifications=notification_reads(inc, b.cases, b.recorded, refs),
        corrective_actions=[
            LinkedCaSummary(
                id=ca.id,
                ref=ca.ref,
                title=ca.title,
                status=ca.status,
                control_level=ca.control_level,
                due_date=ca.due_date,
                overdue=ca_overdue(ca, day),
            )
            for ca in b.cas
        ],
        allowed_transitions=allowed_transitions(p, b),
        warnings=warnings or [],
        created_at=inc.created_at,
        updated_at=inc.updated_at,
    )


def investigation_overdue(inc: Incident, inv: Investigation, day: date) -> bool:
    return (
        inv.due_date is not None
        and inv.submitted_at is None
        and inc.status in (ST.reported, ST.under_investigation)
        and day > inv.due_date
    )


def read(db: Session, p: Principal, incident_id: uuid.UUID) -> IncidentRead:
    return to_read(db, p, bundle(db, get_incident(db, p, incident_id)))


# ---- validation ----------------------------------------------------------------------------------


def _apply_fields(db: Session, project: Project, inc: Incident, data: dict[str, Any]) -> None:
    simple = (
        "location_detail",
        "shift",
        "title",
        "description",
        "immediate_actions",
        "activity",
        "work_related",
        "not_work_related_reason",
        "work_related_rationale",
        "actual_severity",
        "potential_severity",
        "ambient_temp_c",
        "primary_type",
    )
    for k in simple:
        if k in data:
            setattr(inc, k, data[k])
    if "site_id" in data:
        inc.site_id = data["site_id"]
    if "zone_id" in data:
        inc.zone_id = data["zone_id"]
    if "responsible_engagement_id" in data:
        inc.responsible_engagement_id = data["responsible_engagement_id"]
    if "occurred_at" in data:
        inc.occurred_at = data["occurred_at"]
        inc.occurred_date = local_date(project, inc.occurred_at)
    if "incident_types" in data:
        inc.incident_types = [IncidentType(t).value for t in data["incident_types"]]
    if "airside_flags" in data:
        inc.airside_flags = [AirsideFlag(f).value for f in data["airside_flags"] or []]
    if "property_damage" in data:
        pd = data["property_damage"]
        inc.pd_asset_type = pd["asset_type"] if pd else None
        inc.pd_estimated_cost_sar = pd["estimated_cost_sar"] if pd else None
    if "environmental" in data:
        env = data["environmental"]
        inc.env_category = env["category"] if env else None
        inc.env_substance = env.get("substance") if env else None
        inc.env_quantity_l = env.get("quantity_l") if env else None
        inc.env_contained = env["contained"] if env else None
        inc.env_reached = env["reached"] if env else None
    if "dangerous_occurrence" in data:
        do = data["dangerous_occurrence"]
        inc.do_category = do["category"] if do else None


def near_miss_error() -> ApiError:
    return ApiError(
        422,
        ErrorCode.NEAR_MISS_EXCLUSIVE,
        "A near miss cannot be combined with any other incident type.",
        "لا يمكن الجمع بين الحادث الوشيك وأي نوع آخر.",
    )


def _validate_shape(db: Session, project: Project, inc: Incident) -> None:
    """Rules that hold for drafts too (I-3, I-18, hierarchy, ≤ now)."""
    types = set(inc.incident_types)
    if IncidentType.near_miss.value in types and len(types) > 1:
        raise near_miss_error()
    if inc.primary_type.value not in types:
        raise validation_error("primary_type", "The primary type must be one of incident_types.")
    _, zone = check_site_zone(db, project, inc.site_id, inc.zone_id)
    if inc.responsible_engagement_id is not None:
        check_engagement(db, project, inc.responsible_engagement_id, "responsible_engagement_id")
    if inc.occurred_at > now() + timedelta(minutes=5):
        raise validation_error("occurred_at", "The incident cannot be in the future.")
    if inc.airside_flags and (zone is None or zone.zone_type != ZoneType.airside):
        raise validation_error("airside_flags", "Airside flags are only allowed for airside zones.")
    if (
        inc.actual_severity is not None
        and inc.potential_severity is not None
        and inc.potential_severity < inc.actual_severity
    ):
        raise validation_error(
            "potential_severity", "Potential severity must be at least the actual severity."
        )
    if not inc.work_related and inc.not_work_related_reason is None and inc.status != ST.draft:
        raise validation_error("not_work_related_reason", "Give the OSHA 1904.5 exception.")
    for t, attr, field in (
        (IncidentType.property_damage, "pd_asset_type", "property_damage"),
        (IncidentType.environmental, "env_category", "environmental"),
        (IncidentType.dangerous_occurrence, "do_category", "dangerous_occurrence"),
    ):
        if t.value not in types and getattr(inc, attr) is not None:
            raise validation_error(field, f"{field} is only allowed for {t.value} incidents.")


def missing_for_report(inc: Incident, cases: Sequence[InjuryCase]) -> list[str]:
    missing = [
        f
        for f in (
            "responsible_engagement_id",
            "shift",
            "description",
            "immediate_actions",
            "activity",
            "actual_severity",
            "potential_severity",
        )
        if getattr(inc, f) in (None, "")
    ]
    types = set(inc.incident_types)
    if not inc.work_related and inc.not_work_related_reason is None:
        missing.append("not_work_related_reason")
    if IncidentType.property_damage.value in types and inc.pd_asset_type is None:
        missing.append("property_damage")
    if IncidentType.environmental.value in types and inc.env_category is None:
        missing.append("environmental")
    if IncidentType.dangerous_occurrence.value in types and inc.do_category is None:
        missing.append("dangerous_occurrence")
    return missing


def text_warnings(inc: Incident) -> list[ApiWarning]:
    return id_warnings(
        title=inc.title,
        description=inc.description,
        immediate_actions=inc.immediate_actions,
        location_detail=inc.location_detail,
        work_related_rationale=inc.work_related_rationale,
    )


# ---- create / update / delete --------------------------------------------------------------------


def snapshot(inc: Incident) -> dict[str, Any]:
    keys = (
        "site_id",
        "zone_id",
        "responsible_engagement_id",
        "occurred_at",
        "shift",
        "incident_types",
        "primary_type",
        "title",
        "activity",
        "work_related",
        "not_work_related_reason",
        "actual_severity",
        "potential_severity",
        "airside_flags",
        "pd_asset_type",
        "pd_estimated_cost_sar",
        "env_category",
        "env_reached",
        "do_category",
        "status",
        "void_reason",
    )
    return {k: getattr(inc, k) for k in keys}


def create(db: Session, p: Principal, project_id: uuid.UUID, body: IncidentCreate) -> IncidentRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    g = p.require(project.id, Capability.incident_report)
    if not covers(g, body.site_id, body.responsible_engagement_id if g.engagement_ids else None):
        if g.engagement_ids is not None and body.responsible_engagement_id is None:
            raise validation_error(
                "responsible_engagement_id", "Choose your contractor as the responsible party."
            )
        raise forbidden_error("This site or contractor is outside your scope.")
    data = body.model_dump()
    year = local_date(project, body.occurred_at).year
    seq = next_seq(db, Incident, project.id, year)
    inc = Incident(
        project_id=project.id,
        ref=make_ref("INC", project.code, year, seq, 4),
        year=year,
        seq=seq,
        site_id=body.site_id,
        occurred_at=body.occurred_at,
        occurred_date=local_date(project, body.occurred_at),
        primary_type=body.primary_type,
        title=body.title,
        status=ST.draft,
        created_by_user_id=p.user.id,
        incident_types=[],
        airside_flags=[],
        alerts_sent=[],
    )
    _apply_fields(db, project, inc, data)
    _validate_shape(db, project, inc)
    db.add(inc)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=project.id,
        after=snapshot(inc),
    )
    return to_read(db, p, bundle(db, inc), text_warnings(inc))


def can_edit(p: Principal, b: Bundle) -> bool:
    inc = b.inc
    if inc.status not in EDITABLE:
        return False
    g = p.grant(inc.project_id, Capability.incident_classify)
    if covers(g, inc.site_id, None):
        return True
    return inc.status == ST.draft and inc.created_by_user_id == p.user.id


def restate_if_locked(
    db: Session, p: Principal | None, b: Bundle, days: Iterable[date], what_en: str, what_ar: str
) -> None:
    """I-9 / W-10: a KPI-relevant change touching a month that was ever locked."""
    for d in sorted(set(days)):
        if mark_restated(db, p, b.project.id, d, what_en):
            notify_restated(db, b.project, d, what_en, what_ar)


def update(db: Session, p: Principal, incident_id: uuid.UUID, body: IncidentUpdate) -> IncidentRead:
    inc = get_incident(db, p, incident_id)
    b = bundle(db, inc)
    ensure_open(b.project)
    p.ensure_writer()
    if inc.status not in EDITABLE:
        raise invalid_transition("Incident", inc.status, "edited")
    if not can_edit(p, b):
        raise forbidden_error()
    before = snapshot(inc)
    old_day = inc.occurred_date
    changes = body.changes()
    _apply_fields(db, b.project, inc, changes)
    _validate_shape(db, b.project, inc)
    if inc.status != ST.draft:
        missing = missing_for_report(inc, b.cases)
        if missing:
            raise validation_error(missing[0], f"{missing[0]} is required once reported.")
    inc.updated_at = now()
    db.flush()
    diff_before, diff_after = audit.diff(before, snapshot(inc))
    if diff_after:
        audit.record(
            db,
            AuditAction.update,
            p.actor(inc.project_id),
            entity_type=EntityType.incident,
            entity_id=inc.id,
            project_id=inc.project_id,
            before=diff_before,
            after=diff_after,
        )
    if inc.status != ST.draft and KPI_FIELDS & set(diff_after):
        restate_if_locked(
            db, p, b, {old_day, inc.occurred_date}, f"{inc.ref} edited", f"تعديل {inc.ref}"
        )
    return to_read(db, p, bundle(db, inc), text_warnings(inc))


def delete(db: Session, p: Principal, incident_id: uuid.UUID) -> None:
    inc = get_incident(db, p, incident_id)
    p.ensure_writer()
    if inc.status != ST.draft:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Reported incidents cannot be deleted; void them with a reason (I-1).",
            "لا يمكن حذف حادثة مُبلَّغ عنها؛ يمكن إلغاؤها مع ذكر السبب.",
        )
    if inc.created_by_user_id != p.user.id:
        raise forbidden_error("Only the creator may delete a draft.")
    for c in load_cases(db, [inc.id]).get(inc.id, []):
        db.delete(c)
    audit.record(
        db,
        AuditAction.archive,
        p.actor(inc.project_id),
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=inc.project_id,
        before=snapshot(inc),
        details={"deleted_draft": True},
    )
    db.delete(inc)
    db.flush()


# ---- state machine (§4.2) ------------------------------------------------------------------------


def _approver_ok(p: Principal, b: Bundle) -> bool:
    g = p.grant(b.inc.project_id, Capability.investigation_approve)
    if not covers(g, b.inc.site_id, None):
        return False
    level = b.inv.level if b.inv else InvestigationLevel.L1
    return level != InvestigationLevel.L3 or p.is_manager


def _authorise(p: Principal, b: Bundle, to: IncidentStatus) -> None:
    """Who may trigger the transition (conditions are checked separately). Raises 409 for an
    edge not in §4.2 and 403 when the caller may not trigger it."""
    inc = b.inc
    src = inc.status
    classify = covers(p.grant(inc.project_id, Capability.incident_classify), inc.site_id, None)
    edges: dict[tuple[IncidentStatus, IncidentStatus], bool] = {
        (ST.draft, ST.reported): inc.created_by_user_id == p.user.id or classify,
        (ST.reported, ST.under_investigation): classify,
        (ST.reported, ST.closed): classify,
        (ST.under_investigation, ST.pending_review): (
            (b.inv is not None and b.inv.lead_investigator_id == p.user.id) or p.is_manager
        ),
        (ST.pending_review, ST.under_investigation): _approver_ok(p, b),
        (ST.pending_review, ST.actions_pending): _approver_ok(p, b),
        (ST.pending_review, ST.closed): _approver_ok(p, b),
        (ST.actions_pending, ST.closed): _approver_ok(p, b),
        (ST.reported, ST.voided): classify,
        (ST.under_investigation, ST.voided): classify,
        (ST.closed, ST.under_investigation): p.is_manager,
        (ST.voided, ST.reported): p.is_manager,
    }
    allowed = edges.get((src, to))
    if allowed is None:
        raise invalid_transition("Incident", src, to)
    if src == ST.draft and inc.created_by_user_id == p.user.id:
        p.ensure_writer()
        return
    p.require(
        inc.project_id, Capability.incident_report if src == ST.draft else Capability.incident_view
    )
    if not allowed:
        raise forbidden_error()


def _cases_confirmed(b: Bundle) -> None:
    if any(c.classification_status != ClassificationStatus.confirmed for c in b.cases):
        raise ApiError(
            409,
            ErrorCode.CASES_NOT_CONFIRMED,
            "Confirm the category of every injury case first.",
            "يجب تأكيد تصنيف جميع حالات الإصابة أولاً.",
        )


def _higher_control(b: Bundle, justification: str | None) -> None:
    """I-17: potential severity ≥ 4 needs ≥ 1 elimination/substitution/engineering CA, or the
    approver's justification."""
    if (b.inc.potential_severity or 0) < 4:
        return
    live = [ca for ca in b.cas if ca.status != CaStatus.cancelled]
    if any(ca.control_level in HIGHER_CONTROLS for ca in live):
        return
    if justification and len(justification.strip()) >= 20:
        b.inc.higher_control_justification = justification.strip()
        return
    raise ApiError(
        409,
        ErrorCode.HIGHER_CONTROL_REQUIRED,
        "Potential severity ≥ 4 needs at least one elimination, substitution or engineering "
        "control, or a justification why none is reasonably practicable (I-17).",
        "الشدة المحتملة ≥ 4 تتطلب إجراء تحكم من مستوى الإزالة أو الاستبدال أو الهندسي، أو "
        "تبريراً لعدم إمكانيته.",
    )


def _report_alerts(db: Session, b: Bundle) -> None:
    """§7: who is told when an incident becomes Reported (no names, P6)."""
    inc = b.inc
    cats = {c.category for c in b.cases}
    pid = inc.project_id
    severe = (
        CaseCategory.FAT in cats
        or any(c.permanent_disability != PermanentDisability.none for c in b.cases)
        or IncidentType.dangerous_occurrence.value in inc.incident_types
        or inc.hipo
        or {AirsideFlag.runway_incursion.value, AirsideFlag.aircraft_involved.value}
        & set(inc.airside_flags)
    )
    reps = contractor_reps(db, pid, inc.responsible_engagement_id)
    officers = project_role_users(db, pid, Role.hse_officer)
    recipients = set(officers) | set(reps)
    if severe:
        recipients |= set(notify.managers(db)) | set(
            project_role_users(db, pid, Role.viewer_client)
        )
    elif cats & RECORDABLE:
        recipients |= set(notify.managers(db))
    worst = next(
        (
            c.value
            for c in (
                CaseCategory.FAT,
                CaseCategory.LTI,
                CaseCategory.RWC,
                CaseCategory.JTC,
                CaseCategory.MTC,
                CaseCategory.FAC,
            )
            if c in cats
        ),
        inc.primary_type.value,
    )
    hipo = " · HiPo" if inc.hipo else ""
    notify.notify(
        db,
        recipients,
        NotificationKind.incident_reported,
        f"{inc.ref} reported: {worst}{hipo}",
        f"تم الإبلاغ عن {inc.ref}: {worst}{hipo}",
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=pid,
    )
    req = required_notifications(inc, b.cases)
    if req:
        bodies = ", ".join(r.body.value for r in req)
        notify.notify(
            db,
            set(officers) | set(reps),
            NotificationKind.external_notification_due,
            f"{inc.ref}: external notifications required ({bodies})",
            f"{inc.ref}: إخطارات خارجية مطلوبة ({bodies})",
            entity_type=EntityType.incident,
            entity_id=inc.id,
            project_id=pid,
        )


def transition(
    db: Session, p: Principal, incident_id: uuid.UUID, body: IncidentTransitionRequest
) -> IncidentRead:
    from app.services import investigations  # noqa: PLC0415 (circular)

    inc = get_incident(db, p, incident_id)
    b = bundle(db, inc)
    ensure_open(b.project)
    to = body.to_status
    _authorise(p, b, to)
    src = inc.status
    before = snapshot(inc)
    details: dict[str, Any] = {"from": src.value, "to": to.value}
    counted_change = False
    if src == ST.draft and to == ST.reported:
        missing = missing_for_report(inc, b.cases)
        types = set(inc.incident_types)
        if IncidentType.near_miss.value in types and len(types) > 1:
            raise near_miss_error()
        if IncidentType.injury_illness.value in types and not b.cases:
            raise ApiError(
                422,
                ErrorCode.INJURY_CASE_REQUIRED,
                "Add at least one injured or ill person before reporting (I-2).",
                "أضف شخصاً مصاباً واحداً على الأقل قبل الإبلاغ.",
            )
        if missing:
            raise validation_error(missing[0], f"{missing[0]} is required to report.")
        _validate_shape(db, b.project, inc)
        inc.reported_at = now()
        inc.reported_by_user_id = p.user.id
        counted_change = True
    elif src == ST.reported and to == ST.under_investigation:
        if body.investigation is None:
            raise validation_error("investigation", "Set the investigation level and lead.")
        investigations.assign(db, b, body.investigation)
    elif src == ST.reported and to == ST.closed:
        if minimum_level(inc, b.cases) != InvestigationLevel.L1:
            raise ApiError(
                409,
                ErrorCode.INVESTIGATION_LEVEL_TOO_LOW,
                "Only L1 incidents can be quick-closed; this one needs an investigation.",
                "يمكن الإغلاق السريع لحوادث المستوى الأول فقط.",
            )
        if not inc.immediate_actions:
            raise validation_error("immediate_actions", "Immediate actions are required.")
        if any(ca.status in OPEN_CA for ca in b.cas):
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "Open corrective actions exist; investigate instead of quick close.",
                "توجد إجراءات تصحيحية مفتوحة.",
            )
        _cases_confirmed(b)
        inc.status_reason = require_reason(body.reason, "quick-close the incident")
        inc.closed_at = now()
        details["quick_close"] = True
    elif src == ST.under_investigation and to == ST.pending_review:
        assert b.inv is not None  # noqa: S101
        investigations.submit(db, b)
    elif src == ST.pending_review and to == ST.under_investigation:
        assert b.inv is not None  # noqa: S101
        b.inv.returned_comment = require_reason(body.reason, "return the investigation")
        b.inv.submitted_at = None
    elif src == ST.pending_review and to in (ST.actions_pending, ST.closed):
        assert b.inv is not None  # noqa: S101
        if b.inv.lead_investigator_id == p.user.id:
            raise ApiError(
                403,
                ErrorCode.APPROVER_IS_LEAD,
                "The lead investigator cannot approve their own investigation.",
                "لا يمكن لقائد التحقيق اعتماد تحقيقه.",
            )
        _cases_confirmed(b)
        _higher_control(b, body.higher_control_justification)
        open_cas = [ca for ca in b.cas if ca.status in OPEN_CA]
        if to == ST.actions_pending and not open_cas:
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "No open corrective action: close the incident instead.",
                "لا توجد إجراءات مفتوحة: أغلق الحادثة.",
            )
        if to == ST.closed and open_cas:
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "Corrective actions are still open: move to Actions Pending.",
                "لا تزال هناك إجراءات تصحيحية مفتوحة.",
            )
        b.inv.approved_by_user_id = p.user.id
        b.inv.approved_at = now()
        b.inv.returned_comment = None
        if to == ST.closed:
            inc.closed_at = now()
    elif src == ST.actions_pending and to == ST.closed:
        if any(ca.status in OPEN_CA for ca in b.cas):
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "Corrective actions are still open.",
                "لا تزال هناك إجراءات تصحيحية مفتوحة.",
            )
        inc.closed_at = now()
    elif to == ST.voided:
        inc.void_reason = require_reason(body.reason, "void the incident")
        counted_change = True
    elif src == ST.closed and to == ST.under_investigation:
        inc.status_reason = require_reason(body.reason, "reopen the incident")
        inc.closed_at = None
        if b.inv is not None:
            b.inv.approved_at = None
            b.inv.approved_by_user_id = None
            b.inv.submitted_at = None
        else:
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "This incident was quick-closed without an investigation; un-close is not "
                "possible. Create a new investigation by voiding and re-reporting.",
                "أُغلقت الحادثة دون تحقيق.",
            )
    elif src == ST.voided and to == ST.reported:
        inc.status_reason = require_reason(body.reason, "un-void the incident")
        inc.void_reason = None
        counted_change = True
    inc.status = to
    inc.updated_at = now()
    db.flush()
    if body.reason:
        details["reason"] = body.reason
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(inc.project_id),
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=inc.project_id,
        before={"status": before["status"]},
        after={"status": to},
        details=details,
    )
    if src == ST.draft and to == ST.reported:
        _report_alerts(db, b)
    if to in (ST.reported, ST.voided):
        from app.services.med import holds as med_holds  # noqa: PLC0415

        med_holds.on_incident_status(db, inc, p)
    if counted_change:
        restate_if_locked(
            db, p, b, [inc.occurred_date], f"{inc.ref} {to.value}", f"{inc.ref} تغيرت حالته"
        )
    return to_read(db, p, bundle(db, inc))


def settle_after_ca(db: Session, incident_id: uuid.UUID) -> None:
    """§4.2: Actions Pending → Closed by the system once the last CA is Closed/Cancelled (AC25)."""
    inc = db.get(Incident, incident_id)
    if inc is None or inc.status != ST.actions_pending:
        return
    if any(ca.status in OPEN_CA for ca in linked_cas(db, incident_id)):
        return
    inc.status = ST.closed
    inc.closed_at = now()
    inc.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        audit.SYSTEM,
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=inc.project_id,
        before={"status": ST.actions_pending},
        after={"status": ST.closed},
        details={"auto": "last corrective action closed"},
    )


# ---- external notifications ----------------------------------------------------------------------


def record_notification(
    db: Session,
    p: Principal,
    incident_id: uuid.UUID,
    body: ExternalBody,
    payload: ExternalNotificationRecord,
) -> ExternalNotificationRead:
    inc = get_incident(db, p, incident_id)
    b = bundle(db, inc)
    ensure_open(b.project)
    g = p.require(inc.project_id, Capability.incident_classify)
    if not covers(g, inc.site_id, None):
        raise forbidden_error()
    if inc.status in (ST.draft, ST.voided):
        raise invalid_transition("Incident", inc.status, "notified")
    if payload.notified_at > now() + timedelta(minutes=5):
        raise validation_error("notified_at", "The notification time cannot be in the future.")
    row = db.get(ExternalNotification, (inc.id, body))
    before = None
    if row is None:
        row = ExternalNotification(incident_id=inc.id, body=body, alerts_sent=[])
        db.add(row)
    else:
        before = {"notified_at": row.notified_at, "reference_no": row.reference_no}
    row.notified_at = payload.notified_at
    row.reference_no = payload.reference_no
    row.notified_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(inc.project_id),
        entity_type=EntityType.incident,
        entity_id=inc.id,
        project_id=inc.project_id,
        before=before,
        after={"notified_at": row.notified_at, "reference_no": row.reference_no},
        details={"external_notification": body.value},
    )
    b = bundle(db, inc)
    refs = Refs(db)
    return next(n for n in notification_reads(inc, b.cases, b.recorded, refs) if n.body == body)


# ---- register listing ----------------------------------------------------------------------------


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[IncidentStatus] | None = None,
    incident_types: list[IncidentType] | None = None,
    case_categories: list[CaseCategory] | None = None,
    classification_status: ClassificationStatus | None = None,
    site_ids: list[uuid.UUID] | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    activity: Any = None,
    mechanism: Any = None,
    airside_flag: AirsideFlag | None = None,
    hipo: bool | None = None,
    late_report: bool | None = None,
    investigation_level: InvestigationLevel | None = None,
    investigation_overdue_: bool | None = None,
    unclassified_over_hours: int | None = None,
    notification_due: bool | None = None,
    open_lti_: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    sort: str = "-occurred_at",
) -> IncidentPage:
    project = projects.get_visible(db, p, project_id)
    Inc = Incident  # noqa: N806
    stmt = scoped_query(db, p, project)
    # AC26: voided incidents are listed only on request
    stmt = stmt.where(Inc.status.in_(statuses) if statuses else Inc.status != ST.voided)
    if incident_types:
        stmt = stmt.where(Inc.incident_types.overlap([t.value for t in incident_types]))
    case_conds: list[Any] = []
    if case_categories:
        cats = [c.value for c in case_categories]
        case_conds.append(
            or_(
                InjuryCase.confirmed_category.in_(cats),
                and_(
                    InjuryCase.confirmed_category.is_(None), InjuryCase.derived_category.in_(cats)
                ),
            )
        )
    if classification_status:
        case_conds.append(InjuryCase.classification_status == classification_status)
    if mechanism:
        case_conds.append(InjuryCase.mechanism == mechanism)
    if open_lti_ is not None:
        lti = exists().where(
            InjuryCase.incident_id == Inc.id,
            or_(
                InjuryCase.confirmed_category == CaseCategory.LTI,
                and_(
                    InjuryCase.confirmed_category.is_(None),
                    InjuryCase.derived_category == CaseCategory.LTI,
                ),
            ),
            InjuryCase.rtw_date.is_(None),
            InjuryCase.fatal.is_(False),
        )
        stmt = stmt.where(lti if open_lti_ else ~lti)
    if case_conds:
        stmt = stmt.where(exists().where(InjuryCase.incident_id == Inc.id, *case_conds))
    if site_ids:
        stmt = stmt.where(Inc.site_id.in_(site_ids))
    if zone_ids:
        stmt = stmt.where(Inc.zone_id.in_(zone_ids))
    if engagement_ids:
        engs: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                engs |= engagement_descendants(db, e)
        stmt = stmt.where(Inc.responsible_engagement_id.in_(engs))
    if activity:
        stmt = stmt.where(Inc.activity == activity)
    if airside_flag:
        stmt = stmt.where(any_(Inc.airside_flags) == airside_flag.value)
    if hipo is not None:
        stmt = stmt.where(
            (Inc.potential_severity >= 4)
            if hipo
            else or_(Inc.potential_severity.is_(None), Inc.potential_severity < 4)
        )
    if late_report is not None:
        late = and_(
            Inc.reported_at.is_not(None), Inc.reported_at - Inc.occurred_at > timedelta(hours=24)
        )
        stmt = stmt.where(late if late_report else ~late)
    if investigation_level or investigation_overdue_ is not None:
        stmt = stmt.join(Investigation, Investigation.incident_id == Inc.id)
        if investigation_level:
            stmt = stmt.where(Investigation.level == investigation_level)
        if investigation_overdue_ is not None:
            od = and_(
                Investigation.due_date < project_today(project),
                Investigation.submitted_at.is_(None),
                Inc.status.in_([ST.reported, ST.under_investigation]),
            )
            stmt = stmt.where(od if investigation_overdue_ else ~od)
    if unclassified_over_hours:
        stmt = stmt.where(
            Inc.status == ST.reported,
            Inc.reported_at < now() - timedelta(hours=unclassified_over_hours),
        )
    if date_from:
        stmt = stmt.where(Inc.occurred_date >= date_from)
    if date_to:
        stmt = stmt.where(Inc.occurred_date <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Inc.ref.ilike(like), Inc.title.ilike(like)))
    if notification_due is not None:
        cand = list(db.scalars(stmt.where(Inc.status.not_in([ST.draft, ST.voided]))))
        cases = load_cases(db, [i.id for i in cand])
        recorded: dict[uuid.UUID, set[ExternalBody]] = defaultdict(set)
        if cand:
            for n in db.scalars(
                select(ExternalNotification).where(
                    ExternalNotification.incident_id.in_([i.id for i in cand])
                )
            ):
                recorded[n.incident_id].add(ExternalBody(n.body))
        hit = [
            i.id
            for i in cand
            if any(r.body not in recorded[i.id] for r in required_notifications(i, cases[i.id]))
        ]
        stmt = stmt.where(Inc.id.in_(hit) if notification_due else Inc.id.not_in(hit))
    order: Any = {
        "occurred_at": Inc.occurred_at.asc(),
        "-occurred_at": Inc.occurred_at.desc(),
        "ref": Inc.ref.asc(),
        "-ref": Inc.ref.desc(),
        "status": Inc.status.asc(),
    }[sort]
    stmt = stmt.order_by(order, Inc.ref.desc())
    items, total = paginate(db, stmt, page, page_size)
    return IncidentPage(items=list_items(db, items), total=total, page=page, page_size=page_size)


def list_items(db: Session, items: Sequence[Incident]) -> list[IncidentListItem]:
    ids = [i.id for i in items]
    cases = load_cases(db, ids)
    invs = (
        {
            v.incident_id: v
            for v in db.scalars(select(Investigation).where(Investigation.incident_id.in_(ids)))
        }
        if ids
        else {}
    )
    settings: dict[uuid.UUID, HseSettings] = {}
    refs = Refs(db).load(
        sites=[i.site_id for i in items],
        zones=[i.zone_id for i in items],
        engs=[i.responsible_engagement_id for i in items],
    )
    out = []
    for i in items:
        s = settings.setdefault(i.project_id, hse_settings.get(db, i.project_id))
        cs = cases.get(i.id, [])
        inv = invs.get(i.id)
        out.append(
            IncidentListItem(
                id=i.id,
                ref=i.ref,
                occurred_at=i.occurred_at,
                shift=i.shift,
                incident_types=[IncidentType(t) for t in i.incident_types],
                primary_type=i.primary_type,
                title=i.title,
                site=refs.site(i.site_id),
                zone=refs.zone(i.zone_id),
                responsible_engagement=refs.eng(i.responsible_engagement_id),
                activity=i.activity,
                actual_severity=i.actual_severity,
                potential_severity=i.potential_severity,
                hipo=i.hipo,
                status=i.status,
                case_count=len(cs),
                case_categories=sorted({c.category for c in cs}, key=list(CaseCategory).index),
                provisional_cases=sum(
                    1 for c in cs if c.classification_status == ClassificationStatus.provisional
                ),
                excluded_cases=sum(1 for c in cs if exclusion_reasons(i, c, s)),
                late_report=i.late_report,
                investigation_level=inv.level if inv else None,
                investigation_due_date=inv.due_date if inv else None,
            )
        )
    return out


def excluded_cases(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
) -> ExcludedCaseList:
    """AC21: cases (and case-less events) listed but excluded from rates, with reasons."""
    project = projects.get_visible(db, p, project_id)
    s = hse_settings.get(db, project.id)
    stmt = scoped_query(db, p, project).where(Incident.status != ST.draft)
    if date_from:
        stmt = stmt.where(Incident.occurred_date >= date_from)
    if date_to:
        stmt = stmt.where(Incident.occurred_date <= date_to)
    incs = list(db.scalars(stmt.order_by(Incident.occurred_at)))
    cases = load_cases(db, [i.id for i in incs])
    rows = []
    for i in incs:
        detail = i.not_work_related_reason.value if i.not_work_related_reason else None
        cs = cases.get(i.id, [])
        if not cs:
            reasons = exclusion_reasons(i, None, s)
            if reasons:
                rows.append(
                    ExcludedCaseRow(
                        incident_id=i.id,
                        incident_ref=i.ref,
                        case_id=None,
                        case_no=None,
                        occurred_at=i.occurred_at,
                        case_category=None,
                        reasons=[RateExclusionReason(r) for r in reasons],
                        reason_detail=detail if not i.work_related else i.void_reason,
                    )
                )
            continue
        for c in cs:
            reasons = exclusion_reasons(i, c, s)
            if reasons:
                rows.append(
                    ExcludedCaseRow(
                        incident_id=i.id,
                        incident_ref=i.ref,
                        case_id=c.id,
                        case_no=f"{i.ref}-P{c.person_no}",
                        occurred_at=i.occurred_at,
                        case_category=c.category,
                        reasons=[RateExclusionReason(r) for r in reasons],
                        reason_detail=detail if not i.work_related else None,
                    )
                )
    return ExcludedCaseList(items=rows)
