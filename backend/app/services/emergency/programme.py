"""Drill programme (spec 6c-emergency-drills §3.10, DP-1…DP-6, §6.3).

Lines are derived on read (DECISIONS: computed, not stored) from the settings, the Approved ERP,
the active sites and teams and the drills: per site (evacuation_full, its night and unannounced
variants, medical_response, shelter_in_place when a scenario uses it), per team (cse_rescue,
height_rescue), per project (tabletop, airport_exercise) and repeat lines (DR-7). Each line
carries its due-date history: one K-104 item per due_by (DP-5)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.emergency_enums import (
    ActiveStatus,
    AnnouncementRequirement,
    DrillResult,
    DrillShift,
    DrillStatus,
    DrillType,
    LineSource,
    LineStatus,
    ProgrammeScope,
    ShiftRequirement,
)
from app.core.enums import Capability, SiteStatus
from app.core.hse_enums import Shift, WorkforceStatus
from app.models import Drill, RescueTeam, Site, WorkforceReturn
from app.schemas.emergency import Programme, ProgrammeLine
from app.services.emergency import common as ec
from app.services.emergency import reference as ref
from app.services.permissions import Principal
from app.services.train.validity import add_months

C = Capability
DT = DrillType
SR = ShiftRequirement
AR = AnnouncementRequirement
DONE = (DrillStatus.conducted, DrillStatus.evaluated)
PS = ProgrammeScope


@dataclass
class Item:
    due: date
    met: bool
    drill: Drill | None


@dataclass
class Line:
    drill_type: DrillType
    scope: ProgrammeScope
    site_id: uuid.UUID | None
    team_id: uuid.UUID | None
    shift_req: ShiftRequirement
    ann_req: AnnouncementRequirement
    freq: int | None
    source: LineSource
    src: Drill | None = None
    start: date | None = None
    items: list[Item] = field(default_factory=list)
    due_by: date | None = None
    last: Drill | None = None
    status: LineStatus = LineStatus.due

    @property
    def key(self) -> str:
        return ":".join(
            str(x)
            for x in (
                self.drill_type.value, self.scope.value, self.site_id or self.team_id or "-",
                self.shift_req.value, self.ann_req.value, self.source.value,
                self.src.id if self.src else "-",
            )
        )  # fmt: skip


def drill_date(x: Drill) -> date | None:
    """The conducted date of a drill: the local date of its alarm (else of Conduct)."""
    at = ec.dt((x.timeline or {}).get("alarm_at")) or x.conducted_at
    return ec.local_day(at) if at else None


def satisfies(x: Drill, ln: Line) -> bool:
    """DP-2."""
    if x.status not in DONE or x.drill_type != ln.drill_type:
        return False
    if ln.scope == ProgrammeScope.site and x.site_id != ln.site_id:
        return False
    if ln.scope == ProgrammeScope.team and x.team_id != ln.team_id:
        return False
    if ln.shift_req == SR.night and x.shift != DrillShift.night:
        return False
    return not (ln.ann_req == AR.unannounced and x.announced)


def _first_work(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, date]:
    return dict(
        db.execute(
            select(WorkforceReturn.site_id, func.min(WorkforceReturn.work_date))
            .where(
                WorkforceReturn.project_id == project_id,
                WorkforceReturn.headcount > 0,
                WorkforceReturn.status != WorkforceStatus.draft,
            )
            .group_by(WorkforceReturn.site_id)
        ).all()
    )


def _night_sites(db: Session, project_id: uuid.UUID, as_of: date) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(WorkforceReturn.site_id)
            .where(
                WorkforceReturn.project_id == project_id,
                WorkforceReturn.shift == Shift.night,
                WorkforceReturn.headcount > 0,
                WorkforceReturn.work_date > as_of - timedelta(days=90),
                WorkforceReturn.work_date <= as_of,
                WorkforceReturn.status != WorkforceStatus.draft,
            )
            .distinct()
        )
    )


def project_drills(db: Session, project_id: uuid.UUID) -> list[Drill]:
    return list(
        db.scalars(select(Drill).where(Drill.project_id == project_id, Drill.status.in_(DONE)))
    )


def lines(
    db: Session, project_id: uuid.UUID, as_of: date, drills: list[Drill] | None = None
) -> list[Line]:
    c = ec.cfg(db, project_id)
    if c.register_from is None:
        return []
    drills = project_drills(db, project_id) if drills is None else drills
    drills = [x for x in drills if (dd := drill_date(x)) is not None and dd <= as_of]
    erp = ec.erp_in_force(db, project_id)
    scen = list(erp.scenarios or []) if erp else []

    def freq(t: DrillType, site: uuid.UUID | None = None) -> int | None:
        fs = [
            int(s["drill_frequency_months"])
            for s in scen
            if s["drill_type"] == t.value
            and (site is None or str(site) in {str(x) for x in s["site_ids"]})
        ]
        mn = c.minimum(t)
        allf = [*fs, *([mn] if mn is not None else [])]
        return min(allf) if allf else None

    def used(t: DrillType, site: uuid.UUID | None = None) -> bool:
        return any(
            s["drill_type"] == t.value
            and (site is None or str(site) in {str(x) for x in s["site_ids"]})
            for s in scen
        )

    sites = list(
        db.scalars(
            select(Site)
            .where(Site.project_id == project_id, Site.status == SiteStatus.active)
            .order_by(Site.code)
        )
    )
    first = _first_work(db, project_id)
    nights = _night_sites(db, project_id, as_of)
    out: list[Line] = []
    for s in sites:
        st = max(c.register_from, first[s.id]) if s.id in first else None
        if st is None:
            continue  # no day with work yet

        def add(t: DrillType, f: int | None, sr: SR = SR.any, ar: AR = AR.any) -> None:
            if f is not None:
                out.append(Line(t, PS.site, s.id, None, sr, ar, f, LineSource.minimum, start=st))  # noqa: B023

        add(DT.evacuation_full, freq(DT.evacuation_full, s.id))
        if s.id in nights:
            add(DT.evacuation_full, ref.NIGHT_MINIMUM_MONTHS, sr=SR.night)
        add(DT.evacuation_full, ref.UNANNOUNCED_MINIMUM_MONTHS, ar=AR.unannounced)
        add(DT.medical_response, freq(DT.medical_response, s.id))
        if used(DT.shelter_in_place, s.id):
            add(DT.shelter_in_place, freq(DT.shelter_in_place, s.id))
        if used(DT.evacuation_partial, s.id):
            add(DT.evacuation_partial, freq(DT.evacuation_partial, s.id))
    for tm in db.scalars(
        select(RescueTeam)
        .where(RescueTeam.project_id == project_id, RescueTeam.status == ActiveStatus.active)
        .order_by(RescueTeam.team_code)
    ):
        t = DT.cse_rescue if tm.team_type.value == "confined_space" else DT.height_rescue
        out.append(
            Line(t, PS.team, None, tm.id, SR.any, AR.any, freq(t), LineSource.minimum,
                 start=max(c.register_from, tm.created_on))
        )  # fmt: skip
    for t in [DT.tabletop, *([DT.airport_exercise] if c.airport else [])]:
        out.append(
            Line(t, PS.project, None, None, SR.any, AR.any, freq(t), LineSource.minimum,
                 start=c.register_from)
        )  # fmt: skip
    grace = timedelta(days=int(c["first_drill_grace_days"]))
    for ln in out:
        _schedule(ln, drills, as_of, grace)
    # DR-7 repeat lines
    rep = timedelta(days=int(c["repeat_drill_days"]))
    for x in sorted(drills, key=lambda d: (drill_date(d), d.drill_no)):
        if x.status != DrillStatus.evaluated or x.result != DrillResult.unsatisfactory:
            continue
        xd = drill_date(x)
        assert xd is not None  # noqa: S101
        scope = ref.DRILL_TYPES[x.drill_type][3]
        ln = Line(
            x.drill_type,
            ProgrammeScope(scope),
            x.site_id if scope == "site" else None,
            x.team_id if scope == "team" else None,
            SR.any,
            AR.any,
            None,
            LineSource.repeat,
            src=x,
            start=xd,
        )
        ln.due_by = xd + rep
        later = sorted(
            (y for y in drills if y.id != x.id and satisfies(y, ln) and (drill_date(y) or xd) > xd),
            key=lambda y: drill_date(y) or xd,
        )
        if later:
            y = later[0]
            ln.last = y
            ln.items.append(Item(ln.due_by, (drill_date(y) or xd) <= ln.due_by, y))
            ln.status = LineStatus.satisfied
        else:
            if ln.due_by <= as_of:
                ln.items.append(Item(ln.due_by, False, None))
            ln.status = LineStatus.overdue if as_of > ln.due_by else LineStatus.due
        out.append(ln)
    return out


def _schedule(ln: Line, drills: list[Drill], as_of: date, grace: timedelta) -> None:
    """DP-3 / DP-5: due dates and items from the satisfying drills (conducted ≤ as_of)."""
    assert ln.start is not None and ln.freq is not None  # noqa: S101
    sat = sorted(
        ((drill_date(x), x) for x in drills if satisfies(x, ln)),
        key=lambda t: (t[0], t[1].drill_no),
    )
    before = [(d, x) for d, x in sat if d is not None and d <= ln.start]
    if before:
        ln.last = before[-1][1]
        due = add_months(before[-1][0], ln.freq) - timedelta(days=1)
    else:
        due = ln.start + grace
    for d, x in sat:
        if d is None or d <= ln.start:
            continue
        ln.items.append(Item(due, d <= due, x))
        ln.last = x
        due = add_months(d, ln.freq) - timedelta(days=1)
    if due <= as_of:
        ln.items.append(Item(due, False, None))
    ln.due_by = due
    ln.status = LineStatus.overdue if as_of > due else LineStatus.due


# ---- API -----------------------------------------------------------------------------------------


def line_view(db: Session, pcode: str, i: int, ln: Line, as_of: date) -> ProgrammeLine:
    tm = db.get(RescueTeam, ln.team_id) if ln.team_id else None
    return ProgrammeLine(
        line_no=f"DPL-{pcode}-{i:03d}",
        drill_type=ln.drill_type,
        scope=ln.scope,
        site_id=ln.site_id,
        site_code=ec.site_code(db, ln.site_id),
        team_id=ln.team_id,
        team_code=tm.team_code if tm else None,
        shift_requirement=ln.shift_req,
        announcement_requirement=ln.ann_req,
        frequency_months=ln.freq,
        source=ln.source,
        source_drill_no=ln.src.drill_no if ln.src else None,
        due_by=ln.due_by,
        last_satisfied_by=ln.last.drill_no if ln.last else None,
        last_satisfied_on=drill_date(ln.last) if ln.last else None,
        status=ln.status,
        days_to_due=(ln.due_by - as_of).days
        if ln.due_by and ln.status != LineStatus.satisfied
        else None,
    )


def views(db: Session, project_id: uuid.UUID, as_of: date) -> list[ProgrammeLine]:
    code = ec.pcode(db, project_id)
    return [
        line_view(db, code, i + 1, ln, as_of) for i, ln in enumerate(lines(db, project_id, as_of))
    ]


def read_programme(
    db: Session, p: Principal, project_id: uuid.UUID, as_of: date | None
) -> Programme:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    d = as_of or ec.local_day()
    return Programme(project_id=project_id, as_of=d, lines=views(db, project_id, d))


def recipients(db: Session, project_id: uuid.UUID, ln: Line) -> set[uuid.UUID]:
    """DP-4: HSE Officers and the site engineers of the site (team lines: the team lead's
    Contractor HSE Rep too)."""
    out = ec.officers(db, project_id)
    if ln.site_id is not None:
        out |= ec.site_engineers(db, project_id, ln.site_id)
    if ln.team_id is not None:
        from app.models import Deployment  # noqa: PLC0415

        tm = db.get(RescueTeam, ln.team_id)
        dep = db.get(Deployment, tm.lead_deployment_id) if tm else None
        if tm is not None:
            for s in tm.site_ids or []:
                out |= ec.site_engineers(db, project_id, s)
        if dep is not None:
            out |= ec.reps(db, project_id, dep.engagement_id)
    return out


def due_alerts(db: Session, project_id: uuid.UUID, d: date) -> int:
    """DP-4: 30 / 14 / 7 / 0 days before due_by, then overdue day 1 and weekly (07:05)."""
    from app.core.enums import EntityType, NotificationKind  # noqa: PLC0415
    from app.services.cert.alerts import long_step  # noqa: PLC0415

    n = 0
    code = ec.pcode(db, project_id)
    for ln in lines(db, project_id, d):
        if ln.due_by is None or ln.status == LineStatus.satisfied:
            continue
        what = f"{ref.DRILL_TYPES[ln.drill_type][0]}"
        where = ec.site_code(db, ln.site_id) or (
            tm.team_code if ln.team_id and (tm := db.get(RescueTeam, ln.team_id)) else code
        )
        if d <= ln.due_by:
            step = long_step(db, f"em:line:{ln.key}", ln.due_by, d, (30, 14, 7, 0))
            if step is None:
                continue
            en = f"Drill due: {what} ({where}) by {ln.due_by.isoformat()}"
            ar = f"موعد تمرين: {ref.DRILL_TYPES[ln.drill_type][1]} ({where}) قبل {ln.due_by}"
        else:
            over = (d - ln.due_by).days
            if over != 1 and (over - 1) % 7 != 0:
                continue
            if not ec.once(db, f"line_over:{ln.key}:{ln.due_by}:{over}"):
                continue
            en = f"Drill overdue: {what} ({where}) was due {ln.due_by.isoformat()}"
            ar = f"تمرين متأخر: {ref.DRILL_TYPES[ln.drill_type][1]} ({where})"
        n += ec.send(
            db, recipients(db, project_id, ln), NotificationKind.emergency_drill_due, en, ar,
            project_id, EntityType.emergency_drill, None, email=True,
        )  # fmt: skip
    return n
