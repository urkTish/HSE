"""CSV imports (spec 8-quality §D.1.4, Q-IMP-01…06): logger readings (row by row), stock
snapshots, shipments, products and cycle counts (all-or-nothing). The file is stored unchanged
with its SHA-256 (`q_import_file` attachment); the same file again for the same target → 409
`IMPORT_DUPLICATE_FILE`. °F is converted to °C and times to UTC from the profile's time zone. A
batch may be voided within 24 h; its rows leave every calculation and derived excursions are
recomputed. Nothing is written back to a WMS or TMS (Q-IMP-06)."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType
from app.core.quality.q3 import (
    QImportKind,
    QImportStatus,
    QImportTarget,
    QReadingSource,
    QReadingTarget,
    QStorageClass,
)
from app.models import Project, Site, Zone
from app.models.quality import QCustomer
from app.models.quality.q3 import (
    QCycleCount,
    QImportBatch,
    QMappingStudy,
    QMonitoringPoint,
    QProduct,
    QReading,
    QShipment,
    QShipmentLine,
    QStockLine,
    QStockSnapshot,
    QStorageZone,
    QTrip,
)
from app.services import attachments
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality.q3 import base as b

C = Capability
TWO = Decimal("0.01")
MAX_ERRORS = 1000

DEFAULT_COLUMNS: dict[QImportKind, dict[str, str]] = {
    QImportKind.readings: {
        "time": "time",
        "temperature": "temperature",
        "humidity": "humidity",
        "channel": "channel",
    },
    QImportKind.stock_snapshot: {
        "owner": "owner",
        "sku": "sku",
        "batch": "batch",
        "expiry": "expiry",
        "receipt_date": "receipt_date",
        "location": "location",
        "zone": "zone",
        "qty": "qty",
        "unit": "unit",
        "wms_status": "wms_status",
    },
    QImportKind.shipments: {
        "shipment_ref": "shipment_ref",
        "owner": "owner",
        "consignee": "consignee",
        "sku": "sku",
        "batch": "batch",
        "ordered_qty": "ordered_qty",
        "delivered_qty": "delivered_qty",
        "promised_at": "promised_at",
        "dispatched_at": "dispatched_at",
        "delivered_at": "delivered_at",
        "trip_no": "trip_no",
        "compartment": "compartment",
    },
    QImportKind.products: {
        "owner": "owner",
        "sku": "sku",
        "description_en": "description_en",
        "description_ar": "description_ar",
        "gtin": "gtin",
        "storage_class": "storage_class",
        "shelf_life_days": "shelf_life_days",
        "min_remaining_pct": "min_remaining_pct",
        "dated": "dated",
    },
    QImportKind.cycle_count: {
        "sku": "sku",
        "batch": "batch",
        "location": "location",
        "zone": "zone",
        "system_qty": "system_qty",
        "counted_qty": "counted_qty",
        "recount_qty": "recount_qty",
        "tolerance": "tolerance",
        "variance_reason": "variance_reason",
    },
}
FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


class RowError(Exception):
    pass


# ---- profile and parsing -------------------------------------------------------------------------


def _tz(name: str | None) -> Any:
    if not name or name == "Asia/Riyadh":
        return ZoneInfo("Asia/Riyadh")
    if name.upper() in ("UTC", "Z", "+00:00", "UTC+00", "UTC+00:00"):
        return UTC
    m = re.fullmatch(r"(?:UTC)?([+-])(\d{1,2}):?(\d{2})?", name.strip())
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise qc.field_err(
            "profile", f"Unknown time zone {name}.", "منطقة زمنية غير معروفة."
        ) from e


def normalise_profile(kind: QImportKind, raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(raw or {})
    given = raw.get("columns") or {}
    texts = ("unit", "decimal", "timezone", "date_format", "delimiter", "logger_serial_column")
    if (
        not isinstance(given, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in given.items())
        or any(raw.get(k) is not None and not isinstance(raw.get(k), str) for k in texts)
    ):
        raise qc.field_err(
            "profile",
            "The column mapping must map field names to column headings (text).",
            "يجب أن يربط تعيين الأعمدة أسماء الحقول بعناوين الأعمدة (نص).",
        )
    cols = {**DEFAULT_COLUMNS[kind], **given}
    unit = (raw.get("unit") or "C").upper().replace("°", "")
    if unit not in ("C", "F"):
        raise qc.field_err("profile", "Unit is C or F.", "الوحدة C أو F.")
    dec = raw.get("decimal") or "."
    if dec not in (".", ","):
        raise qc.field_err(
            "profile", "Decimal separator is '.' or ','.", "الفاصل العشري '.' أو ','."
        )
    tzname = raw.get("timezone") or "Asia/Riyadh"
    _tz(tzname)
    return {
        "columns": cols,
        "date_format": raw.get("date_format") or None,
        "timezone": tzname,
        "unit": unit,
        "decimal": dec,
        "delimiter": raw.get("delimiter") or ("," if dec == "." else ";"),
        "logger_serial_column": raw.get("logger_serial_column"),
    }


def parse_time(v: str, prof: dict[str, Any]) -> datetime:
    s = (v or "").strip()
    if not s:
        raise RowError("time is empty")
    dt: datetime | None = None
    if prof.get("date_format"):
        try:
            dt = datetime.strptime(s, prof["date_format"])
        except ValueError as e:
            raise RowError(f"time '{s}' does not match {prof['date_format']}") from e
    else:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            for f in FORMATS:
                try:
                    dt = datetime.strptime(s, f)
                    break
                except ValueError:
                    continue
    if dt is None:
        raise RowError(f"time '{s}' is not a date and time")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(prof["timezone"]))
    return dt.astimezone(UTC)


def parse_date(
    v: str | None, prof: dict[str, Any], what: str, required: bool = False
) -> date | None:
    s = (v or "").strip()
    if not s:
        if required:
            raise RowError(f"{what} is empty")
        return None
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise RowError(f"{what} '{s}' is not a date")


def parse_dec(
    v: str | None, prof: dict[str, Any], what: str, required: bool = False
) -> Decimal | None:
    s = (v or "").strip()
    if not s:
        if required:
            raise RowError(f"{what} is empty")
        return None
    if prof["decimal"] == ",":
        s = s.replace(".", "").replace(",", ".")
    s = s.replace("−", "-")  # Unicode minus from some logger software
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise RowError(f"{what} '{v}' is not a number") from e


def to_c(v: Decimal, prof: dict[str, Any]) -> Decimal:
    """Q-IMP-03: °C = (°F − 32) × 5 ÷ 9, kept to 2 dp."""
    if prof["unit"] == "F":
        v = (v - 32) * 5 / 9
    return v.quantize(TWO, ROUND_HALF_UP)


def read_rows(content: bytes, prof: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1256", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=prof["delimiter"])
    fields = [f.strip() for f in reader.fieldnames or []]
    rows = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "") for k, v in r.items()})
    return fields, rows


def col(prof: dict[str, Any], row: dict[str, str], key: str) -> str | None:
    name = prof["columns"].get(key)
    if not name:
        return None
    return row.get(name)


def gtin_ok(g: str) -> bool:
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", g):
        return False
    digits = [int(c) for c in g]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


# ---- entry point ---------------------------------------------------------------------------------


def _target(
    db: Session, project: Project, kind: QImportKind, ttype: QImportTarget, tid: uuid.UUID
) -> tuple[Any, uuid.UUID | None]:
    """The target row and its site."""
    if kind == QImportKind.readings:
        if ttype == QImportTarget.point:
            pt = db.get(QMonitoringPoint, tid)
            if pt is None or pt.project_id != project.id:
                raise qc.field_err(
                    "target_id",
                    "The monitoring point is not on this project.",
                    "نقطة المراقبة ليست في المشروع.",
                )
            z = db.get(QStorageZone, pt.zone_id)
            return pt, z.site_id if z else None
        if ttype == QImportTarget.trip:
            t = db.get(QTrip, tid)
            if t is None or t.project_id != project.id:
                raise qc.field_err(
                    "target_id", "The trip is not on this project.", "الرحلة ليست في المشروع."
                )
            return t, t.site_id
        if ttype == QImportTarget.mapping_study:
            m = db.get(QMappingStudy, tid)
            if m is None or m.project_id != project.id:
                raise qc.field_err(
                    "target_id", "The study is not on this project.", "الدراسة ليست في المشروع."
                )
            z = db.get(QStorageZone, m.zone_id)
            return m, z.site_id if z else None
        if ttype == QImportTarget.receipt:
            from app.models.quality.q3 import QReceipt  # noqa: PLC0415

            r = db.get(QReceipt, tid)
            if r is None or r.project_id != project.id:
                raise qc.field_err(
                    "target_id", "The receipt is not on this project.", "الاستلام ليس في المشروع."
                )
            return r, r.site_id
        raise qc.field_err(
            "target_type",
            "Readings go to a point, a trip, a study or a receipt.",
            "هدف القراءات غير صالح.",
        )
    if kind == QImportKind.products:
        if tid != project.id:
            raise qc.field_err(
                "target_id", "Products are imported for the project.", "تُستورد المنتجات للمشروع."
            )
        return project, None
    site = b.site_of(db, project, tid)
    return site, site.id


def import_file(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    kind: QImportKind,
    target_type: QImportTarget,
    target_id: uuid.UUID,
    file_name: str,
    content: bytes,
    profile: dict[str, Any] | None,
    *,
    as_of: datetime | None = None,
    user_id: uuid.UUID | None = None,
    seed: bool = False,
) -> dict[str, Any]:
    if p is not None:
        cap = C.reading_record if kind == QImportKind.readings else C.stock_record
        rt = QRecordType.excursion if kind == QImportKind.readings else QRecordType.cycle_count
        project, g = b.project_for_create(db, p, project_id, rt, cap)
        uid: uuid.UUID | None = p.user.id
    else:
        project = db.get(Project, project_id)  # type: ignore[assignment]
        assert project is not None  # noqa: S101
        g = None
        uid = user_id
    target, site_id = _target(db, project, kind, target_type, target_id)
    if g is not None and site_id is not None:
        b.require_site(g, site_id)
    prof = normalise_profile(kind, profile)
    sha = hashlib.sha256(content).hexdigest()
    dup = db.scalar(
        select(QImportBatch.id).where(
            QImportBatch.project_id == project.id,
            QImportBatch.sha256 == sha,
            QImportBatch.target_type == target_type,
            QImportBatch.target_id == target_id,
            QImportBatch.status == QImportStatus.imported,
        )
    )
    if dup is not None:
        raise qc.err(
            409,
            ErrorCode.IMPORT_DUPLICATE_FILE,
            "This file was already imported for this target (Q-IMP-01).",
            "سبق استيراد هذا الملف لهذا الهدف.",
            batch_id=str(dup),
        )
    fields, rows = read_rows(content, prof)
    limit = int(b.setting(db, project.id, "import_max_rows"))
    if len(rows) > limit:
        raise qc.err(
            422,
            ErrorCode.IMPORT_TOO_LARGE,
            f"The file has {len(rows)} rows; the limit is {limit} (Q-IMP-04).",
            f"الملف يحتوي {len(rows)} صفاً؛ الحد {limit}.",
        )
    batch = QImportBatch(
        id=uuid.uuid4(),
        project_id=project.id,
        kind=kind,
        profile=prof,
        file_name=file_name[:200],
        sha256=sha,
        target_type=target_type,
        target_id=target_id,
        site_id=site_id,
        rows_read=len(rows),
        errors=[],
        status=QImportStatus.imported,
        imported_by_user_id=uid,
        imported_at=now(),
        seed_fake=seed,
    )
    db.add(batch)
    db.flush()
    missing = [prof["columns"][k] for k in _required(kind) if prof["columns"].get(k) not in fields]
    if missing:
        raise qc.err(
            422,
            ErrorCode.IMPORT_ROWS_INVALID,
            f"Columns not found in the file: {', '.join(missing)}.",
            f"أعمدة غير موجودة في الملف: {', '.join(missing)}.",
            errors=[{"row": 0, "reason": f"missing column {m}"} for m in missing],
        )
    if kind == QImportKind.readings:
        extra = _readings(db, project, batch, target, rows, prof, uid)
    elif kind == QImportKind.stock_snapshot:
        extra = _snapshot(db, project, batch, rows, prof, as_of or now())
    elif kind == QImportKind.shipments:
        extra = _shipments(db, project, batch, rows, prof)
    elif kind == QImportKind.products:
        extra = _products(db, project, batch, rows, prof, uid)
    else:
        extra = _cycle_count(db, project, batch, rows, prof, as_of or now(), uid)
    if not seed:
        att = attachments.store(
            db,
            AttachmentOwner.q_import_file,
            batch.id,
            project.id,
            file_name or "import.csv",
            content,
            "text/csv",
            uid or uuid.UUID(int=0),
            shrink=False,
        )
        batch.attachment_id = att.id
    if p is not None:
        b.audit_create(
            db,
            p,
            project,
            QRecordType.excursion,
            batch.id,
            kind=kind.value,
            rows=batch.rows_accepted,
        )
    db.flush()
    return {**batch_read(db, batch), **extra}


def _required(kind: QImportKind) -> tuple[str, ...]:
    return {
        QImportKind.readings: ("time",),
        QImportKind.stock_snapshot: ("sku", "batch", "location", "qty"),
        QImportKind.shipments: ("shipment_ref", "sku", "ordered_qty"),
        QImportKind.products: ("owner", "sku", "description_en", "storage_class"),
        QImportKind.cycle_count: ("sku", "location", "system_qty", "counted_qty"),
    }[kind]


def _all_or_nothing(errors: list[dict[str, Any]]) -> None:
    if errors:
        raise qc.err(
            422,
            ErrorCode.IMPORT_ROWS_INVALID,
            f"{len(errors)} rows have errors; nothing was imported (Q-IMP-02).",
            f"{len(errors)} صفوف فيها أخطاء؛ لم يُستورد شيء.",
            errors=errors[:MAX_ERRORS],
        )


# ---- readings ----------------------------------------------------------------------------------


def _readings(
    db: Session,
    project: Project,
    batch: QImportBatch,
    target: Any,
    rows: list[dict[str, str]],
    prof: dict[str, Any],
    uid: uuid.UUID | None,
) -> dict[str, Any]:
    """Q-IMP-02: bad time, a value outside −80…+80 °C or 0…100 % RH, or a time already stored for
    the target are rejected row by row; valid rows are stored."""
    from app.services.quality.q3 import excursions  # noqa: PLC0415

    ttype = {
        QImportTarget.point: QReadingTarget.point,
        QImportTarget.trip: QReadingTarget.trip,
        QImportTarget.mapping_study: QReadingTarget.mapping_study,
        QImportTarget.receipt: QReadingTarget.receipt,
    }[batch.target_type]
    default_channel = prof.get("channel") or ""
    if batch.target_type == QImportTarget.trip and not default_channel:
        comps = target.compartments or []
        default_channel = comps[0]["code"] if comps else "C1"
    parsed: list[tuple[int, datetime, Decimal | None, Decimal | None, str]] = []
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, datetime]] = set()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            at = parse_time(col(prof, row, "time") or "", prof)
            t_raw = parse_dec(col(prof, row, "temperature"), prof, "temperature")
            rh = parse_dec(col(prof, row, "humidity"), prof, "humidity")
            if t_raw is None and rh is None:
                raise RowError("no temperature or humidity")
            t_c = to_c(t_raw, prof) if t_raw is not None else None
            if t_c is not None and not (Decimal(-80) <= t_c <= Decimal(80)):
                raise RowError(f"temperature {t_c} °C outside −80…+80")
            if rh is not None and not (Decimal(0) <= rh <= Decimal(100)):
                raise RowError(f"humidity {rh} % outside 0…100")
            ch = (col(prof, row, "channel") or "").strip() or default_channel
            if (
                prof.get("logger_serial_column")
                and batch.target_type == QImportTarget.mapping_study
            ):
                ch = (row.get(prof["logger_serial_column"]) or "").strip() or ch
            key = (ch, at)
            if key in seen:
                raise RowError("time repeated in the file")
            seen.add(key)
            parsed.append((i, at, t_c, rh.quantize(TWO) if rh is not None else None, ch))
        except RowError as e:
            errors.append({"row": i, "reason": str(e)})
    if parsed:
        lo = min(x[1] for x in parsed)
        hi = max(x[1] for x in parsed)
        stored = {
            (r[0], r[1])
            for r in db.execute(
                select(QReading.channel, QReading.measured_at).where(
                    QReading.target_type == ttype,
                    QReading.target_id == batch.target_id,
                    QReading.voided.is_(False),
                    QReading.measured_at >= lo,
                    QReading.measured_at <= hi,
                )
            )
        }
        keep = []
        for x in parsed:
            if (x[4], x[1]) in stored:
                errors.append(
                    {
                        "row": x[0],
                        "reason": "a reading at this time is already stored for the target",
                    }
                )
            else:
                keep.append(x)
        parsed = keep
    t = now()
    if parsed:
        db.execute(
            insert(QReading),
            [
                {
                    "project_id": project.id,
                    "target_type": ttype,
                    "target_id": batch.target_id,
                    "channel": x[4],
                    "measured_at": x[1],
                    "temperature_c": x[2],
                    "humidity_pct": x[3],
                    "source": QReadingSource.import_,
                    "batch_id": batch.id,
                    "entered_by_user_id": uid,
                    "probe_fault": False,
                    "voided": False,
                    "created_at": t,
                }
                for x in parsed
            ],
        )
    errors.sort(key=lambda e: e["row"])
    batch.rows_accepted = len(parsed)
    batch.rows_rejected = len(errors)
    batch.errors = errors[:MAX_ERRORS]
    batch.first_at = min((x[1] for x in parsed), default=None)
    batch.last_at = max((x[1] for x in parsed), default=None)
    db.flush()
    found: list[Any] = []
    if parsed and batch.first_at and batch.last_at:
        found = recompute(db, project, batch, uid)
    return {"excursions": [excursions.brief(x) for x in found if not x.transient]}


def recompute(
    db: Session, project: Project, batch: QImportBatch, uid: uuid.UUID | None, notify: bool = True
) -> list[Any]:
    from app.services.quality.q3 import excursions, mapping  # noqa: PLC0415

    if batch.first_at is None or batch.last_at is None:
        return []
    if batch.target_type == QImportTarget.point:
        pt = db.get(QMonitoringPoint, batch.target_id)
        z = db.get(QStorageZone, pt.zone_id) if pt else None
        if z is None:
            return []
        return excursions.detect_zone(
            db, project, z, batch.first_at, batch.last_at, uid, notify=notify
        )
    if batch.target_type in (QImportTarget.trip,):
        t = db.get(QTrip, batch.target_id)
        if t is None:
            return []
        from app.services.quality.q3 import transport  # noqa: PLC0415

        found = excursions.detect_trip(db, project, t, uid, notify=notify)
        transport.on_transit_data(db, t)
        return found
    if batch.target_type == QImportTarget.mapping_study:
        m = db.get(QMappingStudy, batch.target_id)
        if m is not None:
            mapping.on_data(db, m)
    if batch.target_type == QImportTarget.receipt:
        from app.models.quality.q3 import QReceipt  # noqa: PLC0415

        r = db.get(QReceipt, batch.target_id)
        if r is not None:
            r.transit_batch_id = batch.id if batch.status == "imported" else None
    return []


# ---- stock snapshot, shipments, products, cycle counts (all or nothing) --------------------------


def _owners(db: Session, project: Project) -> dict[str, QCustomer]:
    return {
        c.code: c for c in db.scalars(select(QCustomer).where(QCustomer.project_id == project.id))
    }


def _products_by(db: Session, project: Project) -> dict[tuple[uuid.UUID | None, str], QProduct]:
    out: dict[tuple[uuid.UUID | None, str], QProduct] = {}
    for x in db.scalars(select(QProduct).where(QProduct.project_id == project.id)):
        out[(x.owner_customer_id, x.sku)] = x
        out.setdefault((None, x.sku), x)
    return out


def _zones(db: Session, project: Project) -> dict[str, uuid.UUID]:
    return {
        z.code: z.id
        for z in db.scalars(
            select(Zone).join(Site, Site.id == Zone.site_id).where(Site.project_id == project.id)
        )
    }


def _snapshot(
    db: Session,
    project: Project,
    batch: QImportBatch,
    rows: list[dict[str, str]],
    prof: dict[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    owners, prods, zones = _owners(db, project), _products_by(db, project), _zones(db, project)
    errors: list[dict[str, Any]] = []
    out = []
    for i, row in enumerate(rows, start=2):
        try:
            oc = (col(prof, row, "owner") or "").strip()
            owner = owners.get(oc) if oc else None
            if oc and owner is None:
                raise RowError(f"owner '{oc}' is not a customer of the project")
            sku = (col(prof, row, "sku") or "").strip()
            bt = (col(prof, row, "batch") or "").strip()
            loc = (col(prof, row, "location") or "").strip()
            if not sku or not bt or not loc:
                raise RowError("sku, batch and location are required")
            qty = parse_dec(col(prof, row, "qty"), prof, "qty", True)
            if qty is None or qty < 0:
                raise RowError("qty must be zero or more")
            zc = (col(prof, row, "zone") or "").strip() or None
            if zc and zc not in zones:
                raise RowError(f"zone '{zc}' is not on the project")
            prod = prods.get((owner.id if owner else None, sku))
            out.append(
                {
                    "owner_customer_id": owner.id
                    if owner
                    else (prod.owner_customer_id if prod else None),
                    "product_id": prod.id if prod else None,
                    "sku": sku,
                    "batch": bt,
                    "expiry_date": parse_date(col(prof, row, "expiry"), prof, "expiry"),
                    "receipt_date": parse_date(
                        col(prof, row, "receipt_date"), prof, "receipt_date"
                    ),
                    "location": loc,
                    "zone_code": zc,
                    "zone_id": zones.get(zc) if zc else None,
                    "qty": qty,
                    "unit": (col(prof, row, "unit") or "unit").strip() or "unit",
                    "wms_status": (col(prof, row, "wms_status") or "").strip() or None,
                }
            )
        except RowError as e:
            errors.append({"row": i, "reason": str(e)})
    _all_or_nothing(errors)
    snap = QStockSnapshot(
        id=uuid.uuid4(),
        project_id=project.id,
        site_id=batch.target_id,
        as_of=as_of,
        batch_id=batch.id,
        line_count=len(out),
        created_at=now(),
    )
    db.add(snap)
    db.flush()
    if out:
        db.execute(
            insert(QStockLine), [{**x, "id": uuid.uuid4(), "snapshot_id": snap.id} for x in out]
        )
    batch.rows_accepted = len(out)
    batch.first_at = batch.last_at = as_of
    return {"snapshot_id": snap.id}


def _shipments(
    db: Session,
    project: Project,
    batch: QImportBatch,
    rows: list[dict[str, str]],
    prof: dict[str, Any],
) -> dict[str, Any]:
    owners, prods = _owners(db, project), _products_by(db, project)
    trips = {t.trip_no: t for t in db.scalars(select(QTrip).where(QTrip.project_id == project.id))}
    errors: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    heads: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows, start=2):
        try:
            ref = (col(prof, row, "shipment_ref") or "").strip()
            sku = (col(prof, row, "sku") or "").strip()
            if not ref or not sku:
                raise RowError("shipment_ref and sku are required")
            oc = (col(prof, row, "owner") or "").strip()
            owner = owners.get(oc) if oc else None
            if oc and owner is None:
                raise RowError(f"owner '{oc}' is not a customer of the project")
            cons = (col(prof, row, "consignee") or "").strip()
            cons_c = owners.get(cons)
            tn = (col(prof, row, "trip_no") or "").strip()
            if tn and tn not in trips:
                raise RowError(f"trip '{tn}' not found")
            head = {
                "owner_customer_id": owner.id if owner else None,
                "consignee_customer_id": cons_c.id if cons_c else None,
                "consignee_name": (cons_c.name_en if cons_c else cons) or "—",
                "promised_at": parse_time(col(prof, row, "promised_at") or "", prof)
                if (col(prof, row, "promised_at") or "").strip()
                else None,
                "dispatched_at": parse_time(col(prof, row, "dispatched_at") or "", prof)
                if (col(prof, row, "dispatched_at") or "").strip()
                else None,
                "delivered_at": parse_time(col(prof, row, "delivered_at") or "", prof)
                if (col(prof, row, "delivered_at") or "").strip()
                else None,
                "trip_id": trips[tn].id if tn else None,
                "compartment": (col(prof, row, "compartment") or "").strip() or None,
            }
            if ref in heads and heads[ref]["consignee_name"] != head["consignee_name"]:
                raise RowError("one shipment has two consignees")
            heads.setdefault(ref, head)
            prod = prods.get((owner.id if owner else None, sku))
            groups[ref].append(
                {
                    "product_id": prod.id if prod else None,
                    "sku": sku,
                    "batch": (col(prof, row, "batch") or "").strip() or None,
                    "storage_class": prod.storage_class if prod else None,
                    "ordered_qty": parse_dec(
                        col(prof, row, "ordered_qty"), prof, "ordered_qty", True
                    ),
                    "delivered_qty": parse_dec(
                        col(prof, row, "delivered_qty"), prof, "delivered_qty"
                    ),
                }
            )
        except RowError as e:
            errors.append({"row": i, "reason": str(e)})
    existing = {
        s.shipment_ref: s
        for s in db.scalars(
            select(QShipment).where(
                QShipment.project_id == project.id, QShipment.shipment_ref.in_(list(groups))
            )
        )
    }
    for ref in groups:
        if ref in existing:
            errors.append({"row": 0, "reason": f"shipment {ref} was already imported"})
    _all_or_nothing(errors)
    t = now()
    created = 0
    for ref, ls in groups.items():
        s = QShipment(
            id=uuid.uuid4(),
            project_id=project.id,
            site_id=batch.target_id,
            shipment_ref=ref,
            batch_id=batch.id,
            created_at=t,
            seed_fake=batch.seed_fake,
            **heads[ref],
        )
        db.add(s)
        created += 1
        db.flush()
        for ln in ls:
            db.add(QShipmentLine(shipment_id=s.id, unit="unit", **ln))
    batch.rows_accepted = len(rows)
    db.flush()
    return {"shipments": created}


def _products(
    db: Session,
    project: Project,
    batch: QImportBatch,
    rows: list[dict[str, str]],
    prof: dict[str, Any],
    uid: uuid.UUID | None,
) -> dict[str, Any]:
    owners = _owners(db, project)
    have = {
        (x.owner_customer_id, x.sku): x
        for x in db.scalars(select(QProduct).where(QProduct.project_id == project.id))
    }
    errors: list[dict[str, Any]] = []
    out = []
    for i, row in enumerate(rows, start=2):
        try:
            oc = (col(prof, row, "owner") or "").strip()
            owner = owners.get(oc)
            if owner is None:
                raise RowError(f"owner '{oc}' is not a customer of the project")
            sku = (col(prof, row, "sku") or "").strip()
            desc = (col(prof, row, "description_en") or "").strip()
            if not sku or not desc:
                raise RowError("sku and description_en are required")
            sc_raw = (col(prof, row, "storage_class") or "").strip()
            try:
                sc = QStorageClass(sc_raw)
            except ValueError as e:
                raise RowError(f"storage_class '{sc_raw}' is not a storage class") from e
            gt = (col(prof, row, "gtin") or "").strip() or None
            if gt and not gtin_ok(gt):
                raise RowError(f"GTIN {gt} has a wrong length or check digit")
            sl = parse_dec(col(prof, row, "shelf_life_days"), prof, "shelf_life_days")
            mr = parse_dec(col(prof, row, "min_remaining_pct"), prof, "min_remaining_pct")
            dated_raw = (col(prof, row, "dated") or "true").strip().lower()
            out.append(
                {
                    "owner": owner,
                    "sku": sku,
                    "description_en": desc,
                    "description_ar": (col(prof, row, "description_ar") or "").strip(),
                    "gtin": gt,
                    "storage_class": sc,
                    "shelf_life_days": int(sl) if sl is not None else None,
                    "min_remaining_shelf_life_pct": mr,
                    "dated": dated_raw not in ("false", "0", "no", "n"),
                }
            )
        except RowError as e:
            errors.append({"row": i, "reason": str(e)})
    _all_or_nothing(errors)
    n_new = 0
    for x in out:
        cust_o: QCustomer = x.pop("owner")  # type: ignore[assignment]
        prow = have.get((cust_o.id, str(x["sku"])))
        if prow is None:
            prow = QProduct(
                project_id=project.id,
                owner_customer_id=cust_o.id,
                active=True,
                created_by_user_id=uid,
                seed_fake=batch.seed_fake,
            )
            db.add(prow)
            n_new += 1
        for k, v in x.items():
            setattr(prow, k, v)
    batch.rows_accepted = len(out)
    db.flush()
    return {"products_created": n_new, "products_updated": len(out) - n_new}


def _cycle_count(
    db: Session,
    project: Project,
    batch: QImportBatch,
    rows: list[dict[str, str]],
    prof: dict[str, Any],
    at: datetime,
    uid: uuid.UUID | None,
) -> dict[str, Any]:
    from app.services.quality.q3 import stock  # noqa: PLC0415

    prods = _products_by(db, project)
    errors: list[dict[str, Any]] = []
    out = []
    for i, row in enumerate(rows, start=2):
        try:
            sku = (col(prof, row, "sku") or "").strip()
            loc = (col(prof, row, "location") or "").strip()
            if not sku or not loc:
                raise RowError("sku and location are required")
            prod = prods.get((None, sku))
            out.append(
                {
                    "product_id": prod.id if prod else None,
                    "sku": sku,
                    "batch": (col(prof, row, "batch") or "").strip() or None,
                    "location": loc,
                    "zone_code": (col(prof, row, "zone") or "").strip() or None,
                    "system_qty": parse_dec(col(prof, row, "system_qty"), prof, "system_qty", True),
                    "counted_qty": parse_dec(
                        col(prof, row, "counted_qty"), prof, "counted_qty", True
                    ),
                    "recount_qty": parse_dec(col(prof, row, "recount_qty"), prof, "recount_qty"),
                    "tolerance": parse_dec(col(prof, row, "tolerance"), prof, "tolerance"),
                    "variance_reason": (col(prof, row, "variance_reason") or "").strip() or None,
                }
            )
        except RowError as e:
            errors.append({"row": i, "reason": str(e)})
    _all_or_nothing(errors)
    cc = stock.create_count(db, project, batch.target_id, at, out, uid, batch_id=batch.id)
    batch.rows_accepted = len(out)
    batch.first_at = batch.last_at = at
    return {"cycle_count_id": cc.id}


# ---- void (Q-IMP-05) -----------------------------------------------------------------------------


def void(db: Session, p: Principal, batch_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    bt = db.get(QImportBatch, batch_id)
    if bt is None or not p.can_see_project(bt.project_id):
        raise b.not_found(db, p, QRecordType.excursion, batch_id, None)
    project = qc.get_project(db, p, bt.project_id)
    qc.writable(project, p)
    g = p.require(project.id, C.quality_void)
    if g.scope.value == "responsible":
        raise forbidden_error()
    why = qc.reason(body.get("reason"))
    if bt.status != QImportStatus.imported:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "The batch is not imported.", "الدفعة غير مستوردة."
        )
    if now() > bt.imported_at + timedelta(hours=24):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A batch can only be voided within 24 h of import; later, imported data are never "
            "changed (Q-IMP-05).",
            "يمكن إلغاء الدفعة خلال 24 ساعة من الاستيراد فقط.",
        )
    if bt.kind == QImportKind.products:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Product imports are corrected by editing the products.",
            "تُصحح المنتجات بتعديلها.",
        )
    bt.status = QImportStatus.voided
    bt.voided_at = now()
    bt.voided_by_user_id = p.user.id
    bt.void_reason = why
    if bt.kind == QImportKind.readings:
        for r in db.scalars(select(QReading).where(QReading.batch_id == bt.id)):
            r.voided = True
        db.flush()
        recompute(db, project, bt, p.user.id, notify=False)
    elif bt.kind == QImportKind.stock_snapshot:
        for s in db.scalars(select(QStockSnapshot).where(QStockSnapshot.batch_id == bt.id)):
            s.voided = True
    elif bt.kind == QImportKind.cycle_count:
        for c in db.scalars(select(QCycleCount).where(QCycleCount.batch_id == bt.id)):
            c.voided = True
    elif bt.kind == QImportKind.shipments:
        for shp in db.scalars(select(QShipment).where(QShipment.batch_id == bt.id)):
            if shp.trip_id is not None:
                raise qc.err(
                    409,
                    ErrorCode.INVALID_TRANSITION,
                    f"{shp.shipment_ref} is on a trip; it stays.",
                    "الشحنة ضمن رحلة.",
                )
            for ln in db.scalars(select(QShipmentLine).where(QShipmentLine.shipment_id == shp.id)):
                db.delete(ln)
            db.delete(shp)
    b.audit_status(db, p, project, QRecordType.excursion, bt.id, "imported", "voided", reason=why)
    db.flush()
    return batch_read(db, bt)


# ---- reads --------------------------------------------------------------------------------------


def batch_read(db: Session, bt: QImportBatch) -> dict[str, Any]:
    return {
        "id": bt.id,
        "kind": bt.kind,
        "file_name": bt.file_name,
        "sha256": bt.sha256,
        "attachment_id": bt.attachment_id,
        "target_type": bt.target_type,
        "target_id": bt.target_id,
        "profile": bt.profile,
        "rows_read": bt.rows_read,
        "rows_accepted": bt.rows_accepted,
        "rows_rejected": bt.rows_rejected,
        "errors": bt.errors,
        "first_at": bt.first_at,
        "last_at": bt.last_at,
        "status": bt.status,
        "imported_at": bt.imported_at,
        "voided_at": bt.voided_at,
        "void_reason": bt.void_reason,
        "voidable": bt.status == QImportStatus.imported
        and now() <= bt.imported_at + timedelta(hours=24)
        and bt.kind != QImportKind.products,
    }


def list_batches(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page_no: int,
    size: int,
    kind: QImportKind | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    if g.scope.value == "responsible":
        raise forbidden_error()
    q = select(QImportBatch).where(QImportBatch.project_id == project.id)
    if kind:
        q = q.where(QImportBatch.kind == kind)
    rows = list(db.scalars(q.order_by(QImportBatch.imported_at.desc()).limit(500)))
    return b.page([batch_read(db, x) for x in rows], page_no, size)


def preview(content: bytes, kind: QImportKind, profile: dict[str, Any] | None) -> dict[str, Any]:
    """The first rows as the file will be read (the import screen shows them before importing)."""
    prof = normalise_profile(kind, profile)
    fields, rows = read_rows(content, prof)
    sample = []
    for row in rows[:10]:
        item: dict[str, Any] = {"raw": row}
        if kind == QImportKind.readings:
            try:
                at = parse_time(col(prof, row, "time") or "", prof)
                tv = parse_dec(col(prof, row, "temperature"), prof, "temperature")
                item.update(
                    {"measured_at": at, "temperature_c": to_c(tv, prof) if tv is not None else None}
                )
            except RowError as e:
                item["error"] = str(e)
        sample.append(item)
    return {"columns": fields, "rows": len(rows), "sample": sample, "profile": prof}


def profiles(
    db: Session, p: Principal, project_id: uuid.UUID, kind: QImportKind
) -> list[dict[str, Any]]:
    """Saved column mappings: the distinct profiles of the recent batches of a kind."""
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    out: list[dict[str, Any]] = []
    for bt in db.scalars(
        select(QImportBatch)
        .where(
            QImportBatch.project_id == project.id,
            QImportBatch.kind == kind,
            QImportBatch.status == QImportStatus.imported,
        )
        .order_by(QImportBatch.imported_at.desc())
        .limit(50)
    ):
        if bt.profile not in out:
            out.append(bt.profile)
    return out[:10]
