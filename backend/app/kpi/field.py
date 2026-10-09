"""Field assurance KPIs K-110…K-117 (spec 6d-field-assurance §6.5, §6.7, FM-1).

Computed from the 6d registers on the request's session, reached through the per-request heat
facts (same session and project list), as the 6c KPIs. as_of = the period end or today, whichever
is earlier. Attribution (FM-1): responses → completed local date and their engagement (no
engagement → only without a contractor filter); audits → issued date and the auditee; talks /
K-116 → the attendee's deployment engagement (unnamed → the host); campaigns → the pair."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hse_enums import KpiKind, KpiMetric
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.periods import Window

UUID = uuid.UUID
M = KpiMetric
D = Decimal
ZERO = Decimal(0)


@dataclass
class FFacts:
    db: Session
    pids: list[UUID]
    memo: dict[Any, Any] = field(default_factory=dict)


def ffacts(e: Engine) -> FFacts | None:
    m: FFacts | None = getattr(e, "_field_facts", None)
    if m is None:
        hf = getattr(e.facts, "heat", None)
        if hf is None:
            return None
        m = FFacts(hf.db, list(hf.pids))
        e._field_facts = m  # type: ignore[attr-defined]
    return m


def _end(e: Engine, w: Window) -> date:
    return min(e.as_of, w.end)


def _memo(ff: FFacts, key: Any, fn: Any) -> Any:
    if key not in ff.memo:
        ff.memo[key] = fn()
    return ff.memo[key]


# ---- inspections (K-110…K-112) -------------------------------------------------------------------


@dataclass(frozen=True)
class Resp:
    id: UUID
    pid: UUID
    d: date
    site: UUID
    zone: UUID | None
    eng: UUID | None
    aw: Decimal
    ew: Decimal
    passed: bool
    crit: int
    template: str
    itype: str
    self_insp: bool
    answers: tuple[tuple[str, bool], ...]  # (item_code, compliant) of applicable answers


def responses(ff: FFacts) -> list[Resp]:
    from app.core.field_enums import ResponseOwnerType, ResponseResult  # noqa: PLC0415
    from app.models import ChecklistResponse  # noqa: PLC0415

    def load() -> list[Resp]:
        R = ChecklistResponse  # noqa: N806
        out = []
        for r in ff.db.scalars(
            select(R).where(
                R.project_id.in_(ff.pids),
                R.owner_type == ResponseOwnerType.inspection,
                R.submitted.is_(True),
                R.voided.is_(False),
                R.completed_date.is_not(None),
            )
        ):
            assert r.completed_date is not None  # noqa: S101
            out.append(
                Resp(
                    r.id, r.project_id, r.completed_date, r.site_id, r.zone_id, r.engagement_id,
                    D(r.applicable_weight), D(r.earned_weight), r.result == ResponseResult.pass_,
                    r.critical_fail_count, r.template_code,
                    r.inspection_type.value if r.inspection_type else "", r.self_inspection,
                    tuple((a["item_code"], bool(a.get("compliant")))
                          for a in r.answers or [] if a.get("applicable")),
                )
            )  # fmt: skip
        return out

    return _memo(ff, "responses", load)  # type: ignore[no-any-return]


def _ok(e: Engine, site: UUID | None, zone: UUID | None, eng: UUID | None) -> bool:
    f = e.flt
    if site is not None and not f.site_ok(site):
        return False
    if site is None and f.sites is not None:
        return False
    if f.zone_filtered and not f.zone_ok(zone, e.facts.zones):
        return False
    return f.eng_ok(eng)


def resp_in(e: Engine, w: Window, **flt: Any) -> list[Resp]:
    ff = ffacts(e)
    if ff is None:
        return []
    end = _end(e, w)
    out = []
    for r in responses(ff):
        if not (w.start <= r.d <= end) or not _ok(e, r.site, r.zone, r.eng):
            continue
        if any(getattr(r, k) != v for k, v in flt.items()):
            continue
        out.append(r)
    return out


def _k110(e: Engine, a: Agg) -> Result:
    rs = resp_in(e, a.window)
    aw = sum((r.aw for r in rs), D(0))
    ew = sum((r.ew for r in rs), D(0))
    res = e._pct(M.K110, ew, aw)
    passed = sum(1 for r in rs if r.passed)
    res.components = [
        Component("pass_rate", "Pass rate", "نسبة النجاح",
                  D(passed) * 100 / len(rs) if rs else None, KpiKind.percentage, 1),
        Component("inspections", "Inspections", "عمليات التفتيش", D(len(rs)), KpiKind.count_),
    ]  # fmt: skip
    return res


def stop_orders(e: Engine, w: Window) -> int:
    from app.core.field_enums import StopOrderStatus  # noqa: PLC0415
    from app.models import StopWorkOrder  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    ff = ffacts(e)
    if ff is None:
        return 0
    end = _end(e, w)
    rows = _memo(ff, "orders", lambda: list(ff.db.scalars(select(StopWorkOrder).where(
        StopWorkOrder.project_id.in_(ff.pids)))))  # fmt: skip
    return sum(
        1
        for o in rows
        if o.status != StopOrderStatus.voided
        and w.start <= fc.local_day(o.raised_at) <= end
        and _ok(e, o.site_id, o.zone_id, o.engagement_id)
    )


def _k111(e: Engine, a: Agg) -> Result:
    rs = resp_in(e, a.window)
    n = sum(r.crit for r in rs)
    res = e._count(M.K111, n)
    rate = (D(n) * 100 / len(rs)) if rs else None
    res.components = [
        Component("per_100", "Per 100 inspections", "لكل 100 تفتيش", rate, KpiKind.rate, 2),
        Component("stop_work_orders", "Stop-work orders", "أوامر إيقاف العمل",
                  D(stop_orders(e, a.window)), KpiKind.count_),
        Component("inspections", "Inspections", "عمليات التفتيش", D(len(rs)), KpiKind.count_),
    ]  # fmt: skip
    return res


def item_findings(ff: FFacts) -> dict[UUID, tuple[int, int]]:
    """response id → (item findings, repeats)."""
    from app.models import FieldFinding  # noqa: PLC0415

    def load() -> dict[UUID, tuple[int, int]]:
        acc: dict[UUID, list[int]] = defaultdict(lambda: [0, 0])
        for rid, rep in ff.db.execute(
            select(FieldFinding.response_id, FieldFinding.repeat_of_id).where(
                FieldFinding.project_id.in_(ff.pids),
                FieldFinding.item_code.is_not(None),
                FieldFinding.voided.is_(False),
            )
        ):
            acc[rid][0] += 1
            acc[rid][1] += rep is not None
        return {k: (v[0], v[1]) for k, v in acc.items()}

    return _memo(ff, "findings", load)  # type: ignore[no-any-return]


def _k112(e: Engine, a: Agg) -> Result:
    ff = ffacts(e)
    if ff is None:
        return e._pct(M.K112, 0, 0)
    fx = item_findings(ff)
    n = rep = 0
    for r in resp_in(e, a.window):
        x = fx.get(r.id, (0, 0))
        n += x[0]
        rep += x[1]
    return e._pct(M.K112, rep, n)


# ---- K-113 coverage (ISP-3) ----------------------------------------------------------------------


@dataclass
class Unit:
    pid: UUID
    eng: UUID
    site: UUID
    week: date
    covered: bool = False


def coverage_units(e: Engine, w: Window) -> list[Unit]:
    from app.services.field import common as fc  # noqa: PLC0415

    ff = ffacts(e)
    if ff is None:
        return []
    end = _end(e, w)
    out: list[Unit] = []
    for pid in ff.pids:
        weeks = fc.weeks_in(ff.db, pid, w.start, end, e.as_of)
        if not weeks:
            continue
        lo, hi = weeks[0], weeks[-1] + timedelta(days=6)
        req: dict[tuple[UUID, UUID, date], Unit] = {}
        for r in e.wf:
            if r.project != pid or r.hc <= 0 or not (lo <= r.d <= hi):
                continue
            ws = weeks[(r.d - lo).days // 7]
            req.setdefault((r.eng, r.site, ws), Unit(pid, r.eng, r.site, ws))
        for i in e.insp:
            if i.project != pid or i.completed is None or not (lo <= i.completed <= hi):
                continue
            if i.completed > e.as_of:
                continue
            ws = weeks[(i.completed - lo).days // 7]
            u = req.get((i.eng, i.site, ws)) if i.eng else None
            if u is not None:
                u.covered = True
        out.extend(req.values())
    return out


def _k113(e: Engine, a: Agg) -> Result:
    us = coverage_units(e, a.window)
    return e._pct(M.K113, sum(1 for u in us if u.covered), len(us))


# ---- K-114 / K-115 audits ------------------------------------------------------------------------


@dataclass
class ProgItem:
    pid: UUID
    eng: UUID | None
    due: date
    met: bool


def programme_items(e: Engine, w: Window) -> list[ProgItem]:
    from app.services.field import audits as au  # noqa: PLC0415

    ff = ffacts(e)
    if ff is None:
        return []
    end = _end(e, w)
    out = []
    for pid in ff.pids:
        lines = _memo(ff, ("lines", pid, end), lambda pid=pid: au.lines(ff.db, pid, end))
        for ln in lines:
            if ln.engagement_id is None and e.flt.engs is not None:
                continue
            if ln.engagement_id is not None and not e.flt.eng_ok(ln.engagement_id):
                continue
            for d, x in ln.items:
                if w.start <= d <= end:
                    out.append(ProgItem(pid, ln.engagement_id, d, au.met_on_time((d, x))))
    return out


def _k114(e: Engine, a: Agg) -> Result:
    its = programme_items(e, a.window)
    return e._pct(M.K114, sum(1 for i in its if i.met), len(its))


@dataclass
class AuditStats:
    aw: Decimal = ZERO
    ew: Decimal = ZERO
    major: int = 0
    minor: int = 0
    grades: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    n: int = 0


def audit_stats(e: Engine, w: Window) -> AuditStats:
    from app.core.field_enums import AuditStatus, FindingSeverity  # noqa: PLC0415
    from app.models import ChecklistResponse, FieldAudit, FieldFinding  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    ff = ffacts(e)
    out = AuditStats()
    if ff is None:
        return out
    end = _end(e, w)
    for au in ff.db.scalars(
        select(FieldAudit).where(
            FieldAudit.project_id.in_(ff.pids),
            FieldAudit.status.in_((AuditStatus.issued, AuditStatus.closed)),
            FieldAudit.issued_at.is_not(None),
        )
    ):
        assert au.issued_at is not None  # noqa: S101
        if not (w.start <= fc.local_day(au.issued_at) <= end):
            continue
        if not e.flt.eng_ok(au.auditee_engagement_id) or (
            e.flt.sites is not None and not any(e.flt.site_ok(s) for s in au.site_ids or [])
        ):
            continue
        r = ff.db.get(ChecklistResponse, au.response_id) if au.response_id else None
        if r is None:
            continue
        out.n += 1
        out.aw += D(r.applicable_weight)
        out.ew += D(r.earned_weight)
        if r.grade:
            out.grades[r.grade.value] += 1
        for sev in ff.db.scalars(
            select(FieldFinding.severity).where(FieldFinding.response_id == r.id)
        ):
            out.major += sev == FindingSeverity.major_nc
            out.minor += sev == FindingSeverity.minor_nc
    return out


def _k115(e: Engine, a: Agg) -> Result:
    s = audit_stats(e, a.window)
    res = e._pct(M.K115, s.ew, s.aw)
    res.components = [
        Component("major_nc", "Major NCs", "عدم مطابقة رئيسية", D(s.major), KpiKind.count_),
        Component("minor_nc", "Minor NCs", "عدم مطابقة ثانوية", D(s.minor), KpiKind.count_),
        *[
            Component(f"grade_{g}", f"Grade {g}", f"التقدير {g}", D(s.grades.get(g, 0)),
                      KpiKind.count_)
            for g in ("A", "B", "C", "D")
        ],
    ]  # fmt: skip
    return res


# ---- K-116 reach (§6.5) --------------------------------------------------------------------------


@dataclass
class ReachUnit:
    pid: UUID
    eng: UUID
    site: UUID
    week: date
    h: Decimal
    b: int

    @property
    def reach(self) -> Decimal:
        return min(D(self.b), self.h)


@dataclass
class Reach:
    units: list[ReachUnit] = field(default_factory=list)
    named: int = 0
    matched: int = 0
    active: bool = False


def reach(e: Engine, w: Window) -> Reach:
    from app.core.field_enums import TalkStatus, UnderstoodLanguage  # noqa: PLC0415
    from app.models import TalkAttendance, ToolboxTalk  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    ff = ffacts(e)
    out = Reach()
    if ff is None:
        return out
    end = _end(e, w)
    T, A = ToolboxTalk, TalkAttendance  # noqa: N806
    for pid in ff.pids:
        rf = fc.cfg(ff.db, pid).toolbox_from
        if rf is None or rf > end:
            continue
        out.active = True
        weeks = [ws for ws in fc.weeks_in(ff.db, pid, w.start, end, e.as_of) if ws >= rf]
        if not weeks:
            continue
        lo, hi = weeks[0], weeks[-1] + timedelta(days=6)
        hc: dict[tuple[UUID, UUID, date], dict[date, int]] = defaultdict(lambda: defaultdict(int))
        for r in e.wf:
            if r.project != pid or not (lo <= r.d <= hi):
                continue
            ws = weeks[(r.d - lo).days // 7] if (r.d - lo).days // 7 < len(weeks) else None
            if ws is None or not (ws <= r.d <= ws + timedelta(days=6)):
                continue
            hc[(r.eng, r.site, ws)][r.d] += r.hc
        briefed: dict[tuple[UUID, UUID, date], set[UUID]] = defaultdict(set)
        unnamed: dict[tuple[UUID, UUID, date], int] = defaultdict(int)
        talks = list(
            ff.db.execute(
                select(
                    T.id, T.site_id, T.host_engagement_id, T.delivered_date, T.unnamed_count
                ).where(
                    T.project_id == pid,
                    T.status.in_((TalkStatus.delivered, TalkStatus.locked)),
                    T.delivered_date >= lo,
                    T.delivered_date <= hi,
                )
            ).all()
        )
        tinfo = {t[0]: t for t in talks}
        for _tid, site, host, d, un in talks:
            ws = weeks[(d - lo).days // 7]
            unnamed[(host, site, ws)] += un
        if tinfo:
            for tid, dep, eng, ul in ff.db.execute(
                select(A.talk_id, A.deployment_id, A.engagement_id, A.understood_language).where(
                    A.talk_id.in_(list(tinfo))
                )
            ):
                _t, site, _host, d, _un = tinfo[tid]
                if e.flt.site_ok(site) and e.flt.eng_ok(eng):
                    out.named += 1
                    out.matched += ul != UnderstoodLanguage.none
                if ul == UnderstoodLanguage.none or eng is None:
                    continue
                ws = weeks[(d - lo).days // 7]
                briefed[(eng, site, ws)].add(dep)
        for key, days in hc.items():
            pos = [v for v in days.values() if v > 0]
            if not pos:
                continue
            eng, site, ws = key
            if not (e.flt.eng_ok(eng) and e.flt.site_ok(site)):
                continue
            h = D(sum(pos)) / len(pos)
            out.units.append(ReachUnit(pid, eng, site, ws, h, len(briefed[key]) + unnamed[key]))
    return out


def _k116(e: Engine, a: Agg) -> Result:
    r = reach(e, a.window)
    num = sum((u.reach for u in r.units), D(0))
    den = sum((u.h for u in r.units), D(0))
    res = e._pct(M.K116, num, den)
    res.components = [
        Component("language_match", "Language match", "تطابق اللغة",
                  D(r.matched) * 100 / r.named if r.named else None, KpiKind.percentage, 1),
    ]  # fmt: skip
    return res


# ---- K-117 campaigns (CMP-3) ---------------------------------------------------------------------


def campaign_pairs(e: Engine, w: Window) -> list[tuple[str, bool]]:
    from app.core.field_enums import CampaignStatus  # noqa: PLC0415
    from app.models import BriefingCampaign  # noqa: PLC0415
    from app.services.field import campaigns as cmp  # noqa: PLC0415

    ff = ffacts(e)
    if ff is None:
        return []
    end = _end(e, w)
    out = []
    for c in ff.db.scalars(
        select(BriefingCampaign).where(
            BriefingCampaign.project_id.in_(ff.pids),
            BriefingCampaign.status.in_((CampaignStatus.issued, CampaignStatus.closed)),
            BriefingCampaign.due_date >= w.start,
            BriefingCampaign.due_date <= end,
        )
    ):
        for s in cmp.pair_states(ff.db, c):
            if e.flt.eng_ok(s.engagement_id) and e.flt.site_ok(s.site_id):
                out.append((c.campaign_no, s.on_time(c.due_date)))
    return out


def _k117(e: Engine, a: Agg) -> Result:
    ps = campaign_pairs(e, a.window)
    return e._pct(M.K117, sum(1 for _, ok in ps if ok), len(ps))


engine_mod._DISPATCH.update(
    {
        M.K110: _k110,
        M.K111: _k111,
        M.K112: _k112,
        M.K113: _k113,
        M.K114: _k114,
        M.K115: _k115,
        M.K116: _k116,
        M.K117: _k117,
    }
)


def q1(v: Decimal | None) -> Decimal | None:
    return v.quantize(D("0.1"), rounding=ROUND_HALF_UP) if v is not None else None
