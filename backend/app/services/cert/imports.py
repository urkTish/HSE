"""Certificate imports: CSV/XLSX dry-run → commit the valid rows (spec 4-third-party-cert §3.15,
§4.9, IM-1…IM-7).

ID numbers in personnel files are used only for the blind-index lookup and the PC-3 match: they
are kept encrypted per row until commit / discard / expiry and never echoed (masked, WK-4)."""

import hashlib
import io
import re
import uuid
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import WorkerIdType
from app.core.cert_enums import (
    CertImportCode,
    CertImportSource,
    CertImportStatus,
    CertImportTemplate,
    CertInspectionType,
    CertKind,
    CertSource,
    CertVerificationMethod,
    DefectCategory,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    IdMatchResult,
    LimitationCode,
    LineResult,
    NameMatch,
    PersonnelLimitationCode,
    ServiceStatus,
    VerificationOutcome,
    VerificationStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, ExportFormat, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner, ImportRowStatus
from app.models import (
    Attachment,
    CertImportBatch,
    CertVerification,
    Contractor,
    EquipmentCertificate,
    EquipmentDeployment,
    EquipmentItem,
    PersonnelCertificate,
    Project,
    ProjectEngagement,
    Tpi,
    Worker,
    WorkerIdHistory,
)
from app.schemas.cert_imports import (
    CertImportCounts,
    CertImportIssue,
    CertImportPage,
    CertImportRead,
    CertImportRowReport,
    CertImportSummary,
)
from app.schemas.equipment_certs import CertLineInput, EquipmentCertificateCreate
from app.services import attachments, projects
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.cert import alerts, validity
from app.services.cert import common as cc
from app.services.cert import equipment_certs as ecs
from app.services.cert import personnel as pcs
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.cert import tpis as tsvc
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.workforce_import import (
    _norm_header,
    _parse_date,
    _read_table,
    file_invalid,
)

C = Capability
IC = CertImportCode
T = CertImportTemplate
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_ZIP = 200 * 1024 * 1024
TTL = timedelta(minutes=60)
SCAN_EXT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

# (key, Arabic header, required)
EQ_COLS: list[tuple[str, str, bool]] = [
    ("project_code", "رمز المشروع", True),
    ("tag", "رقم البطاقة", False),
    ("equipment_no", "رقم المعدة", False),
    ("category", "الفئة", True),
    ("manufacturer", "الشركة المصنعة", True),
    ("serial_no", "الرقم التسلسلي", True),
    ("tpi_code", "رمز الجهة", True),
    ("cert_no", "رقم الشهادة", True),
    ("inspection_type", "نوع الفحص", True),
    ("inspected_on", "تاريخ الفحص", True),
    ("issued_on", "تاريخ الإصدار", True),
    ("printed_next_due", "موعد الفحص التالي", False),
    ("result", "النتيجة", True),
    ("swl_t", "الحمولة الآمنة", False),
    ("load_test_pct", "نسبة اختبار التحميل", False),
    ("limitations", "القيود", False),
    ("defects", "العيوب", False),
    ("colour_code", "رمز اللون", False),
    ("inspector_name", "اسم المفتش", False),
    ("model", "الطراز", False),
    ("contractor_code", "رمز المقاول", False),
]
PC_COLS: list[tuple[str, str, bool]] = [
    ("worker_no", "رقم العامل", False),
    ("id_type", "نوع الهوية", False),
    ("id_number", "رقم الهوية", False),
    ("passport_country", "بلد الجواز", False),
    ("cert_type", "نوع الشهادة", True),
    ("tpi_code", "رمز الجهة", True),
    ("cert_no", "رقم الشهادة", True),
    ("issued_on", "تاريخ الإصدار", True),
    ("printed_expiry", "تاريخ الانتهاء", False),
    ("scope_categories", "نطاق المعدات", False),
    ("max_capacity_t", "أقصى حمولة", False),
    ("level", "المستوى", False),
    ("limitations", "القيود", False),
    ("name_as_printed", "الاسم كما في الشهادة", True),
    ("id_on_card", "الهوية في البطاقة", False),
]

MESSAGES: dict[IC, tuple[str, str]] = {
    IC.E01: (
        "Project code unknown or not this batch's project.",
        "رمز المشروع غير معروف أو ليس مشروع الدفعة.",
    ),
    IC.E02: ("Equipment / worker not found.", "المعدة أو العامل غير موجود."),
    IC.E03: (
        "Category / certificate type not recognised or not matching.",
        "الفئة أو نوع الشهادة غير معروف أو غير مطابق.",
    ),
    IC.E04: (
        "TPI unknown or not acceptable at the date.",
        "الجهة غير معروفة أو غير مقبولة في التاريخ.",
    ),
    IC.E05: ("Serial number does not match the item.", "الرقم التسلسلي لا يطابق المعدة."),
    IC.E06: ("Duplicate certificate.", "شهادة مكررة."),
    IC.E07: (
        "Dates invalid or certificate already expired.",
        "التواريخ غير صحيحة أو الشهادة منتهية.",
    ),
    IC.E08: (
        "Result invalid or SWL above the rated capacity.",
        "النتيجة غير صحيحة أو الحمولة أعلى من السعة.",
    ),
    IC.E09: ("ID on the card does not match the worker.", "الهوية في البطاقة لا تطابق العامل."),
    IC.E10: ("Row outside your scope.", "السطر خارج نطاق صلاحيتك."),
    IC.E11: ("Holder banned or item blacklisted.", "حامل الشهادة محظور أو المعدة محظورة."),
    IC.E12: ("Unparseable date or number.", "تاريخ أو رقم غير قابل للقراءة."),
    IC.W01: (
        "Printed date beyond the platform interval / cap (valid_until shortened).",
        "التاريخ المطبوع يتجاوز الحد (ستُقصّر الصلاحية).",
    ),
    IC.W02: (
        "Name on the card matches only partly or not at all.",
        "الاسم في البطاقة مطابق جزئياً أو غير مطابق.",
    ),
    IC.W03: (
        "No scan in the zip for this certificate (stays Draft).",
        "لا توجد نسخة في الملف المضغوط (تبقى مسودة).",
    ),
    IC.W04: ("TPI accreditation expires within 30 days.", "ينتهي اعتماد الجهة خلال 30 يوماً."),
    IC.W05: (
        "The same file was already committed on this project.",
        "تم اعتماد الملف نفسه سابقاً في هذا المشروع.",
    ),
    IC.W06: ("Certificate expires within 30 days.", "تنتهي الشهادة خلال 30 يوماً."),
}
ERRORS = {c for c in IC if c.value.startswith("E")}


def issue(code: IC, column: str | None = None, **meta: str) -> dict[str, Any]:
    en, ar = MESSAGES[code]
    return {"code": code.value, "column": column, "message_en": en, "message_ar": ar, "meta": meta}


def _cols(t: CertImportTemplate) -> list[tuple[str, str, bool]]:
    return EQ_COLS if t == T.equipment_certificates else PC_COLS


def _hmap(t: CertImportTemplate) -> dict[str, str]:
    out = {}
    for k, ar, _ in _cols(t):
        out[k] = k
        out[_norm_header(ar)] = k
        out[ar] = k
    return out


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _dec(v: Any) -> tuple[Decimal | None, bool]:
    s = _s(v)
    if s is None:
        return None, True
    try:
        return Decimal(s), True
    except InvalidOperation:
        return None, False


def _date(v: Any) -> tuple[date | None, bool]:
    if _s(v) is None and not isinstance(v, date):
        return None, True
    d = _parse_date(v)
    return d, d is not None


# ---- parse ----


def parse(t: CertImportTemplate, name: str, content: bytes) -> list[dict[str, Any]]:
    if len(content) > MAX_BYTES:
        raise file_invalid("The file is larger than 5 MB (E12).")
    table = _read_table(name, content)
    while table and all(c in (None, "") for c in table[-1]):
        table.pop()
    if not table:
        raise file_invalid("The file is empty (E12).")
    hm = _hmap(t)
    headers = [hm.get(_norm_header(h)) or hm.get(str(h or "").strip()) for h in table[0]]
    missing = [k for k, _, req in _cols(t) if req and k not in headers]
    if t == T.equipment_certificates and "tag" not in headers and "equipment_no" not in headers:
        missing.append("tag")
    if t == T.personnel_certificates and "worker_no" not in headers and "id_number" not in headers:
        missing.append("worker_no")
    if missing:
        raise ApiError(
            422,
            ErrorCode.IMPORT_FILE_INVALID,
            "Missing required column(s): " + ", ".join(missing) + " (E12).",
            "أعمدة مطلوبة مفقودة: " + "، ".join(missing),
        )
    data = [r for r in table[1:] if any(c not in (None, "") for c in r)]
    if len(data) > MAX_ROWS:
        raise file_invalid(f"The file has more than {MAX_ROWS:,} data rows (E12).")
    rows = []
    for i, raw in enumerate(data, start=1):
        vals = {h: raw[j] if j < len(raw) else None for j, h in enumerate(headers) if h}
        row: dict[str, Any] = {"row_no": i, "issues": []}
        for k, _ar, _req in _cols(t):
            v = vals.get(k)
            if k in ("inspected_on", "issued_on", "printed_next_due", "printed_expiry"):
                d, ok = _date(v)
                if not ok:
                    row["issues"].append(issue(IC.E12, k))
                row[k] = d.isoformat() if d else None
            elif k in ("swl_t", "load_test_pct", "max_capacity_t"):
                n, ok = _dec(v)
                if not ok:
                    row["issues"].append(issue(IC.E12, k))
                row[k] = str(n) if n is not None else None
            elif k == "id_number":
                s = _s(v)
                row["id_number_enc"] = crypto.encrypt(s).hex() if s else None
            elif k == "id_on_card":
                s = _s(v)
                if s and s.lower() not in ("same_as_lookup", "same"):
                    row["id_on_card_enc"] = crypto.encrypt(s).hex()
                    row["id_on_card"] = "number"
                else:
                    row["id_on_card"] = "same_as_lookup" if s else None
            else:
                row[k] = _s(v)
        rows.append(row)
    return rows


def _dec_id(hexv: str | None) -> str | None:
    return crypto.decrypt(bytes.fromhex(hexv)) if hexv else None


# ---- validation ----


def _tpi(db: Session, code: str | None) -> Tpi | None:
    if not code:
        return None
    return db.scalar(select(Tpi).where(func.upper(Tpi.tpi_code) == code.upper()))


def _parse_lims(v: str | None) -> list[dict[str, Any]] | None:
    out = []
    for raw in (v or "").split(";"):
        part = raw.strip()
        if not part:
            continue
        code, _, val = part.partition(":")
        code = code.strip()
        if code not in LimitationCode.__members__:
            return None
        val = val.strip()
        if code in ("derated_swl", "max_wind_ms", "reinspect_after_hours"):
            try:
                out.append(
                    {"code": code, "value": str(Decimal(val)) if val else None, "text": None}
                )
            except InvalidOperation:
                return None
        else:
            out.append({"code": code, "value": None, "text": val or None})
    return out


def _parse_defects(v: str | None) -> list[dict[str, Any]] | None:
    out = []
    for raw in (v or "").split(";"):
        part = raw.strip()
        if not part:
            continue
        cat, _, text = part.partition(":")
        if cat.strip() not in ("A", "B", "C") or not text.strip():
            return None
        out.append({"category": cat.strip(), "description_en": text.strip()})
    return out


def _err(row: dict[str, Any], code: IC, col: str | None = None, **meta: str) -> None:
    row["issues"].append(issue(code, col, **meta))


def _validate_eq(
    db: Session, p: Principal, b: CertImportBatch, project: Project, rows: list[dict[str, Any]]
) -> None:
    g = p.grant(project.id, C.cert_import)
    s = cset.get(db, project.id)
    d0 = today()
    seen: dict[tuple[str, str, str], int] = {}
    for r in rows:
        r["issues"] = [i for i in r["issues"] if i["code"] == IC.E12.value]
        r["action"] = "none"
        if (r.get("project_code") or "").upper() != project.code.upper():
            _err(r, IC.E01, "project_code")
        cat = r.get("category")
        if cat not in EquipmentCertCategory.__members__ or cat == "scaffold":
            _err(r, IC.E03, "category")
            cat = None
        item = None
        dep = None
        tag = r.get("tag")
        if tag:
            dep = db.scalar(
                select(EquipmentDeployment).where(
                    EquipmentDeployment.project_id == project.id,
                    func.upper(EquipmentDeployment.tag) == tag.upper(),
                    EquipmentDeployment.status != EquipmentDeploymentStatus.cancelled,
                )
            )
            item = db.get(EquipmentItem, dep.equipment_id) if dep else None
        if item is None and r.get("equipment_no"):
            item = db.scalar(
                select(EquipmentItem).where(EquipmentItem.equipment_no == r["equipment_no"].upper())
            )
            if item is not None:
                dep = cc.latest_deployment_on(db, item.id, project.id)
        if item is None:
            if b.create_items and tag and cat and r.get("manufacturer") and r.get("serial_no"):
                con = _contractor(db, project.id, r.get("contractor_code"))
                if con is None:
                    _err(r, IC.E02, "contractor_code")
                else:
                    dup = db.scalar(
                        select(EquipmentItem).where(
                            EquipmentItem.serial_norm == cc.serial_norm(r["serial_no"]),
                            EquipmentItem.manufacturer_norm
                            == cc.manufacturer_norm(r["manufacturer"]),
                        )
                    )
                    if dup is not None and dup.service_status == ServiceStatus.blacklisted:
                        _err(r, IC.E11, "serial_no")
                    elif dup is not None:
                        _err(r, IC.E02, "tag")
                    else:
                        r["action"] = "create_item_and_certificate"
            else:
                _err(r, IC.E02, "tag")
        else:
            if cat and item.category.value != cat:
                _err(r, IC.E03, "category")
            if r.get("serial_no") and cc.serial_norm(r["serial_no"]) != item.serial_norm:
                _err(r, IC.E05, "serial_no")
            if item.service_status == ServiceStatus.blacklisted:
                _err(r, IC.E11, "tag")
            if dep is None:
                _err(r, IC.E02, "tag")
            elif not acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
                _err(r, IC.E10, "tag")
            r["equipment_id"] = str(item.id)
            r["action"] = "create_certificate"
        t = _tpi(db, r.get("tpi_code"))
        insp = date.fromisoformat(r["inspected_on"]) if r.get("inspected_on") else None
        issued = date.fromisoformat(r["issued_on"]) if r.get("issued_on") else None
        nxt = date.fromisoformat(r["printed_next_due"]) if r.get("printed_next_due") else None
        if t is None:
            _err(r, IC.E04, "tpi_code")
        elif insp is not None:
            acc = tsvc.acceptability(
                db, t, insp, categories=[cat] if cat else (), project_id=project.id
            )
            if not acc.ok:
                _err(r, IC.E04, "tpi_code", reason=str(acc.reason or ""))
            elif _acc_expiring(db, t, d0):
                _err(r, IC.W04, "tpi_code")
        it = r.get("inspection_type")
        if it not in CertInspectionType.__members__:
            _err(r, IC.E03, "inspection_type")
        res = (r.get("result") or "").lower()
        if res not in ("pass", "pass_with_conditions", "fail"):
            _err(r, IC.E08, "result")
        r["result"] = res
        if item is not None and r.get("swl_t") and item.rated_capacity_t is not None:  # noqa: SIM102
            if Decimal(r["swl_t"]) > item.rated_capacity_t:
                _err(r, IC.E08, "swl_t")
        if _parse_lims(r.get("limitations")) is None:
            _err(r, IC.E12, "limitations")
        if _parse_defects(r.get("defects")) is None:
            _err(r, IC.E12, "defects")
        if insp and issued and (issued < insp or issued > d0 or (nxt is not None and nxt <= insp)):
            _err(r, IC.E07, "issued_on")
        if insp and cat:
            months = cset.interval_months(s, cat) or 12
            vu, _lf, end = validity.line_validity(insp, nxt, months)
            r["valid_until"] = vu.isoformat()
            if vu < d0:
                _err(r, IC.E07, "printed_next_due")
            else:
                if nxt is not None and nxt > end:
                    _err(r, IC.W01, "printed_next_due")
                if vu <= d0 + timedelta(days=30):
                    _err(r, IC.W06, "printed_next_due")
        # E06
        key = (
            (r.get("tpi_code") or "").upper(),
            (r.get("cert_no") or "").upper(),
            (tag or r.get("equipment_no") or "").upper(),
        )
        if key in seen:
            _err(r, IC.E06, "cert_no")
        seen[key] = r["row_no"]
        if t is not None and r.get("cert_no"):  # noqa: SIM102
            if db.scalar(
                select(EquipmentCertificate.id).where(
                    EquipmentCertificate.tpi_id == t.id,
                    func.upper(EquipmentCertificate.cert_no) == r["cert_no"].upper(),
                )
            ):
                _err(r, IC.E06, "cert_no")
        if b.scans_zip_name is not None:
            r["scan_found"] = (r.get("cert_no") or "").upper() in {
                k.upper() for k in (b.scan_map or {})
            }
            if not r["scan_found"]:
                _err(r, IC.W03, "cert_no")
        _w05(db, b, r)
        _finish(r)


def _acc_expiring(db: Session, t: Tpi, d0: date) -> bool:
    accs = [a for a in tsvc.accreditations(db, t.id) if tsvc.counts(a, d0)]
    return bool(accs) and min(a.valid_until for a in accs) <= d0 + timedelta(days=30)


def _contractor(db: Session, project_id: uuid.UUID, code: str | None) -> ProjectEngagement | None:
    if not code:
        return None
    return db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(
            ProjectEngagement.project_id == project_id,
            func.upper(Contractor.short_code) == code.upper(),
        )
        .limit(1)
    )


def _w05(db: Session, b: CertImportBatch, r: dict[str, Any]) -> None:
    if db.scalar(
        select(CertImportBatch.id).where(
            CertImportBatch.project_id == b.project_id,
            CertImportBatch.file_sha256 == b.file_sha256,
            CertImportBatch.status == CertImportStatus.committed,
            CertImportBatch.id != b.id,
        )
    ):
        _err(r, IC.W05)


def _finish(r: dict[str, Any]) -> None:
    codes = [i["code"] for i in r["issues"]]
    r["codes"] = list(dict.fromkeys(codes))
    if any(c in {e.value for e in ERRORS} for c in codes):
        r["status"] = ImportRowStatus.error.value
        r["action"] = "none"
    elif codes:
        r["status"] = ImportRowStatus.warning.value
    else:
        r["status"] = ImportRowStatus.ok.value


def _worker_by_id(
    db: Session, id_type: str | None, number: str | None, country: str | None
) -> tuple[Worker | None, str | None]:
    if not id_type or not number or id_type not in WorkerIdType.__members__:
        return None, None
    it = WorkerIdType(id_type)
    try:
        bidx = acommon.blind_index(it, number, country)
    except Exception:
        return None, None
    masked = acommon.mask_worker_id(it, number)
    return db.scalar(select(Worker).where(Worker.id_number_bidx == bidx)), masked


def _validate_pc(
    db: Session, p: Principal, b: CertImportBatch, project: Project, rows: list[dict[str, Any]]
) -> None:
    g = p.grant(project.id, C.cert_import)
    s = cset.get(db, project.id)
    d0 = today()
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        r["issues"] = [i for i in r["issues"] if i["code"] == IC.E12.value]
        r["action"] = "none"
        w: Worker | None = None
        if r.get("worker_no"):
            w = db.scalar(select(Worker).where(Worker.worker_no == r["worker_no"].upper()))
        number = _dec_id(r.get("id_number_enc"))
        if w is None and number:
            w, r["id_masked"] = _worker_by_id(
                db, r.get("id_type"), number, r.get("passport_country")
            )
        elif number and r.get("id_type") in WorkerIdType.__members__:
            r["id_masked"] = acommon.mask_worker_id(WorkerIdType(r["id_type"]), number)
        dep = None
        if w is None:
            _err(r, IC.E02, "worker_no")
        else:
            r["worker_no"] = w.worker_no
            r["worker_id"] = str(w.id)
            dep = pcs.deployment(db, w.id, project.id)
            if dep is None or not acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
                _err(r, IC.E10, "worker_no")
        ctype = (r.get("cert_type") or "").upper()
        r["cert_type"] = ctype
        if not cset.is_type(db, ctype):
            _err(r, IC.E03, "cert_type")
        t = _tpi(db, r.get("tpi_code"))
        issued = date.fromisoformat(r["issued_on"]) if r.get("issued_on") else None
        exp = date.fromisoformat(r["printed_expiry"]) if r.get("printed_expiry") else None
        if t is None:
            _err(r, IC.E04, "tpi_code")
        elif issued is not None:
            acc = tsvc.acceptability(db, t, issued, cert_type=ctype, project_id=project.id)
            if not acc.ok:
                _err(r, IC.E04, "tpi_code", reason=str(acc.reason or ""))
            elif _acc_expiring(db, t, d0):
                _err(r, IC.W04, "tpi_code")
        if issued and (issued > d0 or (exp is not None and exp <= issued)):
            _err(r, IC.E07, "issued_on")
        if issued and cset.is_type(db, ctype):
            months = cset.cap_months(db, s, ctype) or 36
            vu, _lf, end = validity.personnel_validity(issued, exp, months)
            r["valid_until"] = vu.isoformat()
            if vu < d0:
                _err(r, IC.E07, "printed_expiry")
            else:
                if exp is not None and exp > end:
                    _err(r, IC.W01, "printed_expiry")
                if vu <= d0 + timedelta(days=30):
                    _err(r, IC.W06, "printed_expiry")
        # PC-7 scope / level
        pct = ref.PCT.get(ctype)
        scope = [
            x.strip()
            for x in (r.get("scope_categories") or "").replace(";", ",").split(",")
            if x.strip()
        ]
        r["scope_list"] = scope
        if (
            pct is not None
            and pct.scope_allowed
            and (not scope or not set(scope) <= {q.value for q in pct.scope_allowed})
        ):
            _err(r, IC.E03, "scope_categories")
        lv = r.get("level")
        if pct is not None and lv and pct.levels and lv not in {x.value for x in pct.levels}:
            _err(r, IC.E03, "level")
        if pct is not None and lv and lv in {x.value for x in pct.rejected_levels}:
            _err(r, IC.E03, "level")
        lims = []
        for part in (r.get("limitations") or "").split(";"):
            code, _, text = part.strip().partition(":")
            if not code:
                continue
            if code.strip() not in PersonnelLimitationCode.__members__:
                _err(r, IC.E12, "limitations")
                break
            lims.append({"code": code.strip(), "text": text.strip() or None})
        r["limitations_list"] = lims
        if w is not None:
            if validity.active_ban(db, w.id, ctype, d0) is not None:
                _err(r, IC.E11, "worker_no")
            nm = pcs.name_match(r.get("name_as_printed") or "", w)
            r["name_match"] = nm.value
            if nm != NameMatch.exact:
                _err(r, IC.W02, "name_as_printed")
            r["id_match"] = _id_match(db, w, r, number)
            if r["id_match"] is None:
                _err(r, IC.E09, "id_on_card")
        key = ((r.get("tpi_code") or "").upper(), ctype, (r.get("cert_no") or "").upper())
        if key in seen:
            _err(r, IC.E06, "cert_no")
        seen.add(key)
        if t is not None and r.get("cert_no"):  # noqa: SIM102
            if db.scalar(
                select(PersonnelCertificate.id).where(
                    PersonnelCertificate.tpi_id == t.id,
                    PersonnelCertificate.cert_type == ctype,
                    func.upper(PersonnelCertificate.cert_no) == r["cert_no"].upper(),
                )
            ):
                _err(r, IC.E06, "cert_no")
        if b.scans_zip_name is not None:
            keys = {k.upper() for k in (b.scan_map or {})}
            r["scan_found"] = (
                r.get("cert_no") or ""
            ).upper() in keys or f"{(r.get('cert_no') or '').upper()}_FRONT" in keys
            if not r["scan_found"]:
                _err(r, IC.W03, "cert_no")
        if r["issues"] == [] or all(i["code"].startswith("W") for i in r["issues"]):
            r["action"] = "create_certificate"
        _w05(db, b, r)
        _finish(r)


def _id_match(db: Session, w: Worker, r: dict[str, Any], lookup_number: str | None) -> str | None:
    """PC-3 for an import row → matched / matched_previous_id / not_shown, or None (E09)."""
    mode = r.get("id_on_card")
    if not mode:
        return IdMatchResult.not_shown.value
    number = lookup_number if mode == "same_as_lookup" else _dec_id(r.get("id_on_card_enc"))
    id_type = r.get("id_type") or (w.id_type.value if w.id_type else None)
    if not number or not id_type or id_type not in WorkerIdType.__members__:
        return None
    it = WorkerIdType(id_type)
    try:
        bidx = acommon.blind_index(it, number, r.get("passport_country") or w.passport_country)
    except Exception:
        return None
    if bidx == w.id_number_bidx:
        return IdMatchResult.matched.value
    for h in db.scalars(select(WorkerIdHistory).where(WorkerIdHistory.worker_id == w.id)):
        try:
            old = crypto.decrypt(h.id_number_enc)
        except Exception:  # noqa: S112
            continue
        if acommon.blind_index(h.id_type, old, h.passport_country) == bidx:
            return IdMatchResult.matched_previous_id.value
    return None


def validate(
    db: Session, p: Principal, b: CertImportBatch, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    project = db.get(Project, b.project_id)
    assert project is not None  # noqa: S101
    if b.template == T.equipment_certificates:
        _validate_eq(db, p, b, project, rows)
    else:
        _validate_pc(db, p, b, project, rows)
    return rows


# ---- counts / read ----


def _counts(b: CertImportBatch, rows: list[dict[str, Any]]) -> dict[str, int]:
    ok = [r for r in rows if r["status"] != ImportRowStatus.error.value]
    if b.template == T.equipment_certificates:
        certs = len(
            {((r.get("tpi_code") or "").upper(), (r.get("cert_no") or "").upper()) for r in ok}
        )
    else:
        certs = len(ok)
    return {
        "rows_total": len(rows),
        "rows_ok": sum(1 for r in rows if r["status"] == ImportRowStatus.ok.value),
        "rows_warning": sum(1 for r in rows if r["status"] == ImportRowStatus.warning.value),
        "rows_error": sum(1 for r in rows if r["status"] == ImportRowStatus.error.value),
        "certificates_valid": certs,
        "items_to_create": sum(1 for r in ok if r.get("action") == "create_item_and_certificate"),
        "certificates_created": (b.counts or {}).get("certificates_created", 0),
        "certificates_left_draft": (b.counts or {}).get("certificates_left_draft", 0),
        "items_created": (b.counts or {}).get("items_created", 0),
    }


def _report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        out.append(
            {
                "row_no": r["row_no"],
                "status": r["status"],
                "codes": r.get("codes", []),
                "issues": r["issues"],
                "tpi_code": r.get("tpi_code"),
                "cert_no": r.get("cert_no"),
                "tag": r.get("tag") or r.get("equipment_no"),
                "category": r.get("category"),
                "worker_no": r.get("worker_no"),
                "id_masked": r.get("id_masked"),
                "cert_type": r.get("cert_type")
                if "worker_no" in r or "id_number_enc" in r
                else None,
                "scan_found": r.get("scan_found"),
                "action": r.get("action"),
            }
        )
    return out


def _issue_read(i: dict[str, Any]) -> CertImportIssue:
    return CertImportIssue(
        code=IC(i["code"]),
        column=i.get("column"),
        message_en=i["message_en"],
        message_ar=i["message_ar"],
        meta={k: str(v) for k, v in (i.get("meta") or {}).items()},
    )


def to_read(db: Session, b: CertImportBatch, include_ok: bool = False) -> CertImportRead:
    refs = Refs(db).load(users=[b.uploaded_by_user_id])
    t = db.get(Tpi, b.tpi_id) if b.tpi_id else None
    rep = [r for r in b.report or [] if include_ok or r["status"] != ImportRowStatus.ok.value]
    rep.sort(key=lambda r: ({"error": 0, "warning": 1, "ok": 2}[r["status"]], r["row_no"]))
    counts = {**_zero_counts(), **(b.counts or {})}
    return CertImportRead(
        id=b.id,
        project_id=b.project_id,
        template=b.template,
        source=b.source,
        tpi_code=t.tpi_code if t else None,
        file_name=b.file_name,
        file_sha256=b.file_sha256,
        file_size=b.file_size,
        sensitive=b.sensitive,
        create_items=b.create_items,
        scans_zip_name=b.scans_zip_name,
        scans_count=b.scans_count,
        evidence_file_name=b.evidence_file_name,
        evidence_sha256=b.evidence_sha256,
        status=_status(b),
        counts=CertImportCounts(**counts),
        file_issues=[_issue_read(i) for i in b.file_issues or []],
        report=[
            CertImportRowReport(
                row_no=r["row_no"],
                status=ImportRowStatus(r["status"]),
                codes=[IC(c) for c in r.get("codes", [])],
                issues=[_issue_read(i) for i in r["issues"]],
                tpi_code=r.get("tpi_code"),
                cert_no=r.get("cert_no"),
                tag=r.get("tag"),
                category=r.get("category"),
                worker_no=r.get("worker_no"),
                id_masked=r.get("id_masked"),
                cert_type=r.get("cert_type"),
                scan_found=r.get("scan_found"),
                action=r.get("action"),
            )
            for r in rep
        ],
        uploaded_by=refs.user(b.uploaded_by_user_id) or cc.UNKNOWN_USER,
        created_at=b.created_at,
        expires_at=b.expires_at,
        committed_at=b.committed_at,
        committed_certificate_ids=list(b.committed_certificate_ids or [])[:500],
    )


def _zero_counts() -> dict[str, int]:
    return dict.fromkeys(CertImportCounts.model_fields, 0)


def _status(b: CertImportBatch) -> CertImportStatus:
    if b.status == CertImportStatus.validated and b.expires_at <= now():
        return CertImportStatus.expired
    return b.status


# ---- upload (dry run) ----


def _read_upload(f: UploadFile | None, limit: int) -> tuple[str, bytes] | None:
    if f is None:
        return None
    content = f.file.read(limit + 1)
    if len(content) > limit:
        raise file_invalid("The file is too large.")
    return f.filename or "file", content


def _require(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = projects.get_visible(db, p, project_id)
    cc.require(p, project.id, C.cert_import)
    return project


def _evidence_ok(t: Tpi, content: bytes) -> bool:
    """IM-6: the evidence is an email from one of the TPI's verification domains."""
    text = content.decode("utf-8", errors="ignore")
    m = re.search(r"^From:.*?@([A-Za-z0-9.-]+)", text, flags=re.MULTILINE | re.IGNORECASE)
    hosts = (
        [m.group(1)]
        if m
        else re.findall(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)[:5]
    )
    return any(tsvc.domain_registered(t, h.lower()) for h in hosts)


def dry_run(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    file_name: str,
    content: bytes,
    template: CertImportTemplate,
    source: CertImportSource = CertImportSource.contractor_file,
    create_items: bool = False,
    tpi_id: uuid.UUID | None = None,
    scans: tuple[str, bytes] | None = None,
    evidence: tuple[str, bytes] | None = None,
) -> CertImportRead:
    project = _require(db, p, project_id)
    hse = cc.is_hse(p, project.id)
    if create_items and (not hse or template != T.equipment_certificates):
        raise forbidden_error("Creating items from an import is for HSE Officers / Manager.")
    t = None
    if source == CertImportSource.tpi_register_file:
        if not hse:
            raise ApiError(
                403,
                ErrorCode.IMPORT_SOURCE_NOT_ALLOWED,
                "A TPI register file is imported by HSE Officers / Manager only.",
                "يستورد ملف سجل الجهة مسؤولو السلامة فقط.",
            )
        t = db.get(Tpi, tpi_id) if tpi_id else None
        if t is None:
            raise not_found("TPI")
        if evidence is None or not _evidence_ok(t, evidence[1]):
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_DOMAIN_MISMATCH,
                "The evidence must be an email from one of the TPI's verification domains.",
                "يجب أن يكون الدليل بريداً من أحد نطاقات التحقق للجهة.",
            )
    rows = parse(template, file_name, content)
    sensitive = any(r.get("id_number_enc") or r.get("id_on_card_enc") for r in rows)
    at = now()
    b = CertImportBatch(
        id=uuid.uuid4(),
        project_id=project.id,
        template=template,
        source=source,
        tpi_id=t.id if t else None,
        file_name=file_name[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        file_size=len(content),
        sensitive=sensitive,
        create_items=create_items,
        scans_zip_name=scans[0][:255] if scans else None,
        scans_count=None,
        scan_map={},
        evidence_file_name=evidence[0][:255] if evidence else None,
        evidence_sha256=hashlib.sha256(evidence[1]).hexdigest() if evidence else None,
        status=CertImportStatus.validated,
        counts={},
        file_issues=[],
        report=[],
        rows=[],
        committed_certificate_ids=[],
        uploaded_by_user_id=p.user.id,
        created_at=at,
        expires_at=at + TTL,
    )
    db.add(b)
    db.flush()
    if scans is not None:
        _store_scans(db, p, b, template, scans[1])
    rows = validate(db, p, b, rows)
    b.rows = rows
    b.report = _report(rows)
    b.counts = _counts(b, rows)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.create,
        EntityType.cert_import_batch,
        b,
        project.id,
        after={"file": b.file_name, "template": template.value, "counts": b.counts},
    )
    return to_read(db, b, include_ok=True)


def _store_scans(
    db: Session, p: Principal, b: CertImportBatch, template: CertImportTemplate, data: bytes
) -> None:
    if len(data) > MAX_ZIP:
        raise file_invalid("The scans zip is larger than 200 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise file_invalid("The scans file is not a valid zip.") from exc
    owner = (
        AttachmentOwner.equipment_certificate_scan
        if template == T.equipment_certificates
        else AttachmentOwner.personnel_cert_scan
    )
    smap: dict[str, str] = {}
    n = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = info.filename.rsplit("/", 1)[-1]
        stem, dot, ext = base.rpartition(".")
        ctype = SCAN_EXT.get(f".{ext.lower()}") if dot else None
        if not ctype or not stem:
            continue
        content = zf.read(info)
        a = attachments.store(db, owner, b.id, b.project_id, base, content, ctype, p.user.id)
        smap[stem.upper()] = str(a.id)
        n += 1
    b.scans_count = n
    b.scan_map = smap


def list_batches(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: CertImportStatus | None = None,
    template: CertImportTemplate | None = None,
) -> CertImportPage:
    project = _require_view(db, p, project_id)
    stmt = select(CertImportBatch).where(CertImportBatch.project_id == project.id)
    if not cc.is_hse(p, project.id):
        stmt = stmt.where(CertImportBatch.uploaded_by_user_id == p.user.id)
    if status is not None:
        if status == CertImportStatus.expired:
            stmt = stmt.where(
                (CertImportBatch.status == CertImportStatus.expired)
                | (
                    (CertImportBatch.status == CertImportStatus.validated)
                    & (CertImportBatch.expires_at <= now())
                )
            )
        else:
            stmt = stmt.where(CertImportBatch.status == status)
            if status == CertImportStatus.validated:
                stmt = stmt.where(CertImportBatch.expires_at > now())
    if template is not None:
        stmt = stmt.where(CertImportBatch.template == template)
    rows, total = paginate(db, stmt.order_by(CertImportBatch.created_at.desc()), page, page_size)
    refs = Refs(db).load(users=[b.uploaded_by_user_id for b in rows])
    return CertImportPage(
        items=[
            CertImportSummary(
                id=b.id,
                template=b.template,
                source=b.source,
                file_name=b.file_name,
                status=_status(b),
                counts=CertImportCounts(**{**_zero_counts(), **(b.counts or {})}),
                uploaded_by=refs.user(b.uploaded_by_user_id) or cc.UNKNOWN_USER,
                created_at=b.created_at,
                committed_at=b.committed_at,
            )
            for b in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _require_view(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.cert_import) is None:
        raise forbidden_error()
    return project


def get_batch(db: Session, p: Principal, batch_id: uuid.UUID) -> CertImportBatch:
    b = db.get(CertImportBatch, batch_id)
    if b is None:
        raise not_found("Import")
    _require_view(db, p, b.project_id)
    if b.uploaded_by_user_id != p.user.id and not cc.is_hse(p, b.project_id):
        raise not_found("Import")
    return b


def get(db: Session, p: Principal, batch_id: uuid.UUID, include_ok: bool = False) -> CertImportRead:
    return to_read(db, get_batch(db, p, batch_id), include_ok)


def _cleanup(db: Session, b: CertImportBatch, used: set[str]) -> None:
    """IM-4: ID data cleared; unused scans deleted."""
    b.rows = []
    for aid in (b.scan_map or {}).values():
        if aid not in used:
            a = db.get(Attachment, uuid.UUID(aid))
            if a is not None:
                attachments.erase(db, a)
    b.scan_map = {}


def discard(db: Session, p: Principal, batch_id: uuid.UUID) -> CertImportRead:
    b = get_batch(db, p, batch_id)
    cc.require(p, b.project_id, C.cert_import)
    if b.status != CertImportStatus.validated:
        raise ApiError(
            409, ErrorCode.IMPORT_NOT_VALIDATED, "This import is closed.", "هذا الاستيراد مغلق."
        )
    b.status = CertImportStatus.discarded
    _cleanup(db, b, set())
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.cert_import_batch,
        b,
        b.project_id,
        details={"to": "discarded"},
        after={"status": "discarded"},
    )
    return to_read(db, b)


def expiry_job(db: Session, at: datetime | None = None) -> int:
    at = at or now()
    n = 0
    for b in db.scalars(
        select(CertImportBatch).where(
            CertImportBatch.status == CertImportStatus.validated, CertImportBatch.expires_at <= at
        )
    ):
        b.status = CertImportStatus.expired
        _cleanup(db, b, set())
        n += 1
    db.flush()
    return n


# ---- commit ----


def commit(db: Session, p: Principal, batch_id: uuid.UUID) -> CertImportRead:
    b = get_batch(db, p, batch_id)
    cc.require(p, b.project_id, C.cert_import)
    if b.uploaded_by_user_id != p.user.id and not p.is_manager:
        raise forbidden_error("Only the uploader may commit this batch.")
    if b.status != CertImportStatus.validated:
        raise ApiError(
            409, ErrorCode.IMPORT_NOT_VALIDATED, "This import is closed.", "هذا الاستيراد مغلق."
        )
    if b.expires_at <= now():
        b.status = CertImportStatus.expired
        _cleanup(db, b, set())
        db.flush()
        db.commit()
        raise ApiError(
            409,
            ErrorCode.IMPORT_EXPIRED,
            "The dry run is older than 60 minutes — upload again.",
            "مضى على التحقق أكثر من 60 دقيقة — أعد الرفع.",
        )
    rows = validate(db, p, b, [dict(r) for r in b.rows])
    valid = [r for r in rows if r["status"] != ImportRowStatus.error.value]
    if not valid:
        b.report, b.counts = _report(rows), _counts(b, rows)
        raise ApiError(409, ErrorCode.IMPORT_HAS_ERRORS, "No row is valid.", "لا يوجد سطر صالح.")
    source = (
        CertSource.tpi_register_file
        if b.source == CertImportSource.tpi_register_file
        else CertSource.import_
    )
    created: list[uuid.UUID] = []
    used: set[str] = set()
    left_draft = items_created = 0
    at = now()
    if b.template == T.equipment_certificates:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in valid:
            groups[((r.get("tpi_code") or "").upper(), (r.get("cert_no") or "").upper())].append(r)
        for (_tc, cno), grp in groups.items():
            lines = []
            for r in grp:
                if r.get("action") == "create_item_and_certificate":
                    r["equipment_id"] = str(_create_item(db, p, b, r))
                    items_created += 1
                lines.append(_line(r))
            first = grp[0]
            t = _tpi(db, first["tpi_code"])
            assert t is not None  # noqa: S101
            scan = (b.scan_map or {}).get(cno)
            body = EquipmentCertificateCreate(
                tpi_id=t.id,
                cert_no=first["cert_no"],
                inspection_type=CertInspectionType(first["inspection_type"]),
                inspected_on=date.fromisoformat(first["inspected_on"]),
                issued_on=date.fromisoformat(first["issued_on"]),
                printed_next_due=date.fromisoformat(first["printed_next_due"])
                if first.get("printed_next_due")
                else None,
                inspector_name=first.get("inspector_name") or f"{t.tpi_code} inspector",
                lines=lines,
            )
            c = ecs.new_row(db, p, b.project_id, body, source=source, batch_id=b.id)
            if scan:
                used.add(scan)
                a = db.get(Attachment, uuid.UUID(scan))
                if a is not None:
                    a.owner_id = c.id
                c.scan_attachment_id = uuid.UUID(scan)
                ecs.submit(db, p, c, at)
            else:
                left_draft += 1
            if source == CertSource.tpi_register_file:
                owners = [db.get(EquipmentItem, ln.equipment_id) for ln in ecs.lines_of(db, c.id)]
                _register_verification(
                    db, p, b, c, CertKind.equipment, [o.owner_contractor_id for o in owners if o]
                )
            created.append(c.id)
    else:
        for r in valid:
            w = db.get(Worker, uuid.UUID(r["worker_id"]))
            assert w is not None  # noqa: S101
            t = _tpi(db, r["tpi_code"])
            assert t is not None  # noqa: S101
            cno = (r.get("cert_no") or "").upper()
            front = (b.scan_map or {}).get(cno) or (b.scan_map or {}).get(f"{cno}_FRONT")
            back = (b.scan_map or {}).get(f"{cno}_BACK")
            data = {
                "cert_type": r["cert_type"],
                "tpi_id": t.id,
                "cert_no": r["cert_no"],
                "issued_on": date.fromisoformat(r["issued_on"]),
                "printed_expiry": date.fromisoformat(r["printed_expiry"])
                if r.get("printed_expiry")
                else None,
                "scope_categories": r.get("scope_list") or [],
                "max_capacity_t": Decimal(r["max_capacity_t"]) if r.get("max_capacity_t") else None,
                "level": r.get("level") or None,
                "limitations": r.get("limitations_list") or [],
                "medical_restriction_on_card": False,
                "name_as_printed": r.get("name_as_printed") or w.full_name_en,
                "assessment": None,
                "scan_front_attachment_id": uuid.UUID(front) if front else None,
                "scan_back_attachment_id": uuid.UUID(back) if back else None,
                "tpi_verification_url": None,
            }
            pc = pcs.new_row(
                db,
                p,
                b.project_id,
                w,
                data,
                IdMatchResult(r["id_match"]),
                NameMatch(r["name_match"]),
                source=source,
                batch_id=b.id,
            )
            for aid in (front, back):
                if aid:
                    used.add(aid)
                    a = db.get(Attachment, uuid.UUID(aid))
                    if a is not None:
                        a.owner_id = pc.id
            if front:
                pcs.submit(db, p, pc, at)
            else:
                left_draft += 1
            if source == CertSource.tpi_register_file:
                dep = pcs.deployment(db, w.id, b.project_id)
                eng = (
                    db.get(ProjectEngagement, dep.engagement_id)
                    if dep and dep.engagement_id
                    else None
                )
                _register_verification(
                    db, p, b, pc, CertKind.personnel, [eng.contractor_id if eng else None]
                )
            created.append(pc.id)
    b.status = CertImportStatus.committed
    b.committed_at = at
    b.committed_certificate_ids = created
    b.report = _report(rows)
    b.counts = {
        **_counts(b, rows),
        "certificates_created": len(created),
        "certificates_left_draft": left_draft,
        "items_created": items_created,
    }
    _cleanup(db, b, used)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.cert_import_batch,
        b,
        b.project_id,
        details={"to": "committed", "certificates": len(created)},
        after={"status": "committed"},
    )
    _notify_reps(db, b, len(created))
    return to_read(db, b)


def _notify_reps(db: Session, b: CertImportBatch, n: int) -> None:
    alerts.send(
        db,
        alerts.officers(db, b.project_id),
        NotificationKind.cert_import_update,
        f"Certificate import committed: {n} certificate(s) for review",
        f"اعتمد استيراد الشهادات: {n} شهادة للمراجعة",
        EntityType.cert_import_batch,
        b.id,
        b.project_id,
    )


def _line(r: dict[str, Any]) -> CertLineInput:
    lt = None
    if r.get("load_test_pct"):
        lt = {"performed": True, "percent_of_swl": r["load_test_pct"], "test_weight_t": None}
    defects = [
        {"category": DefectCategory(x["category"]), "description_en": x["description_en"]}
        for x in _parse_defects(r.get("defects")) or []
    ]
    return CertLineInput.model_validate(
        {
            "equipment_id": r["equipment_id"],
            "serial_as_printed": r.get("serial_no") or "",
            "result": LineResult(r["result"]),
            "swl_t": r.get("swl_t"),
            "load_test": lt,
            "colour_code": r.get("colour_code"),
            "limitations": _parse_lims(r.get("limitations")) or [],
            "defects": defects,
        }
    )


def _create_item(db: Session, p: Principal, b: CertImportBatch, r: dict[str, Any]) -> uuid.UUID:
    """IM-2 create_items: Awaiting Certificate item + Planned deployment (HSE Officer only)."""
    from app.services.cert import deployments as dsvc  # noqa: PLC0415
    from app.services.cert import equipment as esvc  # noqa: PLC0415

    eng = _contractor(db, b.project_id, r.get("contractor_code"))
    assert eng is not None  # noqa: S101
    seq, no = esvc.next_no(db)
    item = EquipmentItem(
        id=uuid.uuid4(),
        seq=seq,
        equipment_no=no,
        category=EquipmentCertCategory(r["category"]),
        manufacturer=r["manufacturer"],
        manufacturer_norm=cc.manufacturer_norm(r["manufacturer"]),
        model=r.get("model") or "—",
        serial_no=r["serial_no"],
        serial_norm=cc.serial_norm(r["serial_no"]),
        year_of_manufacture=today().year,
        owner_contractor_id=eng.contractor_id,
        rated_capacity_t=Decimal(r["swl_t"]) if r.get("swl_t") else None,
        safety_devices=[],
        documents=[],
        service_status=ServiceStatus.awaiting_certificate,
    )
    cc.stamp(item, p, create=True)
    db.add(item)
    db.flush()
    code = cc.project_code(db, b.project_id)
    n = (
        db.scalar(
            select(func.count())
            .select_from(EquipmentDeployment)
            .where(EquipmentDeployment.project_id == b.project_id)
        )
        or 0
    ) + 1
    dep = EquipmentDeployment(
        id=uuid.uuid4(),
        equipment_id=item.id,
        project_id=b.project_id,
        engagement_id=eng.id,
        deployment_no=f"EQD-{code}-{n:04d}",
        tag=r["tag"].upper(),
        site_ids=list(eng.site_ids or [])[:1],
        status=EquipmentDeploymentStatus.planned,
    )
    cc.stamp(dep, p, create=True)
    db.add(dep)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.create,
        EntityType.equipment_item,
        item,
        b.project_id,
        details={"import": str(b.id)},
    )
    _ = dsvc
    return item.id


def _register_verification(
    db: Session,
    p: Principal,
    b: CertImportBatch,
    cert: Any,
    kind: CertKind,
    holders: list[uuid.UUID | None],
) -> None:
    """IM-6: verification record method tpi_register_file, outcome confirmed, reference =
    evidence sha256, performed_by = importer (VF-2 still applies)."""
    emp = p.user.employer_contractor_id
    if emp is not None and emp in {h for h in holders if h}:
        return
    t = db.get(Tpi, b.tpi_id) if b.tpi_id else None
    at = now()
    v = CertVerification(
        id=uuid.uuid4(),
        cert_kind=kind,
        cert_id=cert.id,
        project_id=cert.project_id,
        tpi_id=cert.tpi_id,
        method=CertVerificationMethod.tpi_register_file,
        channel_used=(t.verification_domains or [t.tpi_code])[0] if t else "register",
        outcome=VerificationOutcome.confirmed,
        differences=[],
        reference=(b.evidence_sha256 or "")[:100],
        performed_by_user_id=p.user.id,
        performed_at=at,
        counts_as_verification=True,
        verification_status_after=VerificationStatus.verified,
    )
    db.add(v)
    cert.verification_status = VerificationStatus.verified
    cert.verified_at = at
    db.flush()


# ---- template ----


def template(t: CertImportTemplate, fmt_: ExportFormat, headers: str) -> tuple[bytes, str, str]:
    cols = _cols(t)
    names = [ar if headers == "ar" else k for k, ar, _ in cols]
    if t == T.equipment_certificates:
        ex = {
            "project_code": "ANIA-EXP",
            "tag": "SH-MEWP-12",
            "category": "mewp",
            "manufacturer": "TestLift",
            "serial_no": "TESTSN-MEWP-0012",
            "tpi_code": "AICC",
            "cert_no": "AICC-EQ-TEST-26-0902",
            "inspection_type": "periodic",
            "inspected_on": "2026-09-02",
            "issued_on": "2026-09-02",
            "printed_next_due": "2027-09-01",
            "result": "pass",
            "swl_t": "0.230",
            "limitations": "",
            "defects": "",
            "inspector_name": "Eng. Test Inspector (fake)",
        }
    else:
        ex = {
            "worker_no": "WKR-000019",
            "cert_type": "RIGGER",
            "tpi_code": "AICC",
            "cert_no": "AICC-RG-TEST-24-0001",
            "issued_on": "2024-04-01",
            "printed_expiry": "2027-03-31",
            "level": "2",
            "name_as_printed": "Test Worker (fake)",
            "id_on_card": "",
        }
    example = [ex.get(k, "") for k, _ar, _r in cols]
    return export_svc.encode(names, [example], fmt_, f"certificate-import-{t.value}-{headers}")


def upload(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    file: UploadFile,
    template_: CertImportTemplate,
    source: CertImportSource,
    create_items: bool,
    tpi_id: uuid.UUID | None,
    scans_zip: UploadFile | None,
    evidence_file: UploadFile | None,
) -> CertImportRead:
    main = _read_upload(file, MAX_BYTES)
    assert main is not None  # noqa: S101
    scans = _read_upload(scans_zip, MAX_ZIP)
    evidence = _read_upload(evidence_file, 10 * 1024 * 1024)
    return dry_run(
        db,
        p,
        project_id,
        main[0],
        main[1],
        template_,
        source,
        create_items,
        tpi_id,
        scans,
        evidence,
    )
