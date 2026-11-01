"""Quality KPIs K-141…K-169 (spec 8-quality §E.4, Q-KPI), COPQ / DPMO / sigma / Pareto (§E.6),
targets with RAG, and the warnings E26–E28 (§E.7).

The engine works per project and period (local dates) at `as_of`: counts are aggregated in SQL
from the Phase 8 tables; the parts' own definitions are reused where they exist — Q1
`kpi.ir_counts` / `punch_counts` (K-141, K-142, K-149 ir_inspection, K-156), Q2 competence cells
(K-155), Q3 `metrics.month` (K-160…K-168, which reads the `q_zone_days` cached sums of D-351; it
is called once per month of the period and memoised, never once per tile). Records before
`quality_start_date`, voided NCRs, voided holds, voided and dismissed excursions are excluded.
Rounding half-up at output only; a zero denominator gives None ("—")."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import NormalDist
from typing import Any

from sqlalchemy import and_, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.core.hse_enums import QUALITY_CA_SOURCES, CaStatus
from app.core.quality.common import INTERNAL_STAGES, QNcrClass, QNcrStatus, QSectorProfile
from app.core.quality.q4 import QKpi, QWarning
from app.models import CorrectiveAction, Project
from app.models.quality import QComplaint, QMteItem, QNcr, QNcrCost, QObservation, QSettings
from app.models.quality.q4 import QKpiTarget, QWorkValue

D = Decimal
K = QKpi
C_, L_, B_ = "construction", "logistics", "both"

# id: (EN, AR, profile, unit, better)
CATALOGUE: dict[QKpi, tuple[str, str, str, str, str]] = {
    K.K141: ("First-time pass rate", "نسبة النجاح من أول مرة", C_, "%", "higher"),
    K.K142: ("IR rejection rate", "نسبة رفض طلبات الفحص", C_, "%", "lower"),
    K.K143: ("NCRs raised", "تقارير عدم المطابقة الصادرة", B_, "count", "none"),
    K.K144: ("NCR ageing", "تقادم التقارير المفتوحة", B_, "count", "lower"),
    K.K145: ("NCR closure time", "زمن إغلاق التقارير", B_, "days", "lower"),
    K.K146: ("NCR on-time closure", "إغلاق التقارير في الموعد", B_, "%", "higher"),
    K.K147: ("Repeat NCR rate", "نسبة التقارير المتكررة", B_, "%", "lower"),
    K.K148: ("Cost of poor quality", "تكلفة الجودة الرديئة", B_, "SAR", "lower"),
    K.K149: ("DPMO and sigma level", "العيوب لكل مليون فرصة ومستوى سيجما", B_, "dpmo", "lower"),
    K.K150: ("Pareto of defect causes", "باريتو أسباب العيوب", B_, "count", "none"),
    K.K151: ("Material rejection rate", "نسبة رفض المواد", C_, "%", "lower"),
    K.K152: ("Test failure rate", "نسبة فشل الاختبارات", B_, "%", "lower"),
    K.K153: ("Weld repair rate", "نسبة إصلاح اللحام", C_, "%", "lower"),
    K.K154: ("Calibration compliance", "الالتزام بالمعايرة", B_, "%", "higher"),
    K.K155: ("Competence compliance", "الالتزام بالكفاءة", B_, "%", "higher"),
    K.K156: ("Punch closure", "إغلاق النواقص", C_, "%", "higher"),
    K.K157: ("Supplier quality score", "درجة جودة الموردين", B_, "points", "higher"),
    K.K158: (
        "Quality audit programme compliance",
        "الالتزام ببرنامج تدقيق الجودة",
        B_,
        "%",
        "higher",
    ),
    K.K159: ("Document control", "ضبط الوثائق", B_, "%", "higher"),
    K.K160: ("Receiving rejection rate", "نسبة رفض الاستلام", L_, "%", "lower"),
    K.K161: ("Excursions per zone-month", "الانحرافات لكل منطقة شهرياً", L_, "rate", "lower"),
    K.K162: ("Time out of range", "الزمن خارج النطاق", L_, "%", "lower"),
    K.K163: ("On time in full (OTIF)", "التسليم في الموعد وكاملاً", L_, "%", "higher"),
    K.K164: ("Damage rate", "نسبة التلف", L_, "%", "lower"),
    K.K165: ("Inventory record accuracy", "دقة سجلات المخزون", L_, "%", "higher"),
    K.K166: ("FEFO compliance", "الالتزام بالأقدم انتهاءً أولاً", L_, "%", "higher"),
    K.K167: ("Transport temperature compliance", "الالتزام الحراري في النقل", L_, "%", "higher"),
    K.K168: (
        "Hygiene and pest check compliance",
        "الالتزام بفحوص النظافة والآفات",
        L_,
        "%",
        "higher",
    ),
    K.K169: ("Customer complaints", "شكاوى العملاء", B_, "count", "lower"),
}
TILES = {
    "construction": [K.K141, K.K143, K.K144, K.K148, K.K152, K.K153, K.K154, K.K156],
    "logistics": [K.K160, K.K161, K.K162, K.K163, K.K164, K.K165, K.K167, K.K168],
    "both": [K.K146, K.K149, K.K155, K.K157, K.K158, K.K159, K.K169],
}
DPMO_PROCESSES = (
    "ir_inspection",
    "mir_inspection",
    "receiving",
    "picking_fefo",
    "delivery",
    "inventory",
)
CONSTRUCTION_PROCESSES = ("ir_inspection", "mir_inspection")


def q(v: Decimal | float | int | None, dp: str = "0.1") -> Decimal | None:
    if v is None:
        return None
    return D(str(v)).quantize(D(dp), ROUND_HALF_UP)


def pct(n: int | Decimal, d: int | Decimal, dp: str = "0.1") -> Decimal | None:
    if not d:
        return None
    return q(D(n) * 100 / D(d), dp)


def sigma_level(dpmo: Decimal | float | None) -> tuple[Decimal | None, str]:
    """Q-SIX-03: Φ⁻¹(1 − DPMO ÷ 10⁶) + 1.5 (2 dp); DPMO 0 → "> 6.0"."""
    if dpmo is None:
        return None, "—"
    if D(str(dpmo)) <= 0:
        return None, "> 6.0"
    p = 1 - float(dpmo) / 1_000_000
    if p <= 0:
        return D("0.00"), "0.00"
    s = q(NormalDist().inv_cdf(p) + 1.5, "0.01")
    return s, str(s)


def dpmo_of(defects: int, units_x_opps: int) -> Decimal | None:
    """Q-SIX-02: defects ÷ (units × opportunities) × 10⁶ (1 dp)."""
    if not units_x_opps:
        return None
    return q(D(defects) * 1_000_000 / D(units_x_opps), "0.1")


def pareto(counts: dict[str, int]) -> dict[str, Any]:
    """Q-SIX-04: sorted by count (ties by code), cumulative %, vital few = the smallest leading
    set whose cumulative % ≥ 80.0."""
    rows = sorted(((k, v) for k, v in counts.items() if v), key=lambda x: (-x[1], x[0]))
    total = sum(v for _, v in rows)
    run, out, few = 0, [], 0
    for code, n in rows:
        run += n
        cum = D(run) * 100 / D(total)
        out.append(
            {
                "code": code,
                "count": n,
                "pct": str(q(D(n) * 100 / D(total))),
                "cumulative_pct": str(q(cum)),
            }
        )
        if not few and cum >= 80:
            few = len(out)
    return {"total": total, "rows": out, "vital_few": few}


@dataclass
class QFilter:
    """Filters of §E.4 (sites, zone, engagement tree, supplier, discipline, storage class, test
    type). NCR-based KPIs apply all of them; part counts apply what their records carry."""

    site_ids: frozenset[uuid.UUID] | None = None
    zone_id: uuid.UUID | None = None
    engagement_ids: frozenset[uuid.UUID] | None = None
    supplier_id: uuid.UUID | None = None
    discipline: str | None = None
    storage_class: str | None = None
    test_type: str | None = None

    @property
    def narrowed(self) -> bool:
        """A site- or engagement-narrowed view (grant or filter): project-wide-only figures
        are hidden (D-360)."""
        return self.site_ids is not None or self.engagement_ids is not None

    def at(self, site_col: Any = None, eng_col: Any = None) -> list[Any]:
        """Site / engagement conditions on a source's own columns (None column = not
        applicable to that source, e.g. logistics records carry no engagement, Q-RPM-07)."""
        cs: list[Any] = []
        if site_col is not None and self.site_ids is not None:
            cs.append(site_col.in_(list(self.site_ids) or [uuid.uuid4()]))
        if eng_col is not None and self.engagement_ids is not None:
            cs.append(eng_col.in_(list(self.engagement_ids) or [uuid.uuid4()]))
        return cs

    def ncr(self) -> list[Any]:
        cs: list[Any] = []
        if self.site_ids is not None:
            cs.append(QNcr.site_id.in_(list(self.site_ids) or [uuid.uuid4()]))
        if self.zone_id is not None:
            cs.append(QNcr.zone_id == self.zone_id)
        if self.engagement_ids is not None:
            cs.append(
                QNcr.responsible_engagement_id.in_(list(self.engagement_ids) or [uuid.uuid4()])
            )
        if self.supplier_id is not None:
            cs.append(QNcr.supplier_id == self.supplier_id)
        return cs


@dataclass
class Result:
    kpi: QKpi
    value: Decimal | None
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    display: str = "—"
    chips: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def dump(self) -> dict[str, Any]:
        en, ar, prof, unit, better = CATALOGUE[self.kpi]
        return {
            "kpi": self.kpi.value,
            "name_en": en,
            "name_ar": ar,
            "profile": prof,
            "unit": unit,
            "better": better,
            "value": str(self.value) if self.value is not None else None,
            "numerator": str(self.numerator) if self.numerator is not None else None,
            "denominator": str(self.denominator) if self.denominator is not None else None,
            "display": self.display,
            "chips": self.chips,
            "extra": self.extra,
        }


def chip(code: str, en: str, ar: str, value: Any) -> dict[str, Any]:
    return {
        "code": code,
        "label_en": en,
        "label_ar": ar,
        "value": str(value) if value is not None else None,
    }


def disp(v: Decimal | None, unit: str) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return f"{v} %"
    if unit == "SAR":
        return f"SAR {v:,.2f}"
    return str(v)


class Engine:
    """One project, one period [start, end], one as_of. Memoises the parts' monthly inputs."""

    def __init__(
        self,
        db: Session,
        project: Project,
        start: date,
        end: date,
        as_of: date,
        flt: QFilter | None = None,
    ) -> None:
        self.db, self.project, self.as_of = db, project, as_of
        qs = db.get(QSettings, project.id)
        self.profile: QSectorProfile | None = qs.sector_profile if qs else None
        qstart = qs.quality_start_date if qs and qs.quality_start_date else None
        self.start = max(start, qstart) if qstart else start
        self.end = end
        self.until = min(end, as_of)
        self.flt = flt or QFilter()
        self._memo: dict[str, Any] = {}

    # ---- memo helpers ----------------------------------------------------------------------

    def memo(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    def hidden(self, k: QKpi) -> bool:
        """KPIs that cannot be narrowed to a grant's sites / engagement tree are not shown to
        a narrowed view (D-360): K-155 (quality people's competence), K-158 (the audit
        programme), K-159 (document control), and K-169 under an engagement narrowing outside
        logistics (complaints carry no engagement)."""
        if not self.flt.narrowed:
            return False
        if k in (K.K155, K.K158, K.K159):
            return True
        return (
            k == K.K169
            and self.flt.engagement_ids is not None
            and self.profile != QSectorProfile.logistics
        )

    def months(self) -> list[tuple[int, int]]:
        out, d = [], self.start.replace(day=1)
        while d <= self.end:
            out.append((d.year, d.month))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        return out

    def logistics(self) -> list[dict[str, Any]]:
        """Q3 month metrics, read once per month of the period (cached day sums, D-351)."""
        from app.services.quality.q3 import metrics as q3m  # noqa: PLC0415

        out: list[dict[str, Any]] = self.memo(
            "q3",
            lambda: [
                q3m.month(self.db, self.project, y, m, self.flt.site_ids) for y, m in self.months()
            ],
        )
        return out

    def ir(self) -> Any:
        from app.services.quality.q1 import kpi as q1k  # noqa: PLC0415

        return self.memo(
            "ir",
            lambda: q1k.ir_counts(
                self.db,
                self.project.id,
                self.start,
                self.end,
                site_ids=self.flt.site_ids,
                engagement_ids=self.flt.engagement_ids,
            ),
        )

    def punch(self) -> Any:
        from app.services.quality.q1 import kpi as q1k  # noqa: PLC0415

        return self.memo(
            "punch",
            lambda: q1k.punch_counts(
                self.db,
                self.project.id,
                self.start,
                self.end,
                self.until,
                site_ids=self.flt.site_ids,
                engagement_ids=self.flt.engagement_ids,
            ),
        )

    # ---- NCR SQL ---------------------------------------------------------------------------

    def _ncr_base(self) -> list[Any]:
        return [
            QNcr.project_id == self.project.id,
            QNcr.status != QNcrStatus.voided,
            QNcr.status != QNcrStatus.draft,
            QNcr.before_quality_start.is_(False),
            *self.flt.ncr(),
        ]

    def _opened(self) -> list[Any]:
        return [*self._ncr_base(), QNcr.opened_date >= self.start, QNcr.opened_date <= self.end]

    def _open_at(self, day: date) -> list[Any]:
        return [
            *self._ncr_base(),
            QNcr.opened_date <= day,
            or_(QNcr.closed_date.is_(None), QNcr.closed_date > day),
        ]

    # ---- KPIs ------------------------------------------------------------------------------

    def k141(self) -> Result:
        c = self.ir()
        v = pct(c.first_passes, c.first_rounds)
        return Result(
            K.K141,
            v,
            D(c.first_passes),
            D(c.first_rounds),
            disp(v, "%"),
            [
                chip("k142", "IR rejection rate", "نسبة الرفض", c.rejection_rate),
                chip("waived", "Waived witness points", "نقاط الشهود المتنازل عنها", c.waived),
                chip("short_notice", "Short notice", "إشعار قصير", c.short_notice),
                chip(
                    "paper_pct",
                    "Paper sign-off %",
                    "نسبة التوقيع الورقي",
                    pct(c.paper_signoffs, c.rounds_decided),
                ),
            ],
        )

    def k142(self) -> Result:
        c = self.ir()
        v = pct(c.rounds_failed, c.rounds_decided)
        return Result(K.K142, v, D(c.rounds_failed), D(c.rounds_decided), disp(v, "%"))

    def k143(self) -> Result:
        db = self.db
        rows = dict(
            db.execute(
                select(QNcr.classification, func.count())
                .where(*self._opened())
                .group_by(QNcr.classification)
            ).all()
        )
        total = sum(rows.values())
        open_ = (
            db.scalar(select(func.count()).select_from(QNcr).where(*self._open_at(self.until))) or 0
        )
        by = {
            c.value: int(rows.get(c, 0))
            for c in (QNcrClass.minor, QNcrClass.major, QNcrClass.critical)
        }
        return Result(
            K.K143,
            D(total),
            D(total),
            None,
            str(total),
            [
                chip("minor", "Minor", "بسيط", by["minor"]),
                chip("major", "Major", "جوهري", by["major"]),
                chip("critical", "Critical", "حرج", by["critical"]),
                chip("open", "Open at as of", "مفتوحة", open_),
            ],
            {"by_class": by, "open": int(open_)},
        )

    def k144(self) -> Result:
        day = self.until
        age = literal(day, QNcr.opened_date.type) - QNcr.opened_date
        rows = self.db.execute(select(QNcr.classification, age).where(*self._open_at(day))).all()
        buckets = {"0_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
        by_class: dict[str, dict[str, int]] = {}
        ages = []
        for cls, age_ in rows:
            a = int(age_)
            ages.append(a)
            k = "0_30" if a <= 30 else "31_60" if a <= 60 else "61_90" if a <= 90 else "over_90"
            buckets[k] += 1
            by_class.setdefault(cls.value if cls else "unclassified", dict.fromkeys(buckets, 0))[
                k
            ] += 1
        mean = q(D(sum(ages)) / len(ages)) if ages else None
        return Result(
            K.K144,
            D(len(ages)),
            D(len(ages)),
            None,
            f"{buckets['0_30']} / {buckets['31_60']} / {buckets['61_90']} / {buckets['over_90']}",
            [chip("mean_age", "Mean age (days)", "متوسط العمر (أيام)", mean)],
            {"buckets": buckets, "by_class": by_class, "as_of": day.isoformat()},
        )

    def k145(self) -> Result:
        days = QNcr.closed_date - QNcr.opened_date
        med, mean, n = self.db.execute(
            select(
                func.percentile_cont(0.5).within_group(days), func.avg(days), func.count()
            ).where(
                *self._ncr_base(),
                QNcr.status == QNcrStatus.closed,
                QNcr.closed_date >= self.start,
                QNcr.closed_date <= self.end,
            )
        ).one()
        v = q(med, "1") if n else None
        return Result(
            K.K145,
            v,
            None,
            D(n),
            f"{v} d" if v is not None else "—",
            [chip("mean", "Mean (days)", "المتوسط (أيام)", q(mean) if n else None)],
        )

    def k146(self) -> Result:
        due, ok = self.db.execute(
            select(
                func.count(),
                func.count().filter(
                    and_(
                        QNcr.status == QNcrStatus.closed,
                        QNcr.closed_date <= QNcr.target_close_date,
                        QNcr.closed_date <= self.until,
                    )
                ),
            ).where(
                *self._ncr_base(),
                QNcr.target_close_date >= self.start,
                QNcr.target_close_date <= self.until,
            )
        ).one()
        ca_due, ca_ok = self.db.execute(
            select(
                func.count(),
                func.count().filter(
                    and_(
                        CorrectiveAction.status == CaStatus.closed,
                        CorrectiveAction.verified_date <= CorrectiveAction.due_date,
                    )
                ),
            ).where(
                CorrectiveAction.project_id == self.project.id,
                CorrectiveAction.source_type.in_(list(QUALITY_CA_SOURCES)),
                CorrectiveAction.status != CaStatus.cancelled,
                CorrectiveAction.due_date >= self.start,
                CorrectiveAction.due_date <= self.until,
                *self.flt.at(CorrectiveAction.site_id, CorrectiveAction.responsible_engagement_id),
            )
        ).one()
        v = pct(ok, due)
        return Result(
            K.K146,
            v,
            D(ok),
            D(due),
            disp(v, "%"),
            [
                chip(
                    "quality_ca_ontime",
                    "Quality CA on-time closure",
                    "إغلاق إجراءات الجودة في الموعد",
                    pct(ca_ok, ca_due),
                )
            ],
        )

    def k147(self) -> Result:
        n, rep = self.db.execute(
            select(func.count(), func.count().filter(QNcr.repeat_of_id.is_not(None))).where(
                *self._opened()
            )
        ).one()
        v = pct(rep, n)
        return Result(K.K147, v, D(rep), D(n), disp(v, "%"))

    def k148(self) -> Result:
        db = self.db
        internal = QNcr.detection_stage.in_(list(INTERNAL_STAGES))
        gross, inn, rec = db.execute(
            select(
                func.coalesce(func.sum(QNcrCost.amount_sar), 0),
                func.coalesce(func.sum(QNcrCost.amount_sar).filter(internal), 0),
                func.coalesce(func.sum(QNcrCost.recovered_sar), 0),
            )
            .join(QNcr, QNcr.id == QNcrCost.ncr_id)
            .where(*self._opened())
        ).one()
        gross, inn, rec = D(gross), D(inn), D(rec)
        wv = (
            None
            if self.flt.narrowed
            else db.scalar(
                select(func.sum(QWorkValue.value_sar)).where(
                    QWorkValue.project_id == self.project.id,
                    QWorkValue.month >= self.start.replace(day=1),
                    QWorkValue.month <= self.end,
                )
            )
        )
        not_closed = (
            db.scalar(
                select(func.count())
                .select_from(QNcr)
                .where(*self._opened(), QNcr.status != QNcrStatus.closed)
            )
            or 0
        )
        copq = pct(gross, D(wv), "0.01") if wv else None
        v = q(gross, "0.01")
        return Result(
            K.K148,
            v,
            v,
            D(wv) if wv else None,
            disp(v, "SAR"),
            [
                chip("internal", "Internal failure", "فشل داخلي", q(inn, "0.01")),
                chip("external", "External failure", "فشل خارجي", q(gross - inn, "0.01")),
                chip("recovered", "Recovered", "مسترد", q(rec, "0.01")),
                chip("net", "Net", "الصافي", q(gross - rec, "0.01")),
                chip("copq_pct", "COPQ % of work value", "نسبة التكلفة من قيمة الأعمال", copq),
            ],
            {"provisional": bool(not_closed), "work_value": str(q(D(wv), "0.01")) if wv else None},
        )

    def dpmo(self) -> dict[str, dict[str, Any]]:
        """K-149 per process (Q-SIX-02, `dpmo_processes` opportunities)."""
        return self.memo("dpmo", self._dpmo)  # type: ignore[no-any-return]

    def _dpmo(self) -> dict[str, dict[str, Any]]:
        from app.services.quality.q4 import base as b  # noqa: PLC0415

        cfg = b.setting(self.db, self.project.id, "dpmo_processes") or {}
        out: dict[str, dict[str, Any]] = {}

        def put(code: str, units: int, opps: int, defects: int) -> None:
            d = dpmo_of(defects, opps)
            s, sd = sigma_level(d)
            out[code] = {
                "units": units,
                "opportunities": opps,
                "defects": defects,
                "dpmo": str(d) if d is not None else None,
                "sigma": str(s) if s is not None else None,
                "sigma_display": sd,
            }

        if self._has_construction():
            c = self.ir()
            put(
                "ir_inspection",
                c.first_rounds + max(c.rounds_decided - c.first_rounds, 0),
                c.opportunities,
                c.defects,
            )
            u, o, dfx = self._mir_opps()
            put("mir_inspection", u, o, dfx)
        if self._has_logistics():
            a, e = self._bounds()
            units, defects = self.db.execute(
                text(
                    "select count(distinct l.id), coalesce(sum((select count(*) from "
                    "jsonb_array_elements(l.proposal_reasons) r "
                    "where r->>'decision' <> 'accept')), 0) "
                    "from q_receipt_lines l join q_receipts r on r.id = l.receipt_id "
                    "where r.project_id = :p and r.status = 'decided' and r.decided_at >= :a "
                    "and r.decided_at < :e and (cast(:all_sites as boolean) "
                    "or r.site_id = any(cast(:sites as uuid[])))"
                ),
                {
                    "p": self.project.id,
                    "a": a,
                    "e": e,
                    "all_sites": self.flt.site_ids is None,
                    "sites": [str(x) for x in self.flt.site_ids or ()],
                },
            ).one()
            opp = int(cfg.get("receiving", 4))
            put("receiving", int(units), int(units) * opp, int(defects))
            lg = self.logistics()
            checks = sum(m["k166"]["checks"] for m in lg)
            ok = sum(m["k166"]["counted_compliant"] for m in lg)
            put("picking_fefo", checks, checks * int(cfg.get("picking_fefo", 1)), checks - ok)
            sh = sum(m["k163"]["shipments"] for m in lg)
            miss = sum(
                (m["k163"]["shipments"] - m["k163"]["on_time"])
                + (m["k163"]["shipments"] - m["k163"]["in_full"])
                for m in lg
            )
            put("delivery", sh, sh * int(cfg.get("delivery", 2)), miss)
            ln = sum(m["k165"]["lines"] for m in lg)
            w = sum(m["k165"]["within"] for m in lg)
            put("inventory", ln, ln * int(cfg.get("inventory", 1)), ln - w)
        return out

    def _bounds(self) -> tuple[Any, Any]:
        from app.services.quality.q4 import base as b  # noqa: PLC0415

        return b.day_start(self.start), b.day_start(self.end + timedelta(days=1))

    def _mir_opps(self) -> tuple[int, int, int]:
        from app.models.field import ChecklistResponse  # noqa: PLC0415
        from app.models.quality.q2 import QMir  # noqa: PLC0415

        a, e = self._bounds()
        u, o, c = self.db.execute(
            select(
                func.count(QMir.id),
                func.coalesce(func.sum(ChecklistResponse.applicable_count), 0),
                func.coalesce(func.sum(ChecklistResponse.compliant_count), 0),
            )
            .outerjoin(ChecklistResponse, ChecklistResponse.id == QMir.checklist_response_id)
            .where(
                QMir.project_id == self.project.id,
                QMir.status == "decided",
                QMir.decided_at >= a,
                QMir.decided_at < e,
                *self.flt.at(QMir.site_id, QMir.engagement_id),
            )
        ).one()
        return int(u), int(o), int(o) - int(c)

    def _has_construction(self) -> bool:
        return self.profile in (None, QSectorProfile.construction) or bool(self.ir().rounds_decided)

    def _has_logistics(self) -> bool:
        return self.profile == QSectorProfile.logistics

    def k149(self) -> Result:
        procs = self.dpmo()
        main = (
            procs.get("ir_inspection") or procs.get("receiving") or next(iter(procs.values()), None)
        )
        v = D(main["dpmo"]) if main and main["dpmo"] else None
        return Result(
            K.K149,
            v,
            None,
            None,
            f"{main['dpmo']} · σ {main['sigma_display']}" if main and main["dpmo"] else "—",
            [
                chip(k, k.replace("_", " "), k, f"{x['dpmo'] or '—'} / σ {x['sigma_display']}")
                for k, x in procs.items()
            ],
            {"processes": procs},
        )

    def k150(self, by: str = "category") -> Result:
        from app.services.quality.q4 import base as b  # noqa: PLC0415

        col = QNcr.cause_category if by == "cause_category" else QNcr.category
        counts = {
            (k.value if k else "uncategorised"): int(n)
            for k, n in self.db.execute(
                select(col, func.count()).where(*self._opened()).group_by(col)
            )
        }
        if by == "category" and b.setting(self.db, self.project.id, "pareto_include_observations"):
            for k, n in self.db.execute(
                select(QObservation.category, func.count())
                .where(
                    QObservation.project_id == self.project.id,
                    func.date(QObservation.created_at) >= self.start,
                    func.date(QObservation.created_at) <= self.end,
                    *self.flt.at(QObservation.site_id, QObservation.engagement_id),
                )
                .group_by(QObservation.category)
            ):
                key = getattr(k, "value", str(k)) if k else "uncategorised"
                counts[key] = counts.get(key, 0) + int(n)
        par = pareto(counts)
        return Result(
            K.K150,
            D(par["total"]),
            None,
            None,
            f"vital few {par['vital_few']}",
            [],
            {"pareto": par, "by": by},
        )

    def k151(self) -> Result:
        from app.models.quality.q2 import QMir  # noqa: PLC0415

        a, e = self._bounds()
        n, rej, qty, rq = self.db.execute(
            select(
                func.count(),
                func.count().filter(QMir.rejected_qty > 0),
                func.coalesce(func.sum(QMir.quantity), 0),
                func.coalesce(func.sum(QMir.rejected_qty), 0),
            ).where(
                QMir.project_id == self.project.id,
                QMir.status == "decided",
                QMir.decided_at >= a,
                QMir.decided_at < e,
                *self.flt.at(QMir.site_id, QMir.engagement_id),
            )
        ).one()
        v = pct(rej, n)
        return Result(
            K.K151,
            v,
            D(rej),
            D(n),
            disp(v, "%"),
            [chip("by_qty", "By quantity", "بالكمية", pct(D(rq or 0), D(qty or 0)))],
        )

    def k152(self) -> Result:
        from app.models.quality.q2 import QTestRequest  # noqa: PLC0415

        a, e = self._bounds()
        conds = [
            QTestRequest.project_id == self.project.id,
            QTestRequest.verdict.in_(["pass", "fail"]),
            QTestRequest.results_entered_at >= a,
            QTestRequest.results_entered_at < e,
            QTestRequest.status != "voided",
            *self.flt.at(QTestRequest.site_id, QTestRequest.engagement_id),
        ]
        if self.flt.test_type:
            conds.append(QTestRequest.test_type_code == self.flt.test_type)
        rows = self.db.execute(
            select(
                QTestRequest.test_type_code,
                func.count(),
                func.count().filter(QTestRequest.verdict == "fail"),
            )
            .where(*conds)
            .group_by(QTestRequest.test_type_code)
        ).all()
        n = sum(int(r[1]) for r in rows)
        f = sum(int(r[2]) for r in rows)
        v = pct(f, n)
        return Result(
            K.K152,
            v,
            D(f),
            D(n),
            disp(v, "%"),
            [chip(f"tt:{r[0]}", r[0], r[0], pct(r[2], r[1])) for r in rows],
        )

    def k153(self) -> Result:
        n, rej = self.db.execute(
            text(
                "select count(*), count(*) filter (where r->>'result' = 'reject') from q_welds w, "
                "jsonb_array_elements(w.ndt_results) r where w.project_id = :p "
                "and w.status <> 'voided' "
                "and (r->>'repair_round') = '0' and (r->>'examined_on')::date between :s and :e "
                "and (cast(:all_sites as boolean) or w.site_id = any(cast(:sites as uuid[]))) "
                "and (cast(:all_engs as boolean) "
                "or w.engagement_id = any(cast(:engs as uuid[])))"
            ),
            {
                "p": self.project.id,
                "s": self.start,
                "e": self.end,
                "all_sites": self.flt.site_ids is None,
                "sites": [str(x) for x in self.flt.site_ids or ()],
                "all_engs": self.flt.engagement_ids is None,
                "engs": [str(x) for x in self.flt.engagement_ids or ()],
            },
        ).one()
        v = pct(rej, n)
        return Result(K.K153, v, D(rej), D(n), disp(v, "%"))

    def k154(self) -> Result:
        """Active M&TE with a check kind, not out of service, calibrated or due soon at the day
        (due date not passed and the last calibration not left out of tolerance)."""
        from app.models.quality.q2 import QCalibration, QMteCalOverride  # noqa: PLC0415

        day = self.until
        oos = select(QMteCalOverride.mte_id).where(QMteCalOverride.status == "out_of_service")
        bad = select(QCalibration.id).where(
            QCalibration.id == QMteItem.last_calibration_id, QCalibration.as_left_ok.is_(False)
        )
        base_ = [
            QMteItem.project_id == self.project.id,
            QMteItem.status == "active",
            QMteItem.check_kind != "none",
            QMteItem.id.not_in(oos),
            ~bad.exists(),
            *self.flt.at(QMteItem.site_id, QMteItem.owner_engagement_id),
        ]
        n, ok = self.db.execute(
            select(func.count(), func.count().filter(QMteItem.cal_due_on >= day)).where(*base_)
        ).one()
        from app.models.quality.q2 import QOotReview  # noqa: PLC0415

        oot = (
            self.db.scalar(
                select(func.count())
                .select_from(QOotReview)
                .where(
                    QOotReview.project_id == self.project.id,
                    QOotReview.status != "closed",
                    *(
                        [
                            QOotReview.mte_id.in_(
                                select(QMteItem.id).where(
                                    QMteItem.project_id == self.project.id,
                                    *self.flt.at(QMteItem.site_id, QMteItem.owner_engagement_id),
                                )
                            )
                        ]
                        if self.flt.narrowed
                        else []
                    ),
                )
            )
            or 0
        )
        v = pct(ok, n)
        return Result(
            K.K154,
            v,
            D(ok),
            D(n),
            disp(v, "%"),
            [
                chip("overdue", "Overdue", "متأخرة", int(n) - int(ok)),
                chip("open_oot", "Open OOT reviews", "مراجعات خارج التفاوت المفتوحة", oot),
            ],
        )

    def k155(self) -> Result:
        from app.services.quality.q2 import competence  # noqa: PLC0415

        cells = self.memo("cpt", lambda: competence.cells(self.db, self.project, self.until))
        app_ = [c for c in cells if c["state"].value != "not_applicable"]
        met = sum(1 for c in app_ if c["state"].value in ("met", "expiring"))
        v = pct(met, len(app_))
        return Result(
            K.K155,
            v,
            D(met),
            D(len(app_)),
            disp(v, "%"),
            [
                chip(
                    "expiring",
                    "Expiring",
                    "قاربت على الانتهاء",
                    sum(1 for c in app_ if c["state"].value == "expiring"),
                )
            ],
        )

    def k156(self) -> Result:
        c = self.punch()
        v = pct(c.closed_on_time, c.with_target)
        return Result(
            K.K156,
            v,
            D(c.closed_on_time),
            D(c.with_target),
            disp(v, "%"),
            [
                chip("open_a", "Open A", "مفتوحة A", c.open_a),
                chip("open_b", "Open B", "مفتوحة B", c.open_b),
            ],
        )

    def k157(self) -> Result:
        from app.services.quality.q4 import suppliers  # noqa: PLC0415

        r = suppliers.k157(self.db, self.project.id, self.start, self.end)
        return Result(
            K.K157,
            r["mean"],
            None,
            D(r["suppliers"]),
            str(r["mean"] or "—"),
            [chip(f"band_{k}", f"Band {k}", f"الفئة {k}", v) for k, v in r["by_band"].items()],
        )

    def k158(self) -> Result:
        from app.services.quality.q4 import audits  # noqa: PLC0415

        r = audits.k158(self.db, self.project.id, self.start, self.end, self.as_of)
        nc = audits.audit_counts(self.db, self.project.id, self.start, self.end)
        v = pct(r["on_time"], r["lines"])
        return Result(
            K.K158,
            v,
            D(r["on_time"]),
            D(r["lines"]),
            disp(v, "%"),
            [
                chip("major_nc", "Major NC", "عدم مطابقة كبرى", nc["major_nc"]),
                chip("minor_nc", "Minor NC", "عدم مطابقة صغرى", nc["minor_nc"]),
            ],
        )

    def k159(self) -> Result:
        from app.services.quality.q4 import documents  # noqa: PLC0415

        r = documents.k159(self.db, self.project.id, self.until)
        v = pct(r["in_date"], r["current"])
        return Result(
            K.K159,
            v,
            D(r["in_date"]),
            D(r["current"]),
            disp(v, "%"),
            [
                chip(
                    "ack_pct",
                    "Read-ack completion",
                    "اكتمال الإقرار",
                    pct(r["acks_done"], r["acks_required"]),
                )
            ],
        )

    # logistics (sums of Q3 months) ---------------------------------------------------------

    def _sum(self, key: str, *fields: str) -> list[int | Decimal]:
        lg = self.logistics()
        return [sum((m[key][f] or 0) for m in lg) for f in fields]

    def k160(self) -> Result:
        lg = self.logistics()
        n, rej = self._sum("k160", "receipts", "rejected")
        v = pct(rej, n)
        last = lg[-1]["k160"] if lg else {}
        return Result(
            K.K160,
            v,
            D(rej),
            D(n),
            disp(v, "%"),
            [
                chip("deviation", "Deviation rate", "نسبة الانحراف", last.get("deviation_rate")),
                chip("quarantine", "Quarantine rate", "نسبة العزل", last.get("quarantine_rate")),
                chip(
                    "line_rejection",
                    "Line rejection %",
                    "نسبة رفض البنود",
                    last.get("line_rejection_pct"),
                ),
                chip(
                    "dwell",
                    "Dock dwell over limit",
                    "تجاوز مدة الرصيف",
                    sum(m["k160"]["dock_dwell_over_limit"] for m in lg),
                ),
            ],
        )

    def k161(self) -> Result:
        lg = self.logistics()
        x, zm = self._sum("k161", "excursions", "zone_months")
        v = q(D(x) / D(zm), "0.01") if zm else None
        sev = {
            s: sum(m["k161"]["by_severity"][s] for m in lg) for s in ("minor", "major", "critical")
        }
        return Result(
            K.K161,
            v,
            D(x),
            D(zm),
            str(v) if v is not None else "—",
            [
                chip("minor", "Minor", "بسيط", sev["minor"]),
                chip("major", "Major", "جوهري", sev["major"]),
                chip("critical", "Critical", "حرج", sev["critical"]),
                chip(
                    "transit",
                    "Transit excursions",
                    "انحرافات النقل",
                    sum(m["k161"]["transit_excursions"] for m in lg),
                ),
                chip(
                    "dismissed",
                    "Dismissed (not counted)",
                    "مستبعدة",
                    sum(m["k161"]["dismissed"] for m in lg),
                ),
            ],
            {"by_severity": sev},
        )

    def k162(self) -> Result:
        lg = self.logistics()
        mon, out, per = self._sum("k162", "monitored_minutes", "out_minutes", "period_minutes")
        v = pct(out, mon, "0.01")
        return Result(
            K.K162,
            v,
            D(out),
            D(mon),
            disp(v, "%"),
            [
                chip("coverage", "Coverage %", "نسبة التغطية", pct(mon, per)),
                chip(
                    "not_mapped",
                    "Zones not mapped",
                    "مناطق غير مدروسة",
                    lg[-1]["k162"]["zones_not_mapped"] if lg else None,
                ),
                chip(
                    "gaps", "Monitoring gaps", "فجوات المراقبة", sum(m["k162"]["gaps"] for m in lg)
                ),
            ],
            {"zones": lg[-1]["k162"]["zones"] if len(lg) == 1 else []},
        )

    def k163(self) -> Result:
        n, ok = self._sum("k163", "shipments", "otif")
        v = pct(ok, n)
        return Result(K.K163, v, D(ok), D(n), disp(v, "%"))

    def k164(self) -> Result:
        dmg, hd = self._sum("k164", "units_damaged", "units_handled")
        v = pct(D(dmg), D(hd), "0.001")
        ppm = q(D(dmg) * 1_000_000 / D(hd), "0.1") if hd else None
        return Result(
            K.K164, v, D(dmg), D(hd), disp(v, "%"), [chip("ppm", "ppm", "جزء في المليون", ppm)]
        )

    def k165(self) -> Result:
        n, w = self._sum("k165", "lines", "within")
        v = pct(w, n)
        return Result(K.K165, v, D(w), D(n), disp(v, "%"))

    def k166(self) -> Result:
        n, ok, ex = self._sum("k166", "checks", "counted_compliant", "exceptions")
        v = pct(ok, n)
        return Result(
            K.K166,
            v,
            D(ok),
            D(n),
            disp(v, "%"),
            [chip("exceptions", "Listed exceptions", "استثناءات", ex)],
        )

    def k167(self) -> Result:
        n, ok, nd, pf, ov = self._sum(
            "k167", "with_data", "compliant", "without_data", "preload_fails", "overrides"
        )
        v = pct(ok, n)
        return Result(
            K.K167,
            v,
            D(ok),
            D(n),
            disp(v, "%"),
            [
                chip("without_data", "Trips without data", "رحلات بلا بيانات", nd),
                chip("preload_fails", "Pre-load fails", "إخفاقات ما قبل التحميل", pf),
                chip("overrides", "Overrides", "تجاوزات", ov),
            ],
        )

    def k168(self) -> Result:
        done, due = self._sum("k168", "done", "due")
        v = pct(done, due)
        return Result(K.K168, v, D(done), D(due), disp(v, "%"))

    def k169(self) -> Result:
        from app.services.quality.q4 import base as b  # noqa: PLC0415

        a, e = b.day_start(self.start), b.day_start(self.end + timedelta(days=1))
        n, just = self.db.execute(
            select(func.count(), func.count().filter(QComplaint.justified == "justified")).where(
                QComplaint.project_id == self.project.id,
                QComplaint.received_at >= a,
                QComplaint.received_at < e,
                *self.flt.at(QComplaint.site_id),
            )
        ).one()
        rate = None
        if self.profile == QSectorProfile.logistics:
            sh = sum(m["k163"]["shipments"] for m in self.logistics())
            rate = q(D(n) * 1000 / D(sh), "0.01") if sh else None
        return Result(
            K.K169,
            D(n),
            D(n),
            None,
            str(n),
            [
                chip("per_1000", "Per 1,000 shipments", "لكل 1000 شحنة", rate),
                chip("justified", "Justified %", "نسبة المبررة", pct(just, n)),
            ],
            {"rate_per_1000": str(rate) if rate else None},
        )

    def result(self, k: QKpi) -> Result:
        return self.memo(f"r:{k.value}", getattr(self, "k" + k.value[2:]))  # type: ignore[no-any-return]


# ---- targets, tiles, snapshot, warnings ---------------------------------------------------------


def target_of(db: Session, project_id: uuid.UUID, kpi: QKpi, day: date) -> Decimal | None:
    return db.scalar(
        select(QKpiTarget.target)
        .where(
            QKpiTarget.project_id == project_id,
            QKpiTarget.kpi_id == kpi.value,
            QKpiTarget.valid_from <= day,
        )
        .order_by(QKpiTarget.valid_from.desc())
        .limit(1)
    )


def rag(kpi: QKpi, value: Decimal | None, target: Decimal | None) -> str | None:
    """Green meets the target; amber misses by at most 10 % of the target; red otherwise (D-365)."""
    if value is None or target is None:
        return None
    better = CATALOGUE[kpi][4]
    if better == "higher":
        if value >= target:
            return "green"
        return "amber" if value >= target * D("0.9") else "red"
    if better == "lower":
        if value <= target:
            return "green"
        return "amber" if value <= target * D("1.1") else "red"
    return None


def rag_for(r: Result, target: Decimal | None) -> str | None:
    """RAG of a result; K-148's objective is COPQ % of the work value (A.7 "K-148 ≤ 0.5 %")."""
    if r.kpi == K.K148:
        v = next((c["value"] for c in r.chips if c["code"] == "copq_pct"), None)
        return rag(r.kpi, D(v) if v else None, target)
    return rag(r.kpi, r.value, target)


def tiles_for(profile: QSectorProfile | None) -> list[QKpi]:
    """§E.7: tiles of the current profile and the shared ones (AC-Q4-33)."""
    own = TILES.get(profile.value, []) if profile else TILES["construction"]
    return [*own, *TILES["both"]]


def snapshot(db: Session, project: Project, start: date, end: date) -> dict[str, Any]:
    """Q-MRV-02: every K-141…K-169 of the period with its target, frozen into the minutes."""
    e = Engine(db, project, start, end, end)
    rows = []
    for k in QKpi:
        if not _applies(e, k):
            continue
        r = e.result(k).dump()
        t = target_of(db, project.id, k, end)
        r["target"] = str(t) if t is not None else None
        r["rag"] = rag_for(e.result(k), t)
        rows.append(r)
    import json  # noqa: PLC0415

    out = {"period_start": start.isoformat(), "period_end": end.isoformat(), "kpis": rows}
    return json.loads(json.dumps(out, default=str))  # type: ignore[no-any-return]


def _applies(e: Engine, k: QKpi) -> bool:
    if e.hidden(k):
        return False
    prof = CATALOGUE[k][2]
    if prof == "both":
        return True
    if e.profile is None:
        return True
    return prof == e.profile.value


def month_end(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1)


def warnings(db: Session, project: Project, month: date) -> list[dict[str, Any]]:
    """E26–E28 for the month of `month` (§E.7), with numerators and denominators, never names."""
    from app.services.quality.q4 import base as b  # noqa: PLC0415

    start, end = month.replace(day=1), month_end(month)
    e = Engine(db, project, start, end, end)
    out: list[dict[str, Any]] = []

    def w(code: QWarning, en: str, ar: str, inputs: list[dict[str, Any]]) -> None:
        out.append(
            {
                "code": code.value,
                "month": start.isoformat()[:7],
                "message_en": en,
                "message_ar": ar,
                "inputs": inputs,
            }
        )

    # E26 NCR backlog
    k146 = e.result(K.K146)
    lim = D(str(b.setting(db, project.id, "ncr_ontime_warning_pct")))
    old = (
        db.scalar(
            select(func.count())
            .select_from(QNcr)
            .where(
                *e._open_at(end),
                QNcr.classification.in_([QNcrClass.major, QNcrClass.critical]),
                QNcr.opened_date < end - timedelta(days=90),
            )
        )
        or 0
    )
    from app.models.quality import QLink  # noqa: PLC0415

    held = select(QLink.id).where(
        or_(
            and_(QLink.from_id == QNcr.id, QLink.to_type == "hold"),
            and_(QLink.to_id == QNcr.id, QLink.from_type == "hold"),
        )
    )
    cont = (
        db.scalar(
            select(func.count())
            .select_from(QNcr)
            .where(
                *e._open_at(end),
                QNcr.containment_due_at.is_not(None),
                ~held.exists(),
                QNcr.classification.in_([QNcrClass.major, QNcrClass.critical]),
                QNcr.containment_due_at < b.day_start(end + timedelta(days=1)),
                or_(
                    QNcr.containment_done_at.is_(None),
                    QNcr.containment_done_at >= b.day_start(end + timedelta(days=1)),
                ),
            )
        )
        or 0
    )
    if (k146.value is not None and k146.value < lim) or old or cont:
        w(
            QWarning.E26,
            "NCR backlog",
            "تراكم تقارير عدم المطابقة",
            [
                {
                    "name": "K-146",
                    "value": k146.display,
                    "numerator": str(k146.numerator),
                    "denominator": str(k146.denominator),
                    "limit": str(lim),
                },
                {"name": "major/critical > 90 days", "value": str(old)},
                {"name": "containment overdue", "value": str(cont)},
            ],
        )
    if e.profile == QSectorProfile.construction:
        k141, k152, k153 = e.result(K.K141), e.result(K.K152), e.result(K.K153)
        f1 = D(str(b.setting(db, project.id, "ftpr_warning_pct")))
        f2 = D(str(b.setting(db, project.id, "test_fail_warning_pct")))
        f3 = D(str(b.setting(db, project.id, "repair_rate_alert_pct") or "5.0"))
        if (
            (k141.value is not None and k141.value < f1)
            or (k152.value is not None and k152.value > f2)
            or (k153.value is not None and k153.value > f3)
        ):
            w(
                QWarning.E27,
                "First-time quality",
                "جودة العمل من أول مرة",
                [
                    {
                        "name": r.kpi.value,
                        "value": r.display,
                        "numerator": str(r.numerator),
                        "denominator": str(r.denominator),
                        "limit": str(lm),
                    }
                    for r, lm in ((k141, f1), (k152, f2), (k153, f3))
                ],
            )
    if e.profile == QSectorProfile.logistics:
        lg = e.logistics()
        crit = sum(m["k161"]["by_severity"]["critical"] for m in lg)
        k162, k167 = e.result(K.K162), e.result(K.K167)
        t1 = D(str(b.setting(db, project.id, "tor_warning_pct")))
        t2 = D(str(b.setting(db, project.id, "transport_compliance_warning_pct")))
        nm = lg[-1]["k162"]["zones_not_mapped"] if lg else 0
        od = _loggers_overdue(db, project.id, end)
        if (
            crit
            or (k162.value is not None and k162.value > t1)
            or nm
            or od
            or (k167.value is not None and k167.value < t2)
        ):
            w(
                QWarning.E28,
                "Cold chain",
                "سلسلة التبريد",
                [
                    {"name": "critical excursions", "value": str(crit)},
                    {
                        "name": "K-162",
                        "value": k162.display,
                        "numerator": str(k162.numerator),
                        "denominator": str(k162.denominator),
                        "limit": str(t1),
                    },
                    {"name": "zones not mapped", "value": str(nm)},
                    {"name": "monitoring loggers overdue", "value": str(od)},
                    {
                        "name": "K-167",
                        "value": k167.display,
                        "numerator": str(k167.numerator),
                        "denominator": str(k167.denominator),
                        "limit": str(t2),
                    },
                ],
            )
    return out


def _loggers_overdue(db: Session, project_id: uuid.UUID, day: date) -> int:
    """Loggers assigned to an active monitoring point whose calibration was due before the day."""
    from app.models.quality.q3 import QMonitoringPoint  # noqa: PLC0415

    ids: set[str] = set()
    for loggers in db.scalars(
        select(QMonitoringPoint.loggers).where(
            QMonitoringPoint.project_id == project_id, QMonitoringPoint.active.is_(True)
        )
    ):
        for x in loggers or []:
            if not x.get("to") and x.get("mte_id"):
                ids.add(str(x["mte_id"]))
    if not ids:
        return 0
    return (
        db.scalar(
            select(func.count())
            .select_from(QMteItem)
            .where(
                QMteItem.id.in_([uuid.UUID(i) for i in ids]),
                or_(QMteItem.cal_due_on.is_(None), QMteItem.cal_due_on < day),
            )
        )
        or 0
    )
