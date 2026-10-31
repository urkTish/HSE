"""Demo seed of package Q3 logistics (spec 8-quality Appendix A.5 / A.6, RUH-CCH).

* **Set-up** (`seed_setup`): the Q3 quality checklists (QRCV, QRPL, QHYG, QPST, QRET), the seven
  storage zones of S-DC1 with their classes, 22 monitoring points with loggers MTE-0101…0122, the
  products, mapping states, pest stations and check schedules. The Q3 tests start from it.
* **Records** (`seed`): September 2026 readings (15-min logger data written in bulk by the
  database), the excursions of QX12 / QX13 and the Z-DOCK minors, transients and gaps of QX18,
  receipts (K-160, QX14), stock snapshots, FEFO checks, cycle counts, damage, throughput, the mock
  recall QX16, shipments and trips with PODs (QX17, K-167), hygiene checks and pest visits, linked
  to the Q0 NCRs 0031, 0034 and 0036 through their sources. Every row is `seed_fake`.

`app.seed_quality.seed_quality_data` calls `seed(db)` after the Q0 records (registry §3.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.core.field_enums import ResponseOwnerType, ResponseResult
from app.core.quality.common import (
    QCalStatus,
    QLinkKind,
    QMteCheckKind,
    QMteType,
    QRecordType,
)
from app.core.quality.q3 import (
    QCheckFrequency,
    QCheckType,
    QDamageCause,
    QDamageStage,
    QExcursionCause,
    QExcursionStatus,
    QFefoException,
    QFefoResult,
    QHoldLineStatus,
    QHoldReason,
    QImpactDecision,
    QImportKind,
    QImportStatus,
    QImportTarget,
    QLineCondition,
    QLineDecision,
    QLoadState,
    QMappingPurpose,
    QMappingState,
    QMappingStatus,
    QPestStationType,
    QPointPosition,
    QRecallStatus,
    QRecallType,
    QReceiptStatus,
    QSeason,
    QStorageClass,
    QTripStatus,
    QZoneRole,
)
from app.models import Project, Site, User, Zone
from app.models.field import ChecklistResponse
from app.models.quality import QCustomer, QMteItem, QNcr, QSupplier
from app.models.quality.q3 import (
    QCheckSchedule,
    QCycleCount,
    QCycleCountLine,
    QDamageReport,
    QExcursion,
    QExcursionImpact,
    QFefoCheck,
    QImportBatch,
    QMappingStudy,
    QMonitoringPoint,
    QPestStation,
    QPestVisit,
    QPod,
    QProduct,
    QRecall,
    QReceipt,
    QReceiptLine,
    QShipment,
    QShipmentLine,
    QStockLine,
    QStockSnapshot,
    QStorageZone,
    QThroughput,
    QTrip,
)

RIYADH = ZoneInfo("Asia/Riyadh")
D = Decimal
SC = QStorageClass

# code, class, role, setpoint, points
ZONES: list[tuple[str, QStorageClass, QZoneRole, Decimal | None, int]] = [
    ("Z-DOCK", SC.dock_controlled, QZoneRole.dock, D("12"), 3),
    ("Z-FRZ1", SC.frozen, QZoneRole.storage, D("-22"), 4),
    ("Z-CHL1", SC.chilled, QZoneRole.storage, D("2"), 4),
    ("Z-PHR1", SC.pharma_2_8, QZoneRole.storage, D("5"), 3),
    ("Z-AMB1", SC.ambient_controlled, QZoneRole.storage, D("20"), 3),
    ("Z-DRY1", SC.dry, QZoneRole.storage, None, 3),
    ("Z-QRT", SC.chilled, QZoneRole.quarantine, D("2"), 2),
]
# base value and amplitude of the generated profile per zone (well inside the range)
PROFILE = {
    "Z-DOCK": (11.5, 1.0),
    "Z-FRZ1": (-22.0, 1.0),
    "Z-CHL1": (2.4, 0.5),
    "Z-PHR1": (5.0, 0.8),
    "Z-AMB1": (20.5, 1.5),
    "Z-DRY1": (24.0, 2.0),
    "Z-QRT": (2.5, 0.5),
}
MAPPED_UNTIL = {
    "Z-FRZ1": date(2028, 7, 27),
    "Z-PHR1": date(2026, 10, 20),
    "Z-CHL1": date(2027, 12, 31),
    "Z-DOCK": date(2027, 6, 30),
    "Z-AMB1": date(2027, 6, 30),
    "Z-DRY1": date(2027, 6, 30),
    "Z-QRT": date(2027, 6, 30),
}
# sku, owner, EN, AR, class, shelf life, min remaining %
PRODUCTS: list[tuple[str, str, str, str, QStorageClass, int, int | None]] = [
    ("NDC-1001", "NDC", "Fresh laban 1 L", "لبن طازج 1 لتر", SC.chilled, 14, None),
    ("NDC-Y", "NDC", "Yoghurt 170 g", "زبادي 170 غ", SC.chilled, 30, None),
    ("NDC-5001", "NDC", "UHT milk 1 L", "حليب طويل الأجل 1 لتر", SC.ambient_controlled, 180, None),
    (
        "GFF-2001",
        "GFF",
        "Frozen whole chicken 1,000 g",
        "دجاج كامل مجمد 1000 غ",
        SC.frozen,
        180,
        None,
    ),
    (
        "GFF-2105",
        "GFF",
        "Frozen mixed vegetables 2.5 kg",
        "خضار مشكلة مجمدة 2.5 كغ",
        SC.frozen,
        540,
        None,
    ),
    ("SAHM-3001", "SAHM", "Insulin pen box", "علبة أقلام إنسولين", SC.pharma_2_8, 730, 70),
    ("SAHM-3100", "SAHM", "Eye drops", "قطرة عين", SC.ambient_controlled, 730, None),
]
SEPT = date(2026, 9, 1)


def L(d: date, hh: int = 0, mm: int = 0) -> datetime:  # noqa: N802
    """Riyadh local wall time → UTC."""
    return datetime.combine(d, time(hh, mm), RIYADH).astimezone(UTC)


class _Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        assert p is not None  # noqa: S101
        self.p: Project = p
        site = db.scalar(select(Site).where(Site.project_id == p.id, Site.code == "S-DC1"))
        assert site is not None  # noqa: S101
        self.site: Site = site
        self.zones = {
            z.code: z for z in db.scalars(select(Zone).where(Zone.site_id == self.site.id))
        }
        self.users = {u.email.split("@")[0]: u.id for u in db.scalars(select(User))}
        self.cust = {
            c.code: c
            for c in db.scalars(select(QCustomer).where(QCustomer.project_id == self.p.id))
        }
        self.sup = {s.supplier_code: s for s in db.scalars(select(QSupplier))}
        self.mte = {
            m.mte_no: m
            for m in db.scalars(select(QMteItem).where(QMteItem.project_id == self.p.id))
        }
        self.prod = {
            x.sku: x for x in db.scalars(select(QProduct).where(QProduct.project_id == self.p.id))
        }

    def u(self, who: str) -> uuid.UUID:
        return self.users[who]


# ---- set-up -------------------------------------------------------------------------------------


def seed_setup(db: Session) -> None:
    """Zones, points, loggers, products, checklists, stations and schedules (no records)."""
    from app.services.quality.q3 import checklists  # noqa: PLC0415

    c = _Ctx(db)
    if db.scalar(select(QStorageZone.zone_id).where(QStorageZone.project_id == c.p.id).limit(1)):
        return
    faisal = c.u("faisal.harbi")
    checklists.ensure_templates(db, faisal)
    t0 = L(date(2025, 11, 1))
    from app.services.quality.q3.storage import defaults_for  # noqa: PLC0415

    _instruments(db, c, faisal)
    logger_no = 101
    for code, sc, role, sp, npts in ZONES:
        z = c.zones[code]
        sz = QStorageZone(
            zone_id=z.id,
            project_id=c.p.id,
            site_id=c.site.id,
            storage_class=sc,
            role=role,
            setpoint=sp,
            interval_minutes=15,
            mapping_state=QMappingState.mapped,
            mapped_until=MAPPED_UNTIL[code],
            change_notes=[],
            alerts_sent=[],
            created_at=t0,
            updated_at=t0,
            seed_fake=True,
            **defaults_for(sc),
        )
        if code == "Z-DOCK":
            sz.temp_min, sz.temp_max = D(8), D(15)
        db.add(sz)
        db.flush()
        for i in range(1, npts + 1):
            m = c.mte[f"MTE-{logger_no:04d}"]
            pos = (
                QPointPosition.hot_spot
                if i == 1
                else (QPointPosition.cold_spot if i == 2 else QPointPosition.general)
            )
            db.add(
                QMonitoringPoint(
                    project_id=c.p.id,
                    zone_id=z.id,
                    code=f"{code[2:]}-P{i}",
                    position=pos,
                    position_note=f"{pos.value.replace('_', ' ')} from mapping",
                    interval_minutes=15,
                    loggers=[
                        {"mte_id": str(m.id), "from": L(date(2026, 3, 1)).isoformat(), "to": None}
                    ],
                    active=True,
                    created_by_user_id=faisal,
                    seed_fake=True,
                )
            )
            logger_no += 1
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, c.p, QRecordType.mte, 2026, 127)
    for sku, owner, en, ar, sc, life, mrp in PRODUCTS:
        db.add(
            QProduct(
                project_id=c.p.id,
                owner_customer_id=c.cust[owner].id,
                sku=sku,
                description_en=en,
                description_ar=ar,
                gtin=None,
                storage_class=sc,
                shelf_life_days=life,
                min_remaining_shelf_life_pct=D(mrp) if mrp else None,
                dated=True,
                active=True,
                created_by_user_id=c.u("reem.mutairi"),
                seed_fake=True,
            )
        )
    shield = c.sup["SHIELD"].id
    stations = [
        ("Z-DRY1", 14),
        ("Z-AMB1", 8),
        ("Z-DOCK", 8),
        ("Z-FRZ1", 4),
        ("Z-CHL1", 4),
        ("Z-PHR1", 4),
        ("Z-QRT", 4),
    ]
    n = 0
    for zc, k in stations:
        for _ in range(k):
            n += 1
            db.add(
                QPestStation(
                    project_id=c.p.id,
                    site_id=c.site.id,
                    zone_id=c.zones[zc].id,
                    code=f"RB-{n:02d}",
                    station_type=QPestStationType.rodent_bait
                    if n % 3
                    else QPestStationType.insect_light_trap,
                    location_note=f"{zc} wall {n}",
                    provider_supplier_id=shield,
                    active=True,
                    created_by_user_id=c.u("reem.mutairi"),
                    seed_fake=True,
                )
            )
    schedules: list[tuple[str | None, QCheckType, str, QCheckFrequency, date]] = [
        ("Z-DOCK", QCheckType.hygiene, "QHYG", QCheckFrequency.daily, date(2026, 1, 1)),
        ("Z-FRZ1", QCheckType.hygiene, "QHYG", QCheckFrequency.daily, date(2026, 1, 1)),
        ("Z-PHR1", QCheckType.hygiene, "QHYG", QCheckFrequency.daily, date(2026, 1, 1)),
        ("Z-AMB1", QCheckType.hygiene, "QHYG", QCheckFrequency.daily, date(2026, 1, 1)),
        ("Z-CHL1", QCheckType.hygiene, "QHYG", QCheckFrequency.weekly, date(2026, 9, 27)),
        (None, QCheckType.pest_visit, "QPST", QCheckFrequency.monthly, date(2026, 10, 1)),
    ]
    for szc, ct, code, fr, start in schedules:
        db.add(
            QCheckSchedule(
                project_id=c.p.id,
                site_id=c.site.id,
                zone_id=c.zones[szc].id if szc else None,
                check_type=ct,
                template_code=code,
                frequency=fr,
                weekday=0 if fr == QCheckFrequency.weekly else None,
                start_date=start,
                assignee_role="warehouse_qc",
                active=True,
                created_by_user_id=c.u("reem.mutairi"),
                seed_fake=True,
            )
        )
    db.flush()


def _instruments(db: Session, c: _Ctx, author: uuid.UUID) -> None:
    """Loggers MTE-0101…0122 (points), MTE-0123…0127 (spare mapping loggers, A.5: the Z-FRZ1
    study used 27) and the probes MTE-0042 / MTE-0051 in the Q0 M&TE register, when the Q0 data
    layer has not created them; their calibration status stays `unknown` until Q2 is installed."""
    rows = [(n, QMteType.temp_logger, f"Temperature logger {n}") for n in range(101, 128)]
    rows += [
        (42, QMteType.temp_probe, "Receiving probe thermometer"),
        (51, QMteType.temp_probe, "Dispatch probe thermometer"),
    ]
    for no, typ, desc in rows:
        if f"MTE-{no:04d}" in c.mte:
            continue
        m = QMteItem(
            project_id=c.p.id,
            mte_no=f"MTE-{no:04d}",
            mte_type=typ,
            description=desc,
            manufacturer="Generic",
            model=typ.value,
            serial_no=f"RUH-CCH-SN-{no:05d}",
            site_id=c.site.id,
            check_kind=QMteCheckKind.calibration,
            interval_months=12,
            cal_status=QCalStatus.unknown,
            created_by_user_id=author,
            seed_fake=True,
        )
        db.add(m)
        c.mte[m.mte_no] = m
    db.flush()


# ---- records ------------------------------------------------------------------------------------


def seed(db: Session) -> None:
    """Appendix A.6 records on top of the set-up (idempotent)."""
    seed_setup(db)
    c = _Ctx(db)
    if db.scalar(select(QReceipt.id).where(QReceipt.project_id == c.p.id).limit(1)):
        return
    _readings(db, c)
    _excursions(db, c)
    _snapshots(db, c)
    _hold_0112(db, c)
    _receipts(db, c)
    _stock_checks(db, c)
    _shipments_trips(db, c)
    _recall(db, c)
    _hygiene(db, c)
    _mapping(db, c)
    _counters(db, c)
    db.flush()


def _points(db: Session, c: _Ctx) -> dict[str, QMonitoringPoint]:
    return {
        p.code: p
        for p in db.scalars(select(QMonitoringPoint).where(QMonitoringPoint.project_id == c.p.id))
    }


def _readings(db: Session, c: _Ctx) -> None:
    """22 points × 15-min logger readings 2026-09-01 00:00 … 2026-10-06 09:45 (Riyadh), written
    by `generate_series`, then the QX12 / QX13 / Z-DOCK runs, transients and gaps of QX18."""
    pts = _points(db, c)
    start, end = L(SEPT), L(date(2026, 10, 6), 9, 45)
    weeks = []
    w = SEPT
    while w <= date(2026, 10, 6):
        weeks.append(w)
        w += timedelta(days=7)
    reem = c.u("imran.siddiq")
    batch_of: dict[tuple[uuid.UUID, date], uuid.UUID] = {}
    rows = []
    for code, pt in pts.items():
        for wk in weeks:
            bid = uuid.uuid4()
            batch_of[(pt.id, wk)] = bid
            rows.append(
                {
                    "id": bid,
                    "project_id": c.p.id,
                    "kind": QImportKind.readings,
                    "profile": {
                        "columns": {"time": "time", "temperature": "temperature"},
                        "timezone": "Asia/Riyadh",
                        "unit": "C",
                    },
                    "file_name": f"{code}_{wk.isoformat()}.csv",
                    "sha256": uuid.uuid5(bid, "sha").hex + uuid.uuid5(bid, "sha2").hex,
                    "target_type": QImportTarget.point,
                    "target_id": pt.id,
                    "site_id": c.site.id,
                    "rows_read": 672,
                    "rows_accepted": 672,
                    "rows_rejected": 0,
                    "errors": [],
                    "first_at": L(wk),
                    "last_at": min(L(wk + timedelta(days=7)) - timedelta(minutes=15), end),
                    "status": QImportStatus.imported,
                    "imported_by_user_id": reem,
                    "imported_at": L(wk + timedelta(days=7), 8),
                    "seed_fake": True,
                }
            )
    db.execute(insert(QImportBatch), rows)
    for code, pt in pts.items():
        zc = "Z-" + code.split("-P")[0]
        base, amp = PROFILE[zc]
        phase = int(code[-1])
        db.execute(
            text(
                """
                INSERT INTO q_readings (project_id, target_type, target_id, channel, measured_at,
                    temperature_c, humidity_pct, source, batch_id, entered_by_user_id, probe_fault,
                    voided, created_at)
                SELECT :pid, 'point', :tid, '', t,
                    round((:base + :amp * sin(extract(epoch from t) / 43200.0 * pi() + :ph))
                        ::numeric, 2),
                    CASE WHEN :hum THEN round((45 + 5 * sin(extract(epoch from t) / 86400.0
                        * pi()))::numeric, 2) END,
                    'import', NULL, :uid, false, false, now()
                FROM generate_series(CAST(:a AS timestamptz), CAST(:b AS timestamptz),
                    interval '15 minutes') AS t
                """
            ),
            {
                "pid": c.p.id,
                "tid": pt.id,
                "base": base,
                "amp": amp,
                "ph": phase,
                "hum": zc in ("Z-AMB1", "Z-DRY1"),
                "uid": reem,
                "a": start,
                "b": end,
            },
        )
        for wk in weeks:
            db.execute(
                text(
                    "UPDATE q_readings SET batch_id = :bid WHERE target_id = :tid AND measured_at "
                    ">= :a AND measured_at < :b"
                ),
                {
                    "bid": batch_of[(pt.id, wk)],
                    "tid": pt.id,
                    "a": L(wk),
                    "b": L(wk + timedelta(days=7)),
                },
            )

    def setv(code: str, d: date, hh: int, mm: int, v: float) -> None:
        db.execute(
            text(
                "UPDATE q_readings SET temperature_c = :v WHERE target_id = :tid AND measured_at "
                "= :t"
            ),
            {"v": v, "tid": pts[code].id, "t": L(d, hh, mm)},
        )

    def manual(code: str, d: date, hh: int, mm: int, v: float, probe: str = "MTE-0042") -> None:
        db.execute(
            text(
                """INSERT INTO q_readings (project_id, target_type, target_id, channel, measured_at,
                temperature_c, source, mte_id, entered_by_user_id, probe_fault, voided, created_at)
                VALUES (:pid, 'point', :tid, '', :t, :v, 'manual', :m, :uid, false, false, now())"""
            ),
            {
                "pid": c.p.id,
                "tid": pts[code].id,
                "t": L(d, hh, mm),
                "v": v,
                "m": c.mte[probe].id,
                "uid": reem,
            },
        )

    def gap(zone: str, d: date, hh: int, mm: int, minutes: int) -> None:
        """All points of the zone miss their readings: [t+15, t+15+minutes) is unmonitored."""
        a = L(d, hh, mm) + timedelta(minutes=15)
        for code, pt in pts.items():
            if "Z-" + code.split("-P")[0] == zone:
                db.execute(
                    text(
                        "DELETE FROM q_readings WHERE target_id = :tid AND measured_at >= :a AND "
                        "measured_at < :b"
                    ),
                    {"tid": pt.id, "a": a, "b": a + timedelta(minutes=minutes)},
                )

    # QX12 Z-CHL1 2026-09-17 on CHL1-P2: run 08:15–09:15, 60 min, minor
    for (hh, mm), v in zip(
        ((8, 0), (8, 15), (8, 30), (8, 45), (9, 0), (9, 15)),
        (3.6, 4.4, 5.1, 5.6, 4.8, 3.9),
        strict=True,
    ):
        setv("CHL1-P2", date(2026, 9, 17), hh, mm, v)
    # Z-CHL1 transients: 7 × 10 min + 1 × 5 min = 75 (a manual in-range reading cuts each run)
    for i, cut in enumerate((10, 10, 10, 10, 10, 10, 10, 5)):
        d = date(2026, 9, 3 + i * 3)
        setv("CHL1-P3", d, 14, 0, 4.6)
        manual("CHL1-P3", d, 14, cut, 3.2)
    # QX13 Z-FRZ1 2026-09-22 02:00–05:30 on FRZ1-P1 (defrost failure), peak −13.8, major
    vals = [
        -17.6,
        -17.0,
        -16.4,
        -15.8,
        -15.1,
        -14.6,
        -14.2,
        -13.8,
        -14.0,
        -14.5,
        -15.2,
        -16.0,
        -16.9,
        -17.6,
    ]
    for k, v in enumerate(vals):
        t = L(date(2026, 9, 22), 2) + timedelta(minutes=15 * k)
        lt = t.astimezone(RIYADH)
        setv("FRZ1-P1", lt.date(), lt.hour, lt.minute, v)
    setv("FRZ1-P1", date(2026, 9, 22), 5, 30, -19.2)
    # Z-FRZ1 transients 6 × 15 min (alarm delay 30)
    for i in range(6):
        setv("FRZ1-P3", date(2026, 9, 2 + i * 4), 11, 0, -17.2)
    # Z-DOCK three minor excursions of 60 min (alarm delay 30, t1 60)
    for d in (date(2026, 9, 5), date(2026, 9, 11), date(2026, 9, 28)):
        for k, v in enumerate((15.8, 16.4, 16.9, 16.1)):
            setv("DOCK-P2", d, 12, 15 * k, v)
    # Z-AMB1 transients: 10 min + 15 min
    setv("AMB1-P1", date(2026, 9, 9), 15, 0, 25.6)
    manual("AMB1-P1", date(2026, 9, 9), 15, 10, 24.1, "MTE-0051")
    setv("AMB1-P2", date(2026, 9, 19), 16, 0, 25.4)
    # QX18 unmonitored minutes: Z-CHL1 90, Z-DRY1 120, Z-QRT 120, Z-PHR1 90 (420 in total)
    gap("Z-CHL1", date(2026, 9, 9), 10, 0, 90)
    gap("Z-DRY1", date(2026, 9, 14), 3, 0, 120)
    gap("Z-QRT", date(2026, 9, 20), 22, 0, 120)
    gap("Z-PHR1", date(2026, 9, 25), 13, 0, 90)
    # twice-daily manual readings on P1 of the chilled and medicines zones, in range
    for i in range(30):
        d = SEPT + timedelta(days=i)
        for hh in (7, 19):
            manual("CHL1-P1", d, hh, 37, 2.6)
            manual("PHR1-P1", d, hh, 37, 5.2, "MTE-0051")
    db.flush()


def _excursions(db: Session, c: _Ctx) -> None:
    """Run detection over the seeded data (no alerts, no automatic NCR / hold) and give the
    excursions their Appendix A numbers; QX13 is EXC-RUH-CCH-2026-0041 (NCR-0034's source)."""
    from app.services.quality.q3 import excursions  # noqa: PLC0415

    imran = c.u("imran.siddiq")
    for z in db.scalars(select(QStorageZone).where(QStorageZone.project_id == c.p.id)):
        _detect_quiet(db, c.p, z, imran)
    rows = list(
        db.scalars(
            select(QExcursion)
            .where(QExcursion.project_id == c.p.id, QExcursion.transient.is_(False))
            .order_by(QExcursion.started_at)
        )
    )
    for x in rows:
        x.exc_no = f"TMP-{x.id.hex[:12]}"
    db.flush()
    for i, x in enumerate(rows):
        x.exc_no = f"EXC-RUH-CCH-2026-{38 + i:04d}"
        x.cause = (
            QExcursionCause.defrost if x.severity.value == "major" else QExcursionCause.door_open
        )
        x.acknowledged_by_user_id = imran
        x.acknowledged_at = x.started_at + timedelta(minutes=20)
        if x.severity.value == "minor":
            x.status = QExcursionStatus.closed
            x.no_impact_note = (
                "Short door-open excursion within the product's tolerance; no product impact."
            )
            x.closed_at = x.started_at + timedelta(hours=6)
    _ = excursions


def _detect_quiet(db: Session, project: Project, z: QStorageZone, uid: uuid.UUID) -> None:
    from app.services.quality.q3 import engine as eng  # noqa: PLC0415
    from app.services.quality.q3 import excursions, storage  # noqa: PLC0415

    a, e = L(SEPT) - timedelta(minutes=1), L(date(2026, 10, 6), 10)
    gr = storage.zone_grid(db, z, a, e)
    found = eng.runs(gr, storage.bands(z), storage.limits(z))
    excursions._reconcile(
        db, project, z, None, None, gr, found, a, e, uid, manual=False, notify=False, auto=False
    )


def _snapshot_lines(c: _Ctx, d: date) -> list[dict[str, Any]]:
    """Stock at 23:00 on day d: 14 Z-FRZ1 lines (the QX13 hold), chilled, medicines, ambient."""
    out: list[dict[str, Any]] = []
    p = c.prod

    def add(sku: str, batch: str, exp: date, rec: date, loc: str, zone: str, qty: int) -> None:
        out.append(
            {
                "owner_customer_id": p[sku].owner_customer_id,
                "product_id": p[sku].id,
                "sku": sku,
                "batch": batch,
                "expiry_date": exp,
                "receipt_date": rec,
                "location": loc,
                "zone_code": zone,
                "zone_id": c.zones[zone].id,
                "qty": D(qty),
                "unit": "unit",
                "wms_status": "available",
            }
        )

    for i in range(7):
        add(
            "GFF-2001",
            f"GFF-C-26{i + 1:02d}",
            date(2026, 12, 20) + timedelta(days=10 * i),
            date(2026, 8, 1) + timedelta(days=4 * i),
            f"FRZ1-A{i + 1:02d}",
            "Z-FRZ1",
            240 + 20 * i,
        )
        add(
            "GFF-2105",
            f"GFF-V-26{i + 1:02d}",
            date(2027, 11, 1) + timedelta(days=15 * i),
            date(2026, 7, 20) + timedelta(days=5 * i),
            f"FRZ1-B{i + 1:02d}",
            "Z-FRZ1",
            180 + 10 * i,
        )
    add(
        "NDC-Y",
        "NDC-Y-2609",
        date(2026, 10, 2),
        date(2026, 9, 2),
        "CHL1-C01",
        "Z-CHL1",
        1150 if d >= date(2026, 9, 8) else 1600,
    )
    add("NDC-Y", "NDC-Y-2611", date(2026, 10, 30), date(2026, 9, 30), "CHL1-C02", "Z-CHL1", 600)
    add("NDC-1001", "NDC-L-2640", date(2026, 10, 9), date(2026, 9, 25), "CHL1-C03", "Z-CHL1", 300)
    add(
        "NDC-1001", "NDC-L-2633", date(2026, 10, 3), date(2026, 9, 19), "CHL1-C04", "Z-CHL1", 40
    )  # expired at the clock
    add("SAHM-3001", "SAHM-I-2602", date(2028, 2, 1), date(2026, 3, 1), "PHR1-D01", "Z-PHR1", 120)
    add("SAHM-3100", "SAHM-E-2601", date(2028, 1, 15), date(2026, 1, 20), "AMB1-E01", "Z-AMB1", 400)
    add("NDC-5001", "NDC-U-2608", date(2027, 2, 10), date(2026, 8, 14), "AMB1-E02", "Z-AMB1", 900)
    add(
        "NDC-5001", "NDC-U-2604", date(2026, 10, 25), date(2026, 4, 28), "AMB1-E03", "Z-AMB1", 160
    )  # near expiry
    return out


def _snapshots(db: Session, c: _Ctx) -> None:
    d = SEPT
    while d <= date(2026, 10, 5):
        sid = uuid.uuid4()
        ls = _snapshot_lines(c, d)
        db.add(
            QStockSnapshot(
                id=sid,
                project_id=c.p.id,
                site_id=c.site.id,
                as_of=L(d, 23),
                line_count=len(ls),
                created_at=L(d, 23, 5),
            )
        )
        db.flush()
        db.execute(insert(QStockLine), [{**x, "id": uuid.uuid4(), "snapshot_id": sid} for x in ls])
        d += timedelta(days=1)
    db.flush()


def _hold_0112(db: Session, c: _Ctx) -> None:
    """QX13 → NCR-0034 and HLD-RUH-CCH-2026-0112 with the 14 Z-FRZ1 lines of the 2026-09-21 23:00
    snapshot; impact assessed by Saad (WAREHOUSE_MGR) with the GFF decision on file: 12 lines
    proposed for release, 2 for destruction (the release waits for the NCR disposition)."""
    from app.services.quality import links, numbering, signoff  # noqa: PLC0415
    from app.services.quality.q3 import holds, stock  # noqa: PLC0415

    x = db.scalar(select(QExcursion).where(QExcursion.exc_no == "EXC-RUH-CCH-2026-0041"))
    n34 = db.scalar(select(QNcr).where(QNcr.ncr_no == "NCR-RUH-CCH-2026-0034"))
    if x is None:
        return
    numbering.bump_to(db, c.p, QRecordType.hold, 2026, 111)
    snap = stock.latest_before(db, c.site.id, x.started_at)
    lines = stock.stock_hold_lines(db, snap, "Z-FRZ1")
    h = holds.place(
        db,
        c.p,
        site_id=c.site.id,
        reason=QHoldReason.excursion,
        lines=lines,
        placed_by=c.u("imran.siddiq"),
        zone_id=c.zones["Z-FRZ1"].id,
        source=(QRecordType.excursion, x.id, x.exc_no),
        ncr_id=n34.id if n34 else None,
        note="Stock of the 2026-09-21 23:00 snapshot",
        at=x.started_at + timedelta(minutes=5),
        notify=False,
    )
    h.segregation = "tagged_in_place"  # type: ignore[assignment]
    h.segregation_at = x.started_at + timedelta(hours=2)
    h.wms_confirmed = True
    h.wms_confirmed_at = x.started_at + timedelta(hours=1)
    h.seed_fake = True
    x.hold_id = h.id
    x.status = QExcursionStatus.assessed
    x.assessed_at = L(date(2026, 9, 24), 11)
    if n34 is not None:
        x.ncr_id = n34.id
        n34.source_id = x.id
        links.add(
            db,
            c.p.id,
            QRecordType.ncr,
            n34.id,
            QRecordType.excursion,
            x.id,
            QLinkKind.raised_from,
            c.u("imran.siddiq"),
        )
    saad = c.u("saad.anazi")
    for i, ln in enumerate(holds.lines_of(db, h)):
        dec = QImpactDecision.destroy if i < 2 else QImpactDecision.release
        db.add(
            QExcursionImpact(
                excursion_id=x.id,
                hold_line_id=ln.id,
                decision=dec,
                justification="Peak −13.8 °C for 210 min: within the owner's frozen-poultry "
                "budget; cartons at the coil face destroyed."
                if dec == QImpactDecision.release
                else "Cartons next to the evaporator coil partly thawed.",
                owner_contact_name="GFF Quality Manager",
                owner_decision_date=date(2026, 9, 23),
                created_by_user_id=saad,
                created_at=L(date(2026, 9, 24), 10),
            )
        )
        ln.proposed_decision = dec
    db.flush()
    from app.core.quality.common import QSignoffChannel  # noqa: PLC0415
    from app.models.quality import QSignoff  # noqa: PLC0415

    db.add(
        QSignoff(
            project_id=c.p.id,
            record_type="excursion",
            record_id=x.id,
            step="impact",
            decision="approved",
            comment="Impact assessed with the GFF written decision.",
            signed_by_user_id=saad,
            signed_at=x.assessed_at,
            signer_capacity="position:WAREHOUSE_MGR (Warehouse Manager)",
            channel=QSignoffChannel.in_app,
            evidence_attachment_ids=[],
        )
    )
    _ = signoff


def _receipts(db: Session, c: _Ctx) -> None:
    """640 receipts decided in September: 12 with a rejected line, 25 with a deviation, 8 with a
    quarantine (K-160 1.9 %), incl. RCV-…-01877 (QX14) and RCV-…-01902 (NCR-0031)."""
    from app.services.quality import links, numbering  # noqa: PLC0415
    from app.services.quality.q3 import holds  # noqa: PLC0415

    imran, reem = c.u("imran.siddiq"), c.u("reem.mutairi")
    dock = c.zones["Z-DOCK"].id
    probe = c.mte["MTE-0042"].id
    owners = {"NDC": c.cust["NDC"].id, "GFF": c.cust["GFF"].id, "SAHM": c.cust["SAHM"].id}
    skus = ["NDC-1001", "NDC-Y", "NDC-5001", "GFF-2001", "GFF-2105", "SAHM-3001", "SAHM-3100"]
    temps = {SC.chilled: 3.1, SC.frozen: -20.4, SC.pharma_2_8: 5.0, SC.ambient_controlled: 21.0}
    rec_rows: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    seq = 1600
    special = {1877, 1902}
    quarantine_lines: list[tuple[uuid.UUID, uuid.UUID, dict[str, Any]]] = []
    for i in range(640):
        day = SEPT + timedelta(days=i * 30 // 640)
        slot = (i * 30) % 640 // 30
        arrived = L(day, 5 + slot % 15, (i * 7) % 60)
        seq += 1
        while seq in special:
            seq += 1
        no = seq
        sku = skus[i % len(skus)]
        batch = f"{sku}-B{i:04d}"
        qty = 120 + (i % 9) * 40
        decision = QLineDecision.accept
        if i < 4:  # the recall batch NDC-Y-2609 received 4 × 1,200 = 4,800 (QX16)
            sku, batch, qty, day = "NDC-Y", "NDC-Y-2609", 1200, SEPT + timedelta(days=i % 2)
            arrived = L(day, 6 + i, 10)
        elif 10 <= i < 21:
            decision = QLineDecision.reject
        elif 30 <= i < 54:
            decision = QLineDecision.accept_with_deviation
        elif 60 <= i < 68:
            decision = QLineDecision.quarantine
        if i == 100:
            no, sku, batch, qty = 1877, "GFF-2001", "GFF-C-2614", 480
            day, arrived = date(2026, 9, 14), L(date(2026, 9, 14), 6, 10)
            decision = QLineDecision.accept_with_deviation
        if i == 101:
            no, sku, batch, qty = 1902, "NDC-Y", "NDC-Y-2618", 960
            day, arrived = date(2026, 9, 21), L(date(2026, 9, 21), 7, 5)
            decision = QLineDecision.reject
        prod = c.prod[sku]
        rid, lid = uuid.uuid4(), uuid.uuid4()
        temp = temps.get(prod.storage_class)
        exp = day + timedelta(days=int((prod.shelf_life_days or 30) * 0.9))
        reasons: list[dict[str, Any]] = []
        if i == 100:
            temp, exp = -16.5, date(2026, 12, 20)
            reasons = [
                {
                    "code": "arrival_temperature",
                    "decision": "accept_with_deviation",
                    "en": "-16.5 °C in the deviation band.",
                    "ar": "-16.5 °م ضمن نطاق الانحراف.",
                },
                {
                    "code": "remaining_shelf_life",
                    "decision": "accept_with_deviation",
                    "en": "Remaining shelf life 53.9 % < 60 %.",
                    "ar": "الصلاحية المتبقية 53.9 % < 60 %.",
                },
            ]
        if i == 101:
            temp = 11.0
            reasons = [
                {
                    "code": "arrival_temperature",
                    "decision": "reject",
                    "en": "11.0 °C outside the limits.",
                    "ar": "11.0 °م خارج الحدود.",
                }
            ]
        start = arrived + timedelta(minutes=12)
        dwell = 23 + i % 12
        rec_rows.append(
            {
                "id": rid,
                "project_id": c.p.id,
                "rcv_no": f"RCV-RUH-CCH-2026-{no:05d}",
                "site_id": c.site.id,
                "dock_zone_id": dock,
                "customer_id": owners[sku.split("-")[0]],
                "supplier_id": c.sup["NDCF"].id if sku.startswith("NDC") else None,
                "carrier_id": c.sup["COOLRD"].id,
                "po_ref": f"PO-{77000 + i}",
                "asn_ref": f"ASN-{sku.split('-')[0]}-26-{i:04d}",
                "vehicle_plate": f"{4000 + i} RJA",
                "seal_intact": True,
                "seal_flag": False,
                "expected_at": arrived - timedelta(minutes=10),
                "arrived_at": arrived,
                "unload_start": start,
                "unload_end": start + timedelta(minutes=dwell),
                "dwell_minutes": dwell,
                "status": QReceiptStatus.decided,
                "inspected_at": start + timedelta(minutes=dwell + 5),
                "inspected_by_user_id": imran,
                "decided_at": start + timedelta(minutes=dwell + 10),
                "created_by_user_id": imran,
                "seed_fake": True,
            }
        )
        line = {
            "id": lid,
            "receipt_id": rid,
            "line_no": 1,
            "product_id": prod.id,
            "batch": batch,
            "expiry_date": exp,
            "qty_expected": D(qty),
            "qty_received": D(qty),
            "unit": "unit",
            "condition": QLineCondition.damaged
            if decision == QLineDecision.quarantine
            else QLineCondition.good,
            "labels_ok": decision != QLineDecision.accept_with_deviation or i >= 40,
            "product_temp_c": D(str(temp)) if temp is not None else None,
            "mte_id": probe if temp is not None else None,
            "remaining_shelf_life_pct": D("53.9") if i == 100 else D("90.0"),
            "photo_ids": [],
            "proposed_decision": decision,
            "proposal_reasons": reasons,
            "criteria_versions": {},
            "decision": decision,
            "reason": "Accepted with the owner's approval on file."
            if decision == QLineDecision.accept_with_deviation
            else None,
            "claim_ref": f"CLM-COOLRD-{i:04d}"
            if decision == QLineDecision.reject and i != 101
            else None,
            "recorded_by_user_id": imran,
            "decided_by_user_id": reem if decision != QLineDecision.accept else imran,
            "decided_at": start + timedelta(minutes=dwell + 10),
        }
        line_rows.append(line)
        if decision == QLineDecision.quarantine:
            quarantine_lines.append((rid, lid, line))
    db.execute(insert(QReceipt), rec_rows)
    db.execute(insert(QReceiptLine), line_rows)
    db.flush()
    numbering.bump_to(db, c.p, QRecordType.receipt, 2026, seq)
    numbering.bump_to(db, c.p, QRecordType.hold, 2026, 112)
    for rid, lid, line in quarantine_lines:
        r = db.get(QReceipt, rid)
        assert r is not None  # noqa: S101
        h = holds.place(
            db,
            c.p,
            site_id=c.site.id,
            reason=QHoldReason.receiving,
            lines=[
                {
                    "owner_customer_id": r.customer_id,
                    "product_id": line["product_id"],
                    "batch": line["batch"],
                    "qty": line["qty_received"],
                    "location": "QRT-01",
                    "receipt_line_id": lid,
                }
            ],
            placed_by=imran,
            zone_id=c.zones["Z-QRT"].id,
            source=(QRecordType.receipt, rid, r.rcv_no),
            at=r.decided_at,
            notify=False,
        )
        h.seed_fake = True
        for hl in holds.lines_of(db, h):
            hl.line_status = QHoldLineStatus.rejected
            hl.final_outcome = "returned_to_supplier"  # type: ignore[assignment]
            hl.reason = "Damaged on arrival; returned to the shipper with the carrier."
        holds.refresh(db, h)
        db.get(QReceiptLine, lid).hold_id = h.id  # type: ignore[union-attr]
    n31 = db.scalar(select(QNcr).where(QNcr.ncr_no == "NCR-RUH-CCH-2026-0031"))
    r1902 = db.scalar(select(QReceipt).where(QReceipt.rcv_no == "RCV-RUH-CCH-2026-01902"))
    if n31 is not None and r1902 is not None:
        n31.source_id = r1902.id
        db.scalar(select(QReceiptLine).where(QReceiptLine.receipt_id == r1902.id)).ncr_id = n31.id  # type: ignore[union-attr]
        links.add(
            db,
            c.p.id,
            QRecordType.ncr,
            n31.id,
            QRecordType.receipt,
            r1902.id,
            QLinkKind.raised_from,
            imran,
        )
    db.flush()


def _stock_checks(db: Session, c: _Ctx) -> None:
    """FEFO 200 (194 compliant incl. 2 listed exceptions), cycle counts 400 lines (388 within),
    damage 412 units (incl. DMG-…-00207, 30 yoghurt units of NDC-Y-2609 destroyed), throughput
    1,860,000 units handled."""
    imran = c.u("imran.siddiq")
    rows = []
    for i in range(200):
        d = SEPT + timedelta(days=i * 30 // 200)
        res = QFefoResult.compliant
        exc = None
        if i in (17, 93):
            res, exc = QFefoResult.exception, QFefoException.customer_allocation
        elif i in (5, 44, 78, 120, 151, 188):
            res = QFefoResult.non_compliant
        prod = c.prod["GFF-2001" if i % 2 else "NDC-5001"]
        rows.append(
            {
                "id": uuid.uuid4(),
                "project_id": c.p.id,
                "check_no": f"FEF-RUH-CCH-2026-{i + 1:05d}",
                "site_id": c.site.id,
                "checked_at": L(d, 9 + i % 8, 10),
                "order_ref": f"SO-{56000 + i}",
                "product_id": prod.id,
                "picked_batch": f"PICK-{i:04d}",
                "picked_expiry": date(2027, 1, 1) + timedelta(days=i),
                "eligible_earliest": date(2027, 1, 1)
                + timedelta(days=i - (5 if res != QFefoResult.compliant else 0)),
                "eligible_batch": f"ELIG-{i:04d}",
                "result": res,
                "exception_reason": exc,
                "created_by_user_id": imran,
                "seed_fake": True,
            }
        )
    db.execute(insert(QFefoCheck), rows)
    for k in range(8):
        cid = uuid.uuid4()
        db.add(
            QCycleCount(
                id=cid,
                project_id=c.p.id,
                cc_no=f"CC-RUH-CCH-2026-{k + 21:04d}",
                site_id=c.site.id,
                counted_at=L(date(2026, 9, 3 + k * 3), 20),
                zone_codes=["Z-AMB1", "Z-DRY1"],
                created_by_user_id=imran,
                seed_fake=True,
            )
        )
        db.flush()
        lines = []
        for j in range(50):
            off = 2 if (k * 50 + j) % 33 == 0 and (k * 50 + j) < 396 else 0
            lines.append(
                {
                    "id": uuid.uuid4(),
                    "cc_id": cid,
                    "sku": "NDC-5001",
                    "batch": f"NDC-U-{j:03d}",
                    "location": f"AMB1-{j:03d}",
                    "system_qty": D(100),
                    "counted_qty": D(100 + off),
                    "unit": "unit",
                    "tolerance": D(0),
                    "within_tolerance": off == 0,
                    "variance_reason": "picking error" if off else None,
                }
            )
        db.execute(insert(QCycleCountLine), lines)
    dmg = []
    qtys = [30] + [20] * 19 + [2]  # 30 + 380 + 2 = 412
    for i, q in enumerate(qtys):
        no = 207 if i == 0 else 190 + i if 190 + i != 207 else 230
        sku = "NDC-Y" if i == 0 else ("NDC-5001" if i % 2 else "GFF-2105")
        dmg.append(
            {
                "id": uuid.uuid4(),
                "project_id": c.p.id,
                "dmg_no": f"DMG-RUH-CCH-2026-{no:05d}",
                "site_id": c.site.id,
                "zone_id": c.zones["Z-CHL1" if i == 0 else "Z-AMB1"].id,
                "stage": QDamageStage.storage if i % 3 else QDamageStage.picking,
                "product_id": c.prod[sku].id,
                "batch": "NDC-Y-2609" if i == 0 else f"{sku}-D{i:02d}",
                "qty": D(q),
                "unit": "unit",
                "cause": QDamageCause.forklift if i % 2 else QDamageCause.stacking_crush,
                "destroyed_on_spot": True,
                "owner_notified_at": L(SEPT + timedelta(days=1 + i), 14),
                "reported_at": L(SEPT + timedelta(days=1 + i), 12),
                "created_by_user_id": imran,
                "seed_fake": True,
            }
        )
    db.execute(insert(QDamageReport), dmg)
    db.add(
        QThroughput(
            project_id=c.p.id,
            site_id=c.site.id,
            month=SEPT,
            units_received=940_000,
            units_dispatched=920_000,
            deliveries=1250,
            shipments=1250,
            entered_by_user_id=c.u("reem.mutairi"),
            updated_at=L(date(2026, 10, 1), 9),
            seed_fake=True,
        )
    )
    db.flush()


def _shipments_trips(db: Session, c: _Ctx) -> None:
    """1,250 shipments delivered in September (on time 1,190, in full 1,210, both 1,165 →
    K-163 93.2 %) on 380 trips with logger data; 4 transit excursions incl. TRP-…-00921 (major,
    NCR-0036); 6 pre-load fails, 1 override by Naveen."""
    from app.services.quality import links  # noqa: PLC0415
    from app.services.quality.q3 import engine as eng  # noqa: PLC0415
    from app.services.quality.q3 import excursions  # noqa: PLC0415

    imran, naveen = c.u("imran.siddiq"), c.u("naveen.kumar")
    consignees = [f"Hyper Market {k + 1:02d}" for k in range(14)] + [
        f"Grocery {k + 1:02d}" for k in range(16)
    ]
    trips: list[dict[str, Any]] = []
    for t in range(380):
        d = SEPT + timedelta(days=t * 30 // 380)
        dep = L(d, 4 + t % 14, 15)
        no = 600 + t
        if t == 321:
            no, d = 921, date(2026, 9, 26)
            dep = L(d, 5, 0)
        elif no == 921:
            no = 999
        frozen = t % 3 == 0
        trips.append(
            {
                "id": uuid.uuid4(),
                "project_id": c.p.id,
                "trip_no": f"TRP-RUH-CCH-2026-{no:05d}",
                "site_id": c.site.id,
                "carrier_id": c.sup["COOLRD"].id,
                "own_fleet": False,
                "plate_text": f"{7000 + t} KSA",
                "reefer_serial": f"TK-{t:05d}",
                "compartments": [
                    {
                        "code": "C1",
                        "setpoint": "-20" if frozen else "3",
                        "interval_minutes": 5,
                        "classes": ["frozen" if frozen else "chilled"],
                        "range_min": "-30" if frozen else "0",
                        "range_max": "-18" if frozen else "4",
                    }
                ],
                "driver_name": f"Driver {t % 25 + 1}",
                "logger_mte_ids": [],
                "seal_numbers": [f"S{900000 + t}"],
                "planned_departure": dep,
                "preload_passed": t not in (11, 57, 102, 160, 233, 301),
                "preload_failures": [] if t not in (11, 57, 102, 160, 233, 301) else ["QRPL-01"],
                "loading_temps": [],
                "override_reason": "Box 1.5 °C above range at loading; pre-cooled 20 min more and "
                "re-checked before the doors closed."
                if t == 57
                else None,
                "override_by_user_id": naveen if t == 57 else None,
                "departed_at": dep,
                "delivered_at": dep + timedelta(hours=3),
                "closed_at": dep + timedelta(hours=5),
                "transit_data": True,
                "status": QTripStatus.closed,
                "alerts_sent": [],
                "created_by_user_id": imran,
                "seed_fake": True,
            }
        )
    # the 5 pre-load fails without override were cancelled and re-planned on another vehicle;
    # they still count as pre-load fails of the delivered trips here (K-167 chip)
    db.execute(insert(QTrip), trips)
    ships = []
    lines = []
    pods = []
    for i in range(1250):
        tr = trips[i * 380 // 1250]
        promised = tr["departed_at"] + timedelta(hours=3)
        on_time = i < 1190
        not_full = (14 <= i < 39) or (1190 <= i < 1205)
        delivered = (
            promised - timedelta(minutes=20) if on_time else promised + timedelta(minutes=95)
        )
        sid = uuid.uuid4()
        frozen = tr["compartments"][0]["classes"] == ["frozen"]
        sku = "GFF-2001" if frozen else "NDC-1001"
        batch = f"{sku}-S{i:04d}"
        qty = D(100)
        cons = consignees[i % len(consignees)]
        if i < 14 + 0:  # the mock recall batch NDC-Y-2609: 3,620 units to 14 consignees (QX16)
            sku, batch, cons = "NDC-Y", "NDC-Y-2609", consignees[i]
            qty = D(260) if i < 13 else D(240)
        ships.append(
            {
                "id": sid,
                "project_id": c.p.id,
                "site_id": c.site.id,
                "shipment_ref": f"SHP-26-{50000 + i}",
                "owner_customer_id": c.prod[sku].owner_customer_id,
                "consignee_name": cons,
                "promised_at": promised,
                "dispatched_at": tr["departed_at"],
                "delivered_at": delivered,
                "trip_id": tr["id"],
                "compartment": "C1",
                "stopped": False,
                "notify_consignee": False,
                "created_at": tr["departed_at"] - timedelta(hours=10),
                "seed_fake": True,
            }
        )
        lines.append(
            {
                "id": uuid.uuid4(),
                "shipment_id": sid,
                "product_id": c.prod[sku].id,
                "sku": sku,
                "batch": batch,
                "storage_class": c.prod[sku].storage_class,
                "ordered_qty": qty,
                "delivered_qty": qty - 5 if not_full else qty,
                "unit": "unit",
            }
        )
        pods.append(
            {
                "id": uuid.uuid4(),
                "trip_id": tr["id"],
                "shipment_id": sid,
                "delivered_at": delivered,
                "receiver_name": f"Receiver {i % 40 + 1}",
                "receiver_role": "store keeper",
                "seal_intact": True,
                "exceptions": [{"kind": "shortage", "qty": "5", "note": "5 short"}]
                if not_full
                else [],
                "photo_ids": [],
                "recorded_by_user_id": naveen,
                "created_at": delivered,
            }
        )
    db.execute(insert(QShipment), ships)
    db.execute(insert(QShipmentLine), lines)
    db.execute(insert(QPod), pods)
    # transit readings: 5-min logger data for 2 h per trip (generated in the database)
    for tr in trips:
        base = -21.0 if tr["compartments"][0]["classes"] == ["frozen"] else 2.5
        db.execute(
            text(
                """INSERT INTO q_readings (project_id, target_type, target_id, channel, measured_at,
                temperature_c, source, probe_fault, voided, created_at)
                SELECT :pid, 'trip', :tid, 'C1', t, :v, 'import', false, false, now()
                FROM generate_series(CAST(:a AS timestamptz), CAST(:b AS timestamptz),
                    interval '5 minutes') AS t"""
            ),
            {
                "pid": c.p.id,
                "tid": tr["id"],
                "v": base,
                "a": tr["departed_at"],
                "b": tr["departed_at"] + timedelta(hours=2),
            },
        )
    # 4 transit excursions: TRP-00921 major (frozen at −14 °C for 100 min) and 3 minor
    bad = {321: (-14.0, 100), 40: (5.2, 20), 130: (5.0, 15), 250: (5.4, 25)}
    for t, (v, mins) in bad.items():
        tr = trips[t]
        if t == 321 and tr["compartments"][0]["classes"] != ["frozen"]:
            tr["compartments"] = [
                {
                    "code": "C1",
                    "setpoint": "-20",
                    "interval_minutes": 5,
                    "classes": ["frozen"],
                    "range_min": "-30",
                    "range_max": "-18",
                }
            ]
            db.execute(
                text("UPDATE q_trips SET compartments = CAST(:c AS jsonb) WHERE id = :id"),
                {"c": __import__("json").dumps(tr["compartments"]), "id": tr["id"]},
            )
            db.execute(
                text("UPDATE q_readings SET temperature_c = -21 WHERE target_id = :id"),
                {"id": tr["id"]},
            )
        val = -16.5 if tr["compartments"][0]["classes"] == ["frozen"] and t != 321 else v
        a = tr["departed_at"] + timedelta(minutes=30)
        db.execute(
            text(
                "UPDATE q_readings SET temperature_c = :v WHERE target_id = :id AND measured_at "
                ">= :a AND measured_at < :b"
            ),
            {"v": val, "id": tr["id"], "a": a, "b": a + timedelta(minutes=mins)},
        )
    db.flush()
    for t in bad:
        trow = db.get(QTrip, trips[t]["id"])
        assert trow is not None  # noqa: S101
        excursions.detect_trip(db, c.p, trow, imran, notify=False, auto=False)
    xs = list(
        db.scalars(
            select(QExcursion)
            .where(
                QExcursion.project_id == c.p.id,
                QExcursion.trip_id.is_not(None),
                QExcursion.transient.is_(False),
            )
            .order_by(QExcursion.started_at)
        )
    )
    for k, x in enumerate(xs):
        x.exc_no = f"EXC-RUH-CCH-2026-{43 + k:04d}"
        x.status = (
            QExcursionStatus.closed
            if x.severity.value == "minor"
            else QExcursionStatus.under_assessment
        )
        x.cause = QExcursionCause.loading_delay
        if x.severity.value == "minor":
            x.no_impact_note = (
                "Short rise during unloading at the consignee; product within tolerance."
            )
            x.closed_at = x.started_at + timedelta(hours=8)
    t921 = db.scalar(select(QTrip).where(QTrip.trip_no == "TRP-RUH-CCH-2026-00921"))
    n36 = db.scalar(select(QNcr).where(QNcr.ncr_no == "NCR-RUH-CCH-2026-0036"))
    if t921 is not None and n36 is not None:
        n36.source_id = t921.id
        for x in xs:
            if x.trip_id == t921.id:
                x.ncr_id = n36.id
        for s in db.scalars(select(QShipment).where(QShipment.trip_id == t921.id)):
            s.notify_consignee = True
        links.add(
            db,
            c.p.id,
            QRecordType.ncr,
            n36.id,
            QRecordType.trip,
            t921.id,
            QLinkKind.raised_from,
            imran,
        )
    _ = eng
    db.flush()


def _recall(db: Session, c: _Ctx) -> None:
    """QX16: mock recall RCL-RUH-CCH-2026-0002 of NDC-Y-2609, 2026-09-08 09:00, trace completed
    11:35, closed 100.0 %."""
    from app.services.quality import numbering  # noqa: PLC0415
    from app.services.quality.q3 import recalls  # noqa: PLC0415

    r = QRecall(
        id=uuid.uuid4(),
        project_id=c.p.id,
        rcl_no="RCL-RUH-CCH-2026-0002",
        site_id=c.site.id,
        recall_type=QRecallType.mock,
        items=[{"product_id": str(c.prod["NDC-Y"].id), "sku": "NDC-Y", "batch": "NDC-Y-2609"}],
        reason="Annual mock recall of a chilled dairy batch (Q-RCL-05).",
        initiated_at=L(date(2026, 9, 8), 9),
        trace_completed_at=L(date(2026, 9, 8), 11, 35),
        status=QRecallStatus.closed,
        closed_at=L(date(2026, 9, 9), 10),
        created_by_user_id=c.u("reem.mutairi"),
        seed_fake=True,
    )
    db.add(r)
    db.flush()
    t = recalls.trace(db, r)
    r.snapshot_id = t["snapshot_id"]
    r.trace = recalls._jsonable(t)
    r.effectiveness_pct = recalls.effectiveness(db, r, t)
    numbering.bump_to(db, c.p, QRecordType.recall, 2026, 2)


def _hygiene(db: Session, c: _Ctx) -> None:
    """114 of the 120 daily hygiene checks of September done; pest visits 2026-08-30 and
    2026-09-27 with activity at RB-14 (Z-DRY1) on both (Q-HYG-03 trend)."""
    from app.services.quality.q3 import checklists  # noqa: PLC0415

    t = checklists.template(db, "hygiene", "QHYG")
    imran = c.u("imran.siddiq")
    missed = {
        ("Z-DOCK", 4),
        ("Z-DOCK", 18),
        ("Z-FRZ1", 12),
        ("Z-PHR1", 22),
        ("Z-AMB1", 7),
        ("Z-AMB1", 26),
    }
    rows = []
    for zc in ("Z-DOCK", "Z-FRZ1", "Z-PHR1", "Z-AMB1"):
        for i in range(30):
            if (zc, i + 1) in missed:
                continue
            d = SEPT + timedelta(days=i)
            at = L(d, 7, 30)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "project_id": c.p.id,
                    "client_uuid": uuid.uuid4(),
                    "owner_type": ResponseOwnerType.q_hygiene,
                    "template_id": t.id,
                    "template_code": t.template_code,
                    "template_version": t.version,
                    "site_id": c.site.id,
                    "zone_id": c.zones[zc].id,
                    "airside": False,
                    "started_at": at,
                    "completed_at": at,
                    "completed_date": d,
                    "received_at": at,
                    "inspector_id": imran,
                    "answers": [
                        {
                            "item_code": it["item_code"],
                            "answer": "compliant",
                            "compliant": True,
                            "critical": it["critical"],
                            "applicable": True,
                        }
                        for it in t.items
                    ],
                    "applicable_count": len(t.items),
                    "compliant_count": len(t.items),
                    "applicable_weight": D(sum(int(it["weight"]) for it in t.items)),
                    "earned_weight": D(sum(int(it["weight"]) for it in t.items)),
                    "score_pct": D(100),
                    "critical_fail_count": 0,
                    "result": ResponseResult.pass_,
                    "submitted": True,
                    "self_inspection": False,
                    "voided": False,
                    "warnings": [],
                    "created_by_user_id": imran,
                    "seed_fake": True,
                }
            )
    db.execute(insert(ChecklistResponse), rows)
    stations = list(
        db.scalars(
            select(QPestStation)
            .where(QPestStation.site_id == c.site.id)
            .order_by(QPestStation.code)
        )
    )
    for n, d in enumerate((date(2026, 8, 30), date(2026, 9, 27)), start=1):
        res = [
            {
                "station_id": str(s.id),
                "activity": "low" if s.code == "RB-14" else "none",
                "pest_type": "rodent" if s.code == "RB-14" else None,
                "bait_consumed_pct": 30 if s.code == "RB-14" else 0,
                "action": "bait replaced" if s.code == "RB-14" else None,
            }
            for s in stations
        ]
        props = (
            [
                {
                    "station": "RB-14",
                    "station_id": str(next(s.id for s in stations if s.code == "RB-14")),
                    "why": ["activity on 2 consecutive visits"],
                    "kinds": ["quality_alert", "ncr"],
                    "source_type": "hygiene_pest",
                }
            ]
            if n == 2
            else []
        )
        v = QPestVisit(
            id=uuid.uuid4(),
            project_id=c.p.id,
            visit_no=f"PSV-RUH-CCH-2026-{n + 7:04d}",
            site_id=c.site.id,
            provider_supplier_id=c.sup["SHIELD"].id,
            visited_at=L(d, 10),
            technician_name="Shield technician",
            chemicals=[
                {
                    "product": "Brodifacoum block 0.005 %",
                    "registration_no": "[VERIFY]",
                    "quantity": "2 kg",
                }
            ],
            station_results=res,
            not_serviced=[],
            proposals=[],
            created_by_user_id=c.u("reem.mutairi"),
            seed_fake=True,
        )
        db.add(v)
        db.flush()
        v.proposals = [{**x, "source_id": str(v.id)} for x in props]
    for s in stations:
        if s.code == "RB-14":
            s.activity_trend = True
    db.flush()


def _mapping(db: Session, c: _Ctx) -> None:
    """MAP-RUH-CCH-2026-0004: Z-FRZ1 summer loaded study 2026-07-14…07-21, 27 loggers, 5-min,
    approved 2026-07-28 → valid to 2028-07-27 (results only; the raw study files are not seeded),
    and the planned periodic study of Z-PHR1 (mapped until 2026-10-20)."""
    from app.services.quality import numbering  # noqa: PLC0415

    loggers = [m for k, m in sorted(c.mte.items()) if 101 <= int(k[4:]) <= 127]
    mtes = loggers[:27]
    res = []
    for k, m in enumerate(mtes):
        res.append(
            {
                "position_code": f"L{k + 1:02d}",
                "mte_id": str(m.id),
                "readings": 2016,
                "readings_in_test_windows": 12 if k < 3 else 0,
                "min_c": str(-25.8 + (k % 5) * 0.2),
                "max_c": str(-19.4 - (k % 4) * 0.3),
                "mean_c": "-22.1",
                "pct_in_range": "100.0",
                "in_range": True,
            }
        )
    reem, faisal = c.u("reem.mutairi"), c.u("faisal.harbi")
    db.add(
        QMappingStudy(
            project_id=c.p.id,
            map_no="MAP-RUH-CCH-2026-0004",
            zone_id=c.zones["Z-FRZ1"].id,
            purpose=QMappingPurpose.periodic,
            season=QSeason.summer,
            load_state=QLoadState.loaded,
            planned_start=L(date(2026, 7, 14), 8),
            planned_end=L(date(2026, 7, 21), 8),
            actual_start=L(date(2026, 7, 14), 8),
            actual_end=L(date(2026, 7, 21), 8),
            interval_minutes=5,
            loggers=[
                {
                    "mte_id": str(m.id),
                    "position_code": f"L{k + 1:02d}",
                    "description": f"Grid {k // 9 + 1}-{k % 9 + 1}, height "
                    f"{('low', 'mid', 'high')[k % 3]}",
                }
                for k, m in enumerate(mtes)
            ],
            test_windows=[
                {
                    "kind": "door_open",
                    "from": L(date(2026, 7, 16), 10).isoformat(),
                    "to": L(date(2026, 7, 16), 11).isoformat(),
                }
            ],
            lead_user_id=reem,
            results={
                "loggers": res,
                "zone_min_c": "-25.8",
                "zone_max_c": "-19.4",
                "hot_spot": "L01",
                "cold_spot": "L05",
                "evaluated_at": L(date(2026, 7, 23), 9).isoformat(),
            },
            passed=True,
            recommended_positions=[
                {"position": "hot_spot", "position_code": "L01"},
                {"position": "cold_spot", "position_code": "L05"},
            ],
            status=QMappingStatus.approved,
            approved_at=L(date(2026, 7, 28), 11),
            approved_on=date(2026, 7, 28),
            valid_until=date(2028, 7, 27),
            created_by_user_id=reem,
            seed_fake=True,
        )
    )
    db.add(
        QMappingStudy(
            project_id=c.p.id,
            zone_id=c.zones["Z-PHR1"].id,
            purpose=QMappingPurpose.periodic,
            season=QSeason.winter,
            load_state=QLoadState.loaded,
            planned_start=L(date(2026, 10, 12), 8),
            planned_end=L(date(2026, 10, 15), 8),
            interval_minutes=5,
            loggers=[
                {
                    "mte_id": str(m.id),
                    "position_code": f"P{k + 1:02d}",
                    "description": f"Shelf {k + 1}",
                }
                for k, m in enumerate(mtes[:9])
            ],
            test_windows=[],
            lead_user_id=reem,
            recommended_positions=[],
            status=QMappingStatus.draft,
            created_by_user_id=reem,
            seed_fake=True,
        )
    )
    db.flush()
    numbering.bump_to(db, c.p, QRecordType.mapping_study, 2026, 4)
    _ = faisal


def _counters(db: Session, c: _Ctx) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, c.p, QRecordType.excursion, 2026, 46)
    numbering.bump_to(db, c.p, QRecordType.trip, 2026, 999)
    numbering.bump_to(db, c.p, QRecordType.fefo_check, 2026, 200)
    numbering.bump_to(db, c.p, QRecordType.cycle_count, 2026, 28)
    numbering.bump_to(db, c.p, QRecordType.damage_report, 2026, 230)
