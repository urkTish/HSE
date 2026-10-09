"""Heat action panel (spec 6b-heat-stress §8.2) and season report (§3.12, §4.5, §8.4, HM-4)."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import validation_error
from app.core.heat_enums import (
    BanExemptionStatus,
    HeatActionKind,
    HeatLogStatus,
    InstrumentStatus,
    PatrolOutcome,
    PlanStatus,
    PlanType,
    RecordStatus,
    Regime,
    SeasonReportStatus,
)
from app.core.hse_enums import CaSourceType, CaStatus, KpiMetric
from app.core.ptw_enums import PermitStatus
from app.kpi import fmt, present
from app.kpi import heat as kh
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, month_end
from app.models import (
    AcclimatisationPlan,
    BanExemption,
    BanPatrol,
    CorrectiveAction,
    HeatIllnessEntry,
    HeatInstrument,
    HeatSeasonReport,
    HeatWelfareCheck,
    MonitoringPoint,
    Permit,
    RestStation,
    WbgtReading,
)
from app.schemas.heat import (
    HeatActionItem,
    HeatActionPanel,
    SeasonReportIssue,
    SeasonReportList,
    SeasonReportRead,
)
from app.services.heat import common as hc
from app.services.heat import log as heat_log
from app.services.heat import state
from app.services.permissions import Principal

C = Capability
M = KpiMetric
K = HeatActionKind
LABELS: dict[HeatActionKind, tuple[str, str]] = {
    K.required_zone_without_point: ("Required zones without a monitoring point",
                                    "مناطق مطلوبة بلا نقطة قياس"),
    K.reading_overdue_now: ("WBGT readings overdue now", "قراءات المؤشر الحراري المتأخرة الآن"),
    K.r4_permit_not_suspended: ("Zones at R4 with an Active outdoor permit not suspended",
                                "مناطق عند R4 بتصريح خارجي نشط غير معلق"),
    K.ban_violation_ca_open: ("Ban violations whose CA is not In Progress",
                              "مخالفات حظر لم يبدأ إجراؤها التصحيحي"),
    K.patrol_coverage_missed_yesterday: ("Ban patrols missed yesterday", "جولات حظر فائتة أمس"),
    K.welfare_coverage_missed_yesterday: ("Welfare checks missed yesterday",
                                          "فحوص راحة فائتة أمس"),
    K.plan_days_unconfirmed: ("Acclimatisation plan days unconfirmed > 24 h",
                              "أيام خطط تأقلم غير مؤكدة لأكثر من 24 ساعة"),
    K.heat_reviews_overdue: ("Heat-illness reviews overdue", "مراجعات الإجهاد الحراري المتأخرة"),
    K.active_ban_exemption: ("Active non-permit ban exemptions", "استثناءات حظر نشطة"),
    K.quarantined_instrument_on_point: ("Quarantined instruments still on a point",
                                        "أجهزة معزولة ما زالت على نقطة"),
    K.permit_ban_violation: ("Outdoor work during the midday ban on a permit",
                             "عمل خارجي وقت حظر الظهيرة على تصريح"),
}  # fmt: skip
PERMIT_BAN_DAYS = 7


# ---- action panel ------------------------------------------------------------------------------


def _item(kind: HeatActionKind, refs: list[str]) -> HeatActionItem:
    en, ar = LABELS[kind]
    return HeatActionItem(kind=kind, count=len(refs), refs=sorted(refs), label_en=en, label_ar=ar)


def _reading_overdue(db: Session, pid: uuid.UUID, at: datetime, cfg: hc.Cfg) -> list[str]:
    d = hc.local_day(at)
    if not (cfg.active_on(d) and cfg.in_controls(d) and cfg.in_monitoring(at)):
        return []
    work = hc.days_with_work(db, pid, d, d)
    zones = hc.zone_map(db, pid)
    out = []
    for zid in hc.required_zone_ids(db, pid):
        z = zones.get(zid)
        if z is None or d not in work.get(z.site_id, set()):
            continue
        if state.zone_state(db, pid, zid, at).state != state.S.current:
            out.append(z.code)
    return out


def _r4_permits(db: Session, pid: uuid.UUID, at: datetime) -> list[str]:
    from app.services.heat import ptw as heat_ptw  # noqa: PLC0415

    out = []
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == pid,
            Permit.status == PermitStatus.active,
            Permit.exposure.in_(heat_ptw.OUTDOOR),
        )
    ):
        if not heat_ptw.applies(db, pm, at):
            continue
        ph = heat_ptw.permit_heat(db, pm, at)
        live = any(zs.state == state.S.current for _z, zs in ph.zones)
        if live and ph.regime == Regime.R4:
            out.append(pm.permit_no)
    return out


def _yesterday_patrols(db: Session, pid: uuid.UUID, d: date, cfg: hc.Cfg) -> list[str]:
    if not (cfg.active_on(d) and cfg.ban_date(d)):
        return []
    work = hc.days_with_work(db, pid, d, d)
    zones = hc.zone_map(db, pid)
    need = int(cfg["ban_patrols_per_zone_day"])
    s, t = hc.day_start(d), hc.day_start(d + timedelta(days=1))
    cnt = Counter(
        db.scalars(
            select(BanPatrol.zone_id).where(
                BanPatrol.project_id == pid,
                BanPatrol.status == RecordStatus.valid,
                BanPatrol.checked_at >= s,
                BanPatrol.checked_at < t,
            )
        )
    )
    return [
        zones[z].code
        for z in hc.required_zone_ids(db, pid)
        if z in zones and d in work.get(zones[z].site_id, set()) and cnt[z] < need
    ]


def _yesterday_welfare(db: Session, pid: uuid.UUID, d: date, cfg: hc.Cfg) -> list[str]:
    if not (cfg.active_on(d) and cfg.in_controls(d)):
        return []
    work = hc.days_with_work(db, pid, d, d)
    need = int(cfg["welfare_checks_per_station_day"])
    s, t = hc.day_start(d), hc.day_start(d + timedelta(days=1))
    cnt = Counter(
        db.scalars(
            select(HeatWelfareCheck.station_id).where(
                HeatWelfareCheck.project_id == pid,
                HeatWelfareCheck.status == RecordStatus.valid,
                HeatWelfareCheck.checked_at >= s,
                HeatWelfareCheck.checked_at < t,
            )
        )
    )
    return [
        st.station_code
        for st in db.scalars(
            select(RestStation).where(RestStation.project_id == pid, RestStation.active.is_(True))
        )
        if d in work.get(st.site_id, set()) and cnt[st.id] < need
    ]


def _plan_days(db: Session, pid: uuid.UUID, at: datetime) -> list[str]:
    out = []
    for pl in db.scalars(
        select(AcclimatisationPlan).where(
            AcclimatisationPlan.project_id == pid,
            AcclimatisationPlan.status.in_(
                [PlanStatus.active, PlanStatus.completed, PlanStatus.interrupted]
            ),
        )
    ):
        for x in pl.days or []:
            wd = x.get("work_date")
            if not wd or x.get("confirmed_at"):
                continue
            end = hc.day_start(date.fromisoformat(wd) + timedelta(days=1))
            if at >= end + timedelta(hours=24):
                out.append(f"{pl.plan_no} day {x.get('day_no')}")
    return out


def action_panel(db: Session, p: Principal, project_id: uuid.UUID) -> HeatActionPanel:
    from app.services.heat import config  # noqa: PLC0415

    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_kpi_view, write=False)
    at = now()
    cfg = hc.cfg(db, project_id)
    today = hc.local_day(at)
    yday = today - timedelta(days=1)
    items: list[HeatActionItem] = []
    if cfg.register_from is None:
        return HeatActionPanel(project_id=project_id, at=at, items=items)
    items.append(_item(K.required_zone_without_point, config.coverage_gaps(db, project_id)))
    items.append(_item(K.reading_overdue_now, _reading_overdue(db, project_id, at, cfg)))
    items.append(_item(K.r4_permit_not_suspended, _r4_permits(db, project_id, at)))
    ca_open = [
        x.patrol_no
        for x, st in db.execute(
            select(BanPatrol, CorrectiveAction.status)
            .join(CorrectiveAction, CorrectiveAction.id == BanPatrol.ca_id)
            .where(
                BanPatrol.project_id == project_id,
                BanPatrol.status == RecordStatus.valid,
                BanPatrol.outcome == PatrolOutcome.violation,
            )
        )
        if st == CaStatus.open
    ]
    items.append(_item(K.ban_violation_ca_open, ca_open))
    items.append(
        _item(K.patrol_coverage_missed_yesterday, _yesterday_patrols(db, project_id, yday, cfg))
    )
    items.append(
        _item(K.welfare_coverage_missed_yesterday, _yesterday_welfare(db, project_id, yday, cfg))
    )
    items.append(_item(K.plan_days_unconfirmed, _plan_days(db, project_id, at)))
    overdue = [
        e.entry_no
        for e in db.scalars(
            select(HeatIllnessEntry).where(
                HeatIllnessEntry.project_id == project_id,
                HeatIllnessEntry.status == HeatLogStatus.open,
            )
        )
        if at >= heat_log.review_due(db, e)
    ]
    items.append(_item(K.heat_reviews_overdue, overdue))
    items.append(
        _item(
            K.active_ban_exemption,
            list(
                db.scalars(
                    select(BanExemption.exemption_no).where(
                        BanExemption.project_id == project_id,
                        BanExemption.status == BanExemptionStatus.active,
                    )
                )
            ),
        )
    )
    items.append(
        _item(
            K.quarantined_instrument_on_point,
            list(
                db.scalars(
                    select(HeatInstrument.instrument_no)
                    .join(MonitoringPoint, MonitoringPoint.instrument_id == HeatInstrument.id)
                    .where(
                        MonitoringPoint.project_id == project_id,
                        MonitoringPoint.active.is_(True),
                        HeatInstrument.status == InstrumentStatus.quarantined,
                    )
                    .distinct()
                )
            ),
        )
    )
    items.append(
        _item(
            K.permit_ban_violation,
            list(
                db.scalars(
                    select(BanPatrol.patrol_no).where(
                        BanPatrol.project_id == project_id,
                        BanPatrol.status == RecordStatus.valid,
                        BanPatrol.outcome == PatrolOutcome.violation,
                        BanPatrol.permit_id.is_not(None),
                        BanPatrol.checked_at
                        >= hc.day_start(today - timedelta(days=PERMIT_BAN_DAYS - 1)),
                    )
                )
            ),
        )
    )
    return HeatActionPanel(project_id=project_id, at=at, items=items)


# ---- season report -----------------------------------------------------------------------------


def _engine(db: Session, project_id: uuid.UUID, as_of: date) -> Engine:
    from app.hse_jobs import _engine as build  # noqa: PLC0415
    from app.models import Project  # noqa: PLC0415

    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return build(db, pr, as_of)


def _kv(e: Engine, m: KpiMetric, w: Window) -> dict[str, Any]:
    r = e.result(m, e.aggregate(w))
    d = CATALOGUE[m]
    out: dict[str, Any] = {
        "value": present.value_str(d, r.value),
        "display": present.display(d, r.value),
        "numerator": fmt.exact(r.numerator),
        "denominator": fmt.exact(r.denominator),
    }
    for c in r.components:
        out[c.key] = fmt.dec_str(c.value, c.decimals) if c.value is not None else None
    return out


def _months(w: Window) -> list[Window]:
    out = []
    s = w.start
    while s <= w.end:
        e = min(month_end(s), w.end)
        out.append(Window(s, e))
        s = e + timedelta(days=1)
    return out


def season_window(db: Session, project_id: uuid.UUID, year: int) -> Window:
    s, e = hc.cfg(db, project_id).controls_window(year)
    return Window(s, e)


def _wbgt(db: Session, project_id: uuid.UUID, w: Window) -> list[dict[str, Any]]:
    loc = func.timezone("Asia/Riyadh", WbgtReading.measured_at)
    rows = db.execute(
        select(MonitoringPoint.point_code, func.date(loc), func.max(WbgtReading.wbgt_c))
        .join(MonitoringPoint, MonitoringPoint.id == WbgtReading.point_id)
        .where(
            WbgtReading.project_id == project_id,
            WbgtReading.status == RecordStatus.valid,
            WbgtReading.measured_at >= hc.day_start(w.start),
            WbgtReading.measured_at < hc.day_start(w.end + timedelta(days=1)),
        )
        .group_by(MonitoringPoint.point_code, func.date(loc))
    )
    per: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for code, d, mx in rows:
        per[(code, d.strftime("%Y-%m"))].append(Decimal(mx))
    return [
        {
            "point_code": code,
            "month": mon,
            "max_c": str(max(v)),
            "mean_daily_max_c": str(hc.q1(sum(v, Decimal(0)) / len(v))),
        }
        for (code, mon), v in sorted(per.items())
    ]


def compute(db: Session, project_id: uuid.UUID, year: int, as_of: date) -> dict[str, Any]:
    """§8.4 metrics of the season (period = the controls period of `year`, up to as_of)."""
    full = season_window(db, project_id, year)
    w = Window(full.start, min(full.end, max(as_of, full.start)))
    e = _engine(db, project_id, as_of)
    a = e.aggregate(w)
    months = _months(w)
    zones = hc.zone_map(db, project_id)
    k103 = _kv(e, M.K103, w)
    rows = kh.entries(e, w)
    gaps = kh.entries(e, w, source_only=False)
    by_month_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for x in rows:
        by_month_cat[x.d.strftime("%Y-%m")][x.category.value if x.category else "unknown"] += 1
    prev = None
    pw = season_window(db, project_id, year - 1)
    pe = _engine(db, project_id, pw.end)
    prev_rows = kh.entries(pe, pw)
    if prev_rows:
        prev = _kv(pe, M.K103, pw)
    bs = kh.ban_stats(e, w)
    eng_codes = {x.id: x.code for x in e.facts.engagements.values()}
    plans = kh.plan_stats(e, w)[2]
    merged = {
        "new_worker": plans.get(PlanType.new_worker.value, 0),
        "returner": plans.get(PlanType.returner.value, 0)
        + plans.get(PlanType.post_heat_illness.value, 0),
        "period_start": plans.get(PlanType.period_start.value, 0),
    }
    cas = list(
        db.scalars(
            select(CorrectiveAction.status).where(
                CorrectiveAction.project_id == project_id,
                CorrectiveAction.source_type == CaSourceType.heat_check,
                CorrectiveAction.created_at >= hc.day_start(w.start),
                CorrectiveAction.created_at < hc.day_start(w.end + timedelta(days=1)),
            )
        )
    )
    exemptions = int(
        db.scalar(
            select(func.count(BanExemption.id)).where(
                BanExemption.project_id == project_id,
                BanExemption.date_from <= w.end,
                BanExemption.date_to >= w.start,
            )
        )
        or 0
    )
    return {
        "period_from": w.start.isoformat(),
        "period_to": w.end.isoformat(),
        "as_of": as_of.isoformat(),
        "k01_man_hours": fmt.exact(a.mh),
        "season": {m.value: _kv(e, m, w) for m in kh_metrics()},
        "coverage_by_month": [
            {
                "month": mw.start.strftime("%Y-%m"),
                "K-97": _kv(e, M.K97, mw)["display"],
                "K-99": _kv(e, M.K99, mw)["display"],
                "K-101": _kv(e, M.K101, mw)["display"],
            }
            for mw in months
        ],
        "wbgt_by_point_month": _wbgt(db, project_id, w),
        "k98_by_zone": [
            {
                "zone_code": zones[z].code,
                **{b: fmt.dec_str(v, 1) for b, v in kh.k98_hours(e, w, z).items()},
            }
            for p in (kh.hfacts(e).all() if kh.hfacts(e) else [])  # type: ignore[union-attr]
            for z in p.required
            if z in zones
        ],
        "midday_ban": {
            "patrols": bs.patrols,
            "violations": bs.violations,
            "violations_by_contractor": {
                eng_codes.get(k, "?"): n for k, n in sorted(bs.by_eng.items(), key=str)
            },
            "exemptions_granted": exemptions,
            "K-99": _kv(e, M.K99, w)["display"],
        },
        "acclimatisation": {"plans_by_type": merged, "K-102": _kv(e, M.K102, w)["display"]},
        "heat_illness": {
            "cases": k103["value"],
            "rate": k103.get("rate"),
            "recordable": k103.get("recordable"),
            "recordable_rate": k103.get("recordable_rate"),
            "by_month_category": {k: dict(v) for k, v in sorted(by_month_cat.items())},
            "control_gap_share_pct": (
                fmt.dec_str(Decimal(sum(1 for x in gaps if x.control_gap)) * 100 / len(gaps), 1)
                if gaps
                else None
            ),
            "previous_season": prev,
        },
        "heat_awr_compliance": None,  # parked (PROGRESS): Phase 5 K-82 filtered to HEAT-AWR
        "corrective_actions": {
            "raised": len(cas),
            "closed": sum(1 for s in cas if s == CaStatus.closed),
        },
    }


def kh_metrics() -> list[KpiMetric]:
    return [M.K97, M.K98, M.K99, M.K100, M.K101, M.K102, M.K103]


def _viewer(p: Principal, project_id: uuid.UUID) -> bool:
    if p.is_manager:
        return False
    ps = p.projects.get(project_id)
    return ps is not None and ps.roles == {Role.viewer_client}


def _read(db: Session, x: HeatSeasonReport) -> SeasonReportRead:
    return SeasonReportRead(
        report_no=x.report_no,
        project_id=x.project_id,
        season_year=x.season_year,
        revision=x.revision,
        status=x.status,
        period_from=x.period_from,
        period_to=x.period_to,
        metrics=x.metrics,
        comments_en=x.comments_en,
        comments_ar=x.comments_ar,
        issued_by=hc.user_ref(db, x.issued_by_user_id),
        issued_at=x.issued_at,
    )


def default_year(db: Session, project_id: uuid.UUID, today: date) -> int:
    s, _e = hc.cfg(db, project_id).controls_window(today.year)
    return today.year if today >= s else today.year - 1


def season_reports(
    db: Session, p: Principal, project_id: uuid.UUID, season_year: int | None
) -> SeasonReportList:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_kpi_view, write=False)
    today = hc.local_day()
    year = season_year or default_year(db, project_id, today)
    w = season_window(db, project_id, year)
    issued = list(
        db.scalars(
            select(HeatSeasonReport)
            .where(
                HeatSeasonReport.project_id == project_id,
                HeatSeasonReport.season_year == year,
            )
            .order_by(HeatSeasonReport.revision.desc())
        )
    )
    draft = None
    if not _viewer(p, project_id) and today >= w.start:
        draft = SeasonReportRead(
            report_no=None,
            project_id=project_id,
            season_year=year,
            revision=None,
            status=SeasonReportStatus.draft,
            period_from=w.start,
            period_to=w.end,
            metrics=compute(db, project_id, year, today),
            comments_en=None,
            comments_ar=None,
            issued_by=None,
            issued_at=None,
        )
    return SeasonReportList(draft=draft, issued=[_read(db, x) for x in issued])


def issue(
    db: Session, p: Principal, project_id: uuid.UUID, body: SeasonReportIssue
) -> SeasonReportRead:
    hc.project(db, p, project_id)
    p.require(project_id, C.heat_settings_edit)
    today = hc.local_day()
    w = season_window(db, project_id, body.season_year)
    if today < w.start:
        raise validation_error("season_year", "The season has not started yet.")
    prev = db.scalars(
        select(HeatSeasonReport)
        .where(
            HeatSeasonReport.project_id == project_id,
            HeatSeasonReport.season_year == body.season_year,
        )
        .order_by(HeatSeasonReport.revision.desc())
    ).first()
    why = hc.reason(body.reason, 20) if prev is not None else None
    at = now()
    if prev is not None:
        prev.status, prev.superseded_at = SeasonReportStatus.superseded, at
    rev = (prev.revision if prev else 0) + 1
    x = HeatSeasonReport(
        id=uuid.uuid4(),
        report_no=f"HSR-{hc.pcode(db, project_id)}-{body.season_year}-r{rev}",
        project_id=project_id,
        season_year=body.season_year,
        revision=rev,
        period_from=w.start,
        period_to=w.end,
        status=SeasonReportStatus.issued,
        metrics=compute(db, project_id, body.season_year, today),
        comments_en=body.comments_en,
        comments_ar=body.comments_ar,
        reissue_reason=why,
        issued_by_user_id=p.user.id,
        issued_at=at,
    )
    db.add(x)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.heat_season_report, x, project_id)
    return _read(db, x)
