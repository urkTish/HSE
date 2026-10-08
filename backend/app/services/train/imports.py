"""Training imports: CSV/XLSX dry-run → commit the valid rows (spec 5-training §3.13, §4.8,
IM5-1…IM5-7).

ID numbers are used only for the blind-index lookup and the TR-6 match: kept encrypted per row
until commit / discard / expiry and never echoed (masked, WK-4). Committed training_records rows
become Submitted (Draft without a scan, W03), never Accepted (IM5-5); session_attendance rows
update attendance and assessment of one Delivered session (Close stays separate, IM5-3)."""

import hashlib
import io
import re
import uuid
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import WorkerIdType, WorkerStatus
from app.core.cert_enums import IdMatchResult, NameMatch
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, ExportFormat, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner, ImportRowStatus
from app.core.train_enums import (
    NominationStatus,
    PracticalResult,
    SessionStatus,
    TrainingImportCode,
    TrainingImportSource,
    TrainingImportStatus,
    TrainingImportTemplate,
    TrainingRecordSource,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
)
from app.models import (
    Attachment,
    Project,
    TrainingImportBatch,
    TrainingNomination,
    TrainingProvider,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from app.schemas.training_imports import (
    TrainingImportCounts,
    TrainingImportIssue,
    TrainingImportPage,
    TrainingImportRead,
    TrainingImportRowReport,
    TrainingImportSummary,
)
from app.services import attachments
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.cert import imports as cimp
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.train import common, providers, records
from app.services.train import sessions as ssvc
from app.services.workforce_import import _norm_header, _read_table, file_invalid

C = Capability
IC = TrainingImportCode
T = TrainingImportTemplate
ST = TrainingImportStatus
NS = NominationStatus
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_ZIP = 200 * 1024 * 1024
TTL = timedelta(minutes=60)

# (key, Arabic header, required)
REC_COLS: list[tuple[str, str, bool]] = [
    ("worker_no", "رقم العامل", False),
    ("id_type", "نوع الهوية", False),
    ("id_number", "رقم الهوية", False),
    ("passport_country", "بلد الجواز", False),
    ("course_code", "رمز الدورة", True),
    ("provider_code", "رمز الجهة", True),
    ("certificate_no", "رقم الشهادة", True),
    ("completed_on", "تاريخ الإتمام", True),
    ("printed_expiry", "تاريخ الانتهاء", False),
    ("theory_score_pct", "درجة الاختبار النظري", False),
    ("practical_result", "نتيجة التقييم العملي", False),
    ("hours", "الساعات", False),
    ("project_sponsored", "بتمويل المشروع", False),
    ("name_as_printed", "الاسم كما في الشهادة", True),
    ("id_on_card", "الهوية في الشهادة", False),
]
ATT_COLS: list[tuple[str, str, bool]] = [
    ("worker_no", "رقم العامل", True),
    ("day_no", "رقم اليوم", True),
    ("minutes", "الدقائق", True),
    ("theory_score_pct", "درجة الاختبار النظري", False),
    ("practical_result", "نتيجة التقييم العملي", False),
]

MESSAGES: dict[IC, tuple[str, str]] = {
    IC.E01: ("Worker not found or anonymised.", "العامل غير موجود أو مجهّل."),
    IC.E02: (
        "Course unknown, inactive or an induction (recorded in Phase 2).",
        "الدورة غير معروفة أو غير نشطة أو تعريف (يسجل في وحدة التعريف).",
    ),
    IC.E03: (
        "Provider unknown or not acceptable on the completion date.",
        "جهة التدريب غير معروفة أو غير مقبولة في تاريخ الإتمام.",
    ),
    IC.E04: ("Duplicate certificate.", "شهادة مكررة."),
    IC.E05: (
        "Completion date in the future or training already expired.",
        "تاريخ الإتمام في المستقبل أو التدريب منتهٍ.",
    ),
    IC.E06: (
        "Score, practical result or hours invalid.",
        "الدرجة أو النتيجة العملية أو الساعات غير صحيحة.",
    ),
    IC.E07: ("ID on the certificate does not match the worker.", "الهوية لا تطابق العامل."),
    IC.E08: ("Row outside your scope.", "السطر خارج نطاق صلاحيتك."),
    IC.E09: (
        "Refresher not eligible: the full course is required.",
        "التجديد غير مؤهل: يلزم حضور الدورة الكاملة.",
    ),
    IC.E10: (
        "Worker not nominated, day not a session day, or minutes above the day's net minutes.",
        "العامل غير مرشح أو اليوم ليس من أيام الجلسة أو الدقائق أكثر من المسموح.",
    ),
    IC.E11: (
        "Prerequisite not in force on the completion date.",
        "المتطلب السابق غير ساري في تاريخ الإتمام.",
    ),
    IC.E12: ("Unparseable date or number.", "تاريخ أو رقم غير قابل للقراءة."),
    IC.W01: (
        "Printed expiry beyond the course validity (valid_until shortened).",
        "تاريخ الانتهاء المطبوع يتجاوز صلاحية الدورة (ستُقصّر الصلاحية).",
    ),
    IC.W02: (
        "Name on the certificate matches only partly or not at all.",
        "الاسم في الشهادة مطابق جزئياً أو غير مطابق.",
    ),
    IC.W03: (
        "No scan in the zip for this certificate (stays Draft).",
        "لا توجد نسخة في الملف المضغوط (تبقى مسودة).",
    ),
    IC.W04: (
        "Provider accreditation expires within 30 days.",
        "ينتهي اعتماد جهة التدريب خلال 30 يوماً.",
    ),
    IC.W05: (
        "The same file was already committed on this project.",
        "تم اعتماد الملف نفسه سابقاً في هذا المشروع.",
    ),
    IC.W06: ("Training expires within 30 days.", "ينتهي التدريب خلال 30 يوماً."),
}
ERRORS = {c.value for c in IC if c.value.startswith("E")}
# records.check() error codes → IM5-7 codes
CHECK_CODES: dict[str, IC] = {
    ErrorCode.INDUCTION_OWNED_BY_PHASE2.value: IC.E02,
    ErrorCode.NOT_FOUND.value: IC.E03,
    ErrorCode.PROVIDER_NOT_ACCEPTABLE.value: IC.E03,
    ErrorCode.CERT_EXISTS.value: IC.E04,
    ErrorCode.CERT_NO_REUSED.value: IC.E04,
    ErrorCode.RECORD_ALREADY_EXPIRED.value: IC.E05,
    ErrorCode.REFRESHER_NOT_ELIGIBLE.value: IC.E09,
}
FIELD_CODES: dict[str, IC] = {
    "course_code": IC.E02,
    "completed_on": IC.E05,
    "printed_expiry": IC.E05,
    "hours": IC.E06,
    "sponsoring_project_id": IC.E06,
}


def issue(code: IC, column: str | None = None, **meta: str) -> dict[str, Any]:
    en, ar = MESSAGES[code]
    return {"code": code.value, "column": column, "message_en": en, "message_ar": ar, "meta": meta}


def _err(row: dict[str, Any], code: IC, col: str | None = None, **meta: str) -> None:
    if not any(i["code"] == code.value and i.get("column") == col for i in row["issues"]):
        row["issues"].append(issue(code, col, **meta))


def _cols(t: TrainingImportTemplate) -> list[tuple[str, str, bool]]:
    return REC_COLS if t == T.training_records else ATT_COLS


def _hmap(t: TrainingImportTemplate) -> dict[str, str]:
    out = {}
    for k, ar, _ in _cols(t):
        out[k] = k
        out[_norm_header(ar)] = k
        out[ar] = k
    return out


# ---- parse (IM5-1) ------------------------------------------------------------------------------


def parse(t: TrainingImportTemplate, name: str, content: bytes) -> list[dict[str, Any]]:
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
    if t == T.training_records and "worker_no" not in headers and "id_number" not in headers:
        missing.append("worker_no")
    if missing:
        raise ApiError(
            422,
            ErrorCode.IMPORT_FILE_INVALID,
            "Missing required column(s): " + ", ".join(missing) + " (E12).",
            "أعمدة مطلوبة مفقودة: " + "، ".join(missing),
            meta={"code": IC.E12.value, "missing": ",".join(missing)},
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
            if k in ("completed_on", "printed_expiry"):
                d, ok = cimp._date(v)
                if not ok:
                    row["issues"].append(issue(IC.E12, k))
                row[k] = d.isoformat() if d else None
            elif k in ("theory_score_pct", "hours"):
                n, ok = cimp._dec(v)
                if not ok:
                    row["issues"].append(issue(IC.E12, k))
                row[k] = str(n) if n is not None else None
            elif k in ("day_no", "minutes"):
                n, ok = cimp._dec(v)
                if not ok or (n is not None and n != n.to_integral_value()):
                    row["issues"].append(issue(IC.E12, k))
                    n = None
                row[k] = int(n) if n is not None else None
            elif k == "id_number":
                s = cimp._s(v)
                row["id_number_enc"] = crypto.encrypt(s).hex() if s else None
            elif k == "id_on_card":
                s = cimp._s(v)
                if s and s.lower() not in ("same_as_lookup", "same"):
                    row["id_on_card_enc"] = crypto.encrypt(s).hex()
                    row["id_on_card"] = "number"
                else:
                    row["id_on_card"] = "same_as_lookup" if s else None
            else:
                row[k] = cimp._s(v)
        rows.append(row)
    return rows


# ---- validation (IM5-7) -------------------------------------------------------------------------


def _provider(db: Session, code: str | None) -> TrainingProvider | None:
    if not code:
        return None
    return db.scalar(
        select(TrainingProvider).where(func.upper(TrainingProvider.provider_code) == code.upper())
    )


def _acc_expiring(db: Session, pv: TrainingProvider, d0: date) -> bool:
    accs = [a for a in providers.accreditations(db, pv.id) if providers.counts_on(a, d0)]
    return bool(accs) and min(a.valid_until for a in accs) <= d0 + timedelta(days=30)


def _w05(db: Session, b: TrainingImportBatch, r: dict[str, Any]) -> None:
    if db.scalar(
        select(TrainingImportBatch.id).where(
            TrainingImportBatch.project_id == b.project_id,
            TrainingImportBatch.file_sha256 == b.file_sha256,
            TrainingImportBatch.status == ST.committed,
            TrainingImportBatch.id != b.id,
        )
    ):
        _err(r, IC.W05)


def _finish(r: dict[str, Any]) -> None:
    codes = list(dict.fromkeys(i["code"] for i in r["issues"]))
    r["codes"] = codes
    if any(c in ERRORS for c in codes):
        r["status"] = ImportRowStatus.error.value
    elif codes:
        r["status"] = ImportRowStatus.warning.value
    else:
        r["status"] = ImportRowStatus.ok.value


def _scores(r: dict[str, Any], course: Any) -> None:
    sc = r.get("theory_score_pct")
    if sc is not None:
        v = Decimal(sc)
        if v < 0 or v > 100 or (course is not None and not course.theory_required):
            _err(r, IC.E06, "theory_score_pct")
    pr = (r.get("practical_result") or "").lower() or None
    r["practical_result"] = pr
    if pr is not None and (
        pr not in {x.value for x in PracticalResult}
        or (course is not None and not course.practical_required)
    ):
        _err(r, IC.E06, "practical_result")


def _worker(db: Session, r: dict[str, Any]) -> tuple[Worker | None, str | None]:
    w: Worker | None = None
    if r.get("worker_no"):
        w = db.scalar(select(Worker).where(Worker.worker_no == r["worker_no"].upper()))
    number = cimp._dec_id(r.get("id_number_enc"))
    if w is None and number:
        w, r["id_masked"] = cimp._worker_by_id(
            db, r.get("id_type"), number, r.get("passport_country")
        )
    elif number and r.get("id_type") in WorkerIdType.__members__:
        r["id_masked"] = acommon.mask_worker_id(WorkerIdType(r["id_type"]), number)
    if w is not None and w.status == WorkerStatus.anonymised:
        w = None
    return w, number


def _validate_records(
    db: Session, p: Principal, b: TrainingImportBatch, rows: list[dict[str, Any]]
) -> None:
    g = p.grant(b.project_id, C.training_import)
    d0 = today()
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        r["issues"] = [i for i in r["issues"] if i["code"] == IC.E12.value]
        w, number = _worker(db, r)
        dep = None
        if w is None:
            _err(r, IC.E01, "worker_no")
        else:
            r["worker_no"] = w.worker_no
            r["worker_id"] = str(w.id)
            dep = common.deployment(db, w.id, b.project_id)
            if dep is None or not common.covers_dep(g, dep):
                _err(r, IC.E08, "worker_no")
        code = (r.get("course_code") or "").upper()
        r["course_code"] = code
        c = common.course(db, code)
        if c is None or not c.active:
            _err(r, IC.E02, "course_code")
            c = None
        pv = _provider(db, r.get("provider_code"))
        if pv is None:
            _err(r, IC.E03, "provider_code")
        else:
            r["provider_code"] = pv.provider_code
        _scores(r, c)
        sponsored = (r.get("project_sponsored") or "").strip().upper() in ("Y", "YES", "TRUE", "1")
        r["project_sponsored"] = sponsored
        if sponsored and r.get("hours") is None:
            _err(r, IC.E06, "hours")
        key = (r.get("provider_code") or "", code, (r.get("certificate_no") or "").upper())
        if key in seen:
            _err(r, IC.E04, "certificate_no")
        seen.add(key)
        completed = date.fromisoformat(r["completed_on"]) if r.get("completed_on") else None
        if completed is not None and completed > d0:
            _err(r, IC.E05, "completed_on")
        if w is not None and c is not None and pv is not None and completed is not None:
            data = _data(r, pv, b.project_id)
            ch = records.check(db, b.project_id, w, data)
            for _st, ecode, _en, _ar, fld, meta in ch.errors:
                ic = CHECK_CODES.get(ecode) or FIELD_CODES.get(fld or "") or IC.E05
                m = {k: str(v) for k, v in (meta or {}).items() if v is not None}
                _err(r, ic, fld if ic != IC.E03 else "provider_code", **m)
            r["name_match"] = ch.name_match.value
            for wn in ch.warnings:
                if wn.code in ("W01", "W02"):
                    _err(r, IC(wn.code), wn.field)
            vu = ch.validity[0] if ch.validity else None
            r["valid_until"] = vu.isoformat() if vu else None
            if vu is not None and d0 <= vu <= d0 + timedelta(days=30):
                _err(r, IC.W06, "printed_expiry")
            if pv is not None and _acc_expiring(db, pv, d0):
                _err(r, IC.W04, "provider_code")
            tmp = TrainingRecord(
                id=uuid.uuid4(),
                worker_id=w.id,
                completed_on=completed,
                prerequisite_evidenced=False,
            )
            missing = records.prerequisites_missing(db, tmp, c, b.project_id)
            if missing:
                _err(r, IC.E11, "course_code", missing=",".join(missing))
            idm = cimp._id_match(db, w, r, number)
            if idm is None:
                _err(r, IC.E07, "id_on_card")
            r["id_match"] = idm
        if b.scans_zip_name is not None:
            r["scan_found"] = (r.get("certificate_no") or "").upper() in {
                k.upper() for k in (b.scan_map or {})
            }
            if not r["scan_found"]:
                _err(r, IC.W03, "certificate_no")
        _w05(db, b, r)
        _finish(r)


def _data(r: dict[str, Any], pv: TrainingProvider, project_id: uuid.UUID) -> dict[str, Any]:
    sponsored = bool(r.get("project_sponsored"))
    return {
        "course_code": r["course_code"],
        "provider_id": pv.id,
        "certificate_no": (r.get("certificate_no") or "").strip(),
        "completed_on": date.fromisoformat(r["completed_on"]),
        "printed_expiry": date.fromisoformat(r["printed_expiry"])
        if r.get("printed_expiry")
        else None,
        "theory_score_pct": Decimal(r["theory_score_pct"])
        if r.get("theory_score_pct") is not None
        else None,
        "practical_result": PracticalResult(r["practical_result"])
        if r.get("practical_result")
        else None,
        "hours": Decimal(r["hours"]) if r.get("hours") is not None else None,
        "project_sponsored": sponsored,
        "sponsoring_project_id": project_id if sponsored else None,
        "name_as_printed": r.get("name_as_printed") or "",
        "prerequisite_evidenced": False,
    }


def _validate_attendance(
    db: Session, p: Principal, b: TrainingImportBatch, rows: list[dict[str, Any]]
) -> None:
    s = db.get(TrainingSession, b.session_id) if b.session_id else None
    assert s is not None  # noqa: S101
    g = p.grant(b.project_id, C.training_import)
    trainer = p.user.id in ssvc.trainer_user_ids(db, s)
    c = common.course(db, s.course_code)
    noms: dict[str, TrainingNomination] = {}
    for n in ssvc.nominations(db, s):
        if n.status == NS.withdrawn:
            continue
        w = db.get(Worker, n.worker_id)
        if w is not None:
            noms[w.worker_no] = n
    seen: set[tuple[str, int]] = set()
    for r in rows:
        r["issues"] = [i for i in r["issues"] if i["code"] == IC.E12.value]
        wno = (r.get("worker_no") or "").upper()
        r["worker_no"] = wno
        nom = noms.get(wno)
        if nom is None:
            exists = db.scalar(select(Worker.id).where(Worker.worker_no == wno))
            _err(r, IC.E10 if exists else IC.E01, "worker_no")
        else:
            r["nomination_id"] = str(nom.id)
            dep = common.deployment(db, nom.worker_id, b.project_id)
            if not trainer and not common.covers_dep(g, dep):
                _err(r, IC.E08, "worker_no")
        day_no, mins = r.get("day_no"), r.get("minutes")
        if day_no is not None:
            if day_no < 1 or day_no > len(s.days or []):
                _err(r, IC.E10, "day_no")
            elif mins is not None and (mins < 0 or mins > ssvc.net(s.days[day_no - 1])):
                _err(r, IC.E10, "minutes")
            if (wno, day_no) in seen:
                _err(r, IC.E10, "day_no")
            seen.add((wno, day_no))
        _scores(r, c)
        _w05(db, b, r)
        _finish(r)


def validate(
    db: Session, p: Principal, b: TrainingImportBatch, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if b.template == T.training_records:
        _validate_records(db, p, b, rows)
    else:
        _validate_attendance(db, p, b, rows)
    return rows


# ---- counts / read ------------------------------------------------------------------------------


def _counts(b: TrainingImportBatch, rows: list[dict[str, Any]]) -> dict[str, int]:
    old = b.counts or {}
    return {
        "rows_total": len(rows),
        "rows_ok": sum(1 for r in rows if r["status"] == ImportRowStatus.ok.value),
        "rows_warning": sum(1 for r in rows if r["status"] == ImportRowStatus.warning.value),
        "rows_error": sum(1 for r in rows if r["status"] == ImportRowStatus.error.value),
        "records_created": old.get("records_created", 0),
        "records_left_draft": old.get("records_left_draft", 0),
        "attendance_rows_applied": old.get("attendance_rows_applied", 0),
    }


def _report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "worker_no", "id_masked", "course_code", "provider_code", "certificate_no", "day_no",
        "scan_found",
    )  # fmt: skip
    return [
        {
            "row_no": r["row_no"],
            "status": r["status"],
            "codes": r.get("codes", []),
            "issues": r["issues"],
            **{k: r.get(k) for k in keys},
        }
        for r in rows
    ]


def _issue_read(i: dict[str, Any]) -> TrainingImportIssue:
    return TrainingImportIssue(
        code=IC(i["code"]),
        column=i.get("column"),
        message_en=i["message_en"],
        message_ar=i["message_ar"],
        meta={k: str(v) for k, v in (i.get("meta") or {}).items()},
    )


def _zero_counts() -> dict[str, int]:
    return dict.fromkeys(TrainingImportCounts.model_fields, 0)


def _status(b: TrainingImportBatch) -> TrainingImportStatus:
    if b.status == ST.validated and b.expires_at <= now():
        return ST.expired
    return b.status


def to_read(db: Session, b: TrainingImportBatch, include_ok: bool = False) -> TrainingImportRead:
    refs = Refs(db).load(users=[b.uploaded_by_user_id])
    pv = db.get(TrainingProvider, b.provider_id) if b.provider_id else None
    rep = [r for r in b.report or [] if include_ok or r["status"] != ImportRowStatus.ok.value]
    rep.sort(key=lambda r: ({"error": 0, "warning": 1, "ok": 2}[r["status"]], r["row_no"]))
    return TrainingImportRead(
        id=b.id,
        project_id=b.project_id,
        template=b.template,
        source=b.source,
        session_id=b.session_id,
        provider_code=pv.provider_code if pv else None,
        file_name=b.file_name,
        file_sha256=b.file_sha256,
        file_size=b.file_size,
        sensitive=b.sensitive,
        scans_zip_name=b.scans_zip_name,
        scans_count=b.scans_count,
        evidence_file_name=b.evidence_file_name,
        evidence_sha256=b.evidence_sha256,
        status=_status(b),
        counts=TrainingImportCounts(**{**_zero_counts(), **(b.counts or {})}),
        file_issues=[_issue_read(i) for i in b.file_issues or []],
        report=[
            TrainingImportRowReport(
                row_no=r["row_no"],
                status=ImportRowStatus(r["status"]),
                codes=[IC(c) for c in r.get("codes", [])],
                issues=[_issue_read(i) for i in r["issues"]],
                worker_no=r.get("worker_no"),
                id_masked=r.get("id_masked"),
                course_code=r.get("course_code"),
                provider_code=r.get("provider_code"),
                certificate_no=r.get("certificate_no"),
                day_no=r.get("day_no"),
                scan_found=r.get("scan_found"),
            )
            for r in rep
        ],
        uploaded_by=refs.user(b.uploaded_by_user_id) or cc.UNKNOWN_USER,
        created_at=b.created_at,
        expires_at=b.expires_at,
        committed_at=b.committed_at,
        committed_record_ids=list(b.committed_record_ids or [])[:500],
    )


# ---- upload (dry run) ---------------------------------------------------------------------------


def _require(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = common.visible_project(db, p, project_id)
    p.ensure_writer()
    p.require(project.id, C.training_import)
    return project


def _evidence_ok(pv: TrainingProvider, content: bytes) -> bool:
    """IM5-6: the evidence is an email from one of the provider's verification domains."""
    text = content.decode("utf-8", errors="ignore")
    m = re.search(r"^From:.*?@([A-Za-z0-9.-]+)", text, flags=re.MULTILINE | re.IGNORECASE)
    hosts = (
        [m.group(1)]
        if m
        else re.findall(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)[:5]
    )
    return any(records._domain_ok(h.lower(), pv.verification_domains or []) for h in hosts)


def dry_run(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    file_name: str,
    content: bytes,
    template: TrainingImportTemplate,
    source: TrainingImportSource = TrainingImportSource.contractor_file,
    session_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    scans: tuple[str, bytes] | None = None,
    evidence: tuple[str, bytes] | None = None,
) -> TrainingImportRead:
    project = _require(db, p, project_id)
    pv = None
    if source == TrainingImportSource.provider_register_file:
        if not common.is_hse(p, project.id):
            raise ApiError(
                403,
                ErrorCode.IMPORT_SOURCE_NOT_ALLOWED,
                "A provider register file is imported by HSE Officers / Manager only.",
                "يستورد ملف سجل جهة التدريب مسؤولو السلامة فقط.",
            )
        if template != T.training_records:
            raise file_invalid("A provider register file uses the training_records template.")
        pv = db.get(TrainingProvider, provider_id) if provider_id else None
        if pv is None:
            raise not_found("Training provider")
        if evidence is None or not _evidence_ok(pv, evidence[1]):
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_DOMAIN_MISMATCH,
                "The evidence must be an email from one of the provider's verification domains.",
                "يجب أن يكون الدليل بريداً من أحد نطاقات التحقق لجهة التدريب.",
            )
    if template == T.session_attendance:
        s = db.get(TrainingSession, session_id) if session_id else None
        if s is None or s.project_id != project.id:
            raise not_found("Training session")
        ssvc.advance(db, s)
        if s.status != SessionStatus.delivered:
            raise ApiError(
                409,
                ErrorCode.INVALID_TRANSITION,
                "Attendance files are imported for a Delivered session.",
                "يستورد ملف الحضور لجلسة منفذة فقط.",
            )
        ssvc._can_record(db, p, s)
    elif session_id is not None:
        raise file_invalid("session_id is only for the session_attendance template.")
    rows = parse(template, file_name, content)
    sensitive = any(r.get("id_number_enc") or r.get("id_on_card_enc") for r in rows)
    at = now()
    b = TrainingImportBatch(
        id=uuid.uuid4(),
        project_id=project.id,
        template=template,
        source=source,
        session_id=session_id if template == T.session_attendance else None,
        provider_id=pv.id if pv else None,
        file_name=file_name[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        file_size=len(content),
        sensitive=sensitive,
        scans_zip_name=scans[0][:255] if scans else None,
        scans_count=None,
        scan_map={},
        evidence_file_name=evidence[0][:255] if evidence else None,
        evidence_sha256=hashlib.sha256(evidence[1]).hexdigest() if evidence else None,
        status=ST.validated,
        counts={},
        file_issues=[],
        report=[],
        rows=[],
        committed_record_ids=[],
        uploaded_by_user_id=p.user.id,
        created_at=at,
        expires_at=at + TTL,
    )
    db.add(b)
    db.flush()
    if scans is not None and template == T.training_records:
        _store_scans(db, p, b, scans[1])
    rows = validate(db, p, b, rows)
    b.rows = rows
    b.report = _report(rows)
    b.counts = _counts(b, rows)
    db.flush()
    cc.record(
        db, p, AuditAction.create, EntityType.training_import_batch, b, project.id,
        after={"file": b.file_name, "sha256": b.file_sha256, "template": template.value,
               "counts": b.counts},
    )  # fmt: skip
    return to_read(db, b, include_ok=True)


def _store_scans(db: Session, p: Principal, b: TrainingImportBatch, data: bytes) -> None:
    if len(data) > MAX_ZIP:
        raise file_invalid("The scans zip is larger than 200 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise file_invalid("The scans file is not a valid zip.") from exc
    smap: dict[str, str] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = info.filename.rsplit("/", 1)[-1]
        stem, dot, ext = base.rpartition(".")
        ctype = cimp.SCAN_EXT.get(f".{ext.lower()}") if dot else None
        if not ctype or not stem:
            continue
        a = attachments.store(
            db,
            AttachmentOwner.training_record_scan,
            b.id,
            b.project_id,
            base,
            zf.read(info),
            ctype,
            p.user.id,
        )
        smap[stem.upper()] = str(a.id)
    b.scans_count = len(smap)
    b.scan_map = smap


def upload(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    file: UploadFile,
    template_: TrainingImportTemplate,
    source: TrainingImportSource,
    session_id: uuid.UUID | None,
    provider_id: uuid.UUID | None,
    scans_zip: UploadFile | None,
    evidence_file: UploadFile | None,
) -> TrainingImportRead:
    main = cimp._read_upload(file, MAX_BYTES)
    assert main is not None  # noqa: S101
    scans = cimp._read_upload(scans_zip, MAX_ZIP)
    evidence = cimp._read_upload(evidence_file, 10 * 1024 * 1024)
    return dry_run(
        db, p, project_id, main[0], main[1], template_, source, session_id, provider_id, scans,
        evidence,
    )  # fmt: skip


# ---- history / read -----------------------------------------------------------------------------


def _require_view(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = common.visible_project(db, p, project_id)
    if p.grant(project.id, C.training_import) is None:
        raise forbidden_error()
    return project


def list_batches(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: TrainingImportStatus | None = None,
    template: TrainingImportTemplate | None = None,
) -> TrainingImportPage:
    project = _require_view(db, p, project_id)
    B = TrainingImportBatch  # noqa: N806
    stmt = select(B).where(B.project_id == project.id)
    if not common.is_hse(p, project.id):
        stmt = stmt.where(B.uploaded_by_user_id == p.user.id)
    if status == ST.expired:
        stmt = stmt.where(
            (B.status == ST.expired) | ((B.status == ST.validated) & (B.expires_at <= now()))
        )
    elif status is not None:
        stmt = stmt.where(B.status == status)
        if status == ST.validated:
            stmt = stmt.where(B.expires_at > now())
    if template is not None:
        stmt = stmt.where(B.template == template)
    rows, total = paginate(db, stmt.order_by(B.created_at.desc()), page, page_size)
    refs = Refs(db).load(users=[b.uploaded_by_user_id for b in rows])
    return TrainingImportPage(
        items=[
            TrainingImportSummary(
                id=b.id,
                template=b.template,
                source=b.source,
                file_name=b.file_name,
                status=_status(b),
                counts=TrainingImportCounts(**{**_zero_counts(), **(b.counts or {})}),
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


def get_batch(db: Session, p: Principal, batch_id: uuid.UUID) -> TrainingImportBatch:
    b = db.get(TrainingImportBatch, batch_id)
    if b is None:
        raise not_found("Import")
    _require_view(db, p, b.project_id)
    if b.uploaded_by_user_id != p.user.id and not common.is_hse(p, b.project_id):
        raise not_found("Import")
    return b


def get(
    db: Session, p: Principal, batch_id: uuid.UUID, include_ok: bool = False
) -> TrainingImportRead:
    return to_read(db, get_batch(db, p, batch_id), include_ok)


def _cleanup(db: Session, b: TrainingImportBatch, used: set[str]) -> None:
    """IM5-4: the parsed rows (encrypted IDs) are deleted; unused scans erased."""
    b.rows = []
    for aid in (b.scan_map or {}).values():
        if aid not in used:
            a = db.get(Attachment, uuid.UUID(aid))
            if a is not None:
                attachments.erase(db, a)
    b.scan_map = {}


def _closed() -> ApiError:
    return ApiError(
        409, ErrorCode.IMPORT_NOT_VALIDATED, "This import is closed.", "هذا الاستيراد مغلق."
    )


def discard(db: Session, p: Principal, batch_id: uuid.UUID) -> TrainingImportRead:
    b = get_batch(db, p, batch_id)
    p.ensure_writer()
    p.require(b.project_id, C.training_import)
    if b.status != ST.validated:
        raise _closed()
    b.status = ST.discarded
    _cleanup(db, b, set())
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_import_batch, b, b.project_id,
        details={"to": "discarded"}, after={"status": "discarded"},
    )  # fmt: skip
    return to_read(db, b)


def expiry_job(db: Session, at: datetime | None = None) -> int:
    at = at or now()
    n = 0
    for b in db.scalars(
        select(TrainingImportBatch).where(
            TrainingImportBatch.status == ST.validated, TrainingImportBatch.expires_at <= at
        )
    ):
        b.status = ST.expired
        _cleanup(db, b, set())
        n += 1
    db.flush()
    return n


# ---- commit (IM5-5, IM5-6, IM5-3) ---------------------------------------------------------------


def commit(db: Session, p: Principal, batch_id: uuid.UUID) -> TrainingImportRead:
    b = get_batch(db, p, batch_id)
    p.ensure_writer()
    p.require(b.project_id, C.training_import)
    if b.uploaded_by_user_id != p.user.id and not p.is_manager:
        raise forbidden_error("Only the uploader may commit this batch.")
    if b.status != ST.validated:
        raise _closed()
    if b.expires_at <= now():
        b.status = ST.expired
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
    used: set[str] = set()
    created: list[uuid.UUID] = []
    left_draft = applied = 0
    if b.template == T.training_records:
        created, left_draft = _commit_records(db, p, b, valid, used)
    else:
        applied = _commit_attendance(db, p, b, valid)
    b.status = ST.committed
    b.committed_at = now()
    b.committed_record_ids = created
    b.report = _report(rows)
    b.counts = {
        **_counts(b, rows),
        "records_created": len(created),
        "records_left_draft": left_draft,
        "attendance_rows_applied": applied,
    }
    _cleanup(db, b, used)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_import_batch, b, b.project_id,
        details={"to": "committed", "records": len(created), "attendance_rows": applied,
                 "sha256": b.file_sha256},
        after={"status": "committed"},
    )  # fmt: skip
    if created:
        alerts.send(
            db,
            alerts.officers(db, b.project_id),
            NotificationKind.training_import_update,
            f"Training import committed: {len(created)} record(s) for review",
            f"اعتمد استيراد التدريب: {len(created)} سجل للمراجعة",
            EntityType.training_import_batch,
            b.id,
            b.project_id,
        )
    return to_read(db, b)


def _commit_records(
    db: Session,
    p: Principal,
    b: TrainingImportBatch,
    valid: list[dict[str, Any]],
    used: set[str],
) -> tuple[list[uuid.UUID], int]:
    at = now()
    created: list[uuid.UUID] = []
    left_draft = 0
    for r in valid:
        w = db.get(Worker, uuid.UUID(r["worker_id"]))
        pv = _provider(db, r["provider_code"])
        assert w is not None and pv is not None  # noqa: S101
        dep = common.deployment(db, w.id, b.project_id)
        data = _data(r, pv, b.project_id)
        scan = (b.scan_map or {}).get((r.get("certificate_no") or "").upper())
        rec = records.new_external(
            db, p, b.project_id, w, dep, data,
            IdMatchResult(r.get("id_match") or IdMatchResult.not_shown.value),
            NameMatch(r.get("name_match") or NameMatch.none.value),
        )  # fmt: skip
        rec.source = TrainingRecordSource.import_
        rec.import_batch_id = b.id
        if scan:
            used.add(scan)
            a = db.get(Attachment, uuid.UUID(scan))
            if a is not None:
                a.owner_id = rec.id
            rec.scan_attachment_id = uuid.UUID(scan)
            records.submit(db, p, rec, at)
        else:
            left_draft += 1
        db.flush()
        if b.source == TrainingImportSource.provider_register_file:
            _register_verification(db, p, b, pv, rec, dep, at)
        created.append(rec.id)
    return created, left_draft


def _register_verification(
    db: Session,
    p: Principal,
    b: TrainingImportBatch,
    pv: TrainingProvider,
    rec: TrainingRecord,
    dep: Any,
    at: datetime,
) -> None:
    """VR-8: method provider_register_file, outcome confirmed, reference = evidence sha256
    (VR-2: not by an employee of the holder's employer)."""
    emp = p.user.employer_contractor_id
    if emp is not None and dep is not None and dep.engagement_id is not None:
        from app.models import ProjectEngagement  # noqa: PLC0415

        eng = db.get(ProjectEngagement, dep.engagement_id)
        if eng is not None and eng.contractor_id == emp:
            return
    records.record_verification(
        db,
        p,
        rec,
        TrainingVerificationMethod.provider_register_file,
        (pv.verification_domains or [pv.provider_code])[0],
        TrainingVerificationOutcome.confirmed,
        (b.evidence_sha256 or "")[:100],
        at,
    )


def _commit_attendance(
    db: Session, p: Principal, b: TrainingImportBatch, valid: list[dict[str, Any]]
) -> int:
    s = db.get(TrainingSession, b.session_id) if b.session_id else None
    assert s is not None  # noqa: S101
    by_nom: dict[str, list[dict[str, Any]]] = {}
    for r in valid:
        by_nom.setdefault(r["nomination_id"], []).append(r)
    n_rows = 0
    for nid, rows in by_nom.items():
        n = db.get(TrainingNomination, uuid.UUID(nid))
        if n is None:
            continue
        before = cc.snap(n, exclude=("theory_score_pct",))
        mins = dict(n.minutes_by_day or {})
        for r in rows:
            if r.get("day_no") is not None and r.get("minutes") is not None:
                mins[str(r["day_no"])] = int(r["minutes"])
            if r.get("theory_score_pct") is not None:
                n.theory_score_pct = Decimal(r["theory_score_pct"])
            if r.get("practical_result"):
                n.practical_result = PracticalResult(r["practical_result"])
                n.practical_by_user_id = p.user.id
            n_rows += 1
        n.minutes_by_day = mins
        days = len(s.days or [])
        if all(int(mins.get(str(i + 1), 0)) == 0 for i in range(days)):
            n.status = NS.absent
        elif ssvc.complete(s, n):
            n.status = NS.attended
        else:
            n.status = NS.partial
        cc.stamp(n, p)
        db.flush()
        cc.record(
            db, p, AuditAction.update, EntityType.training_nomination, n, s.project_id, before,
            {"import": str(b.id)}, after=cc.snap(n, exclude=("theory_score_pct",)),
        )  # fmt: skip
    return n_rows


# ---- template -----------------------------------------------------------------------------------


def template(t: TrainingImportTemplate, fmt_: ExportFormat, headers: str) -> tuple[bytes, str, str]:
    cols = _cols(t)
    names = [ar if headers == "ar" else k for k, ar, _ in cols]
    if t == T.training_records:
        ex = {
            "worker_no": "WKR-000019",
            "course_code": "WAH",
            "provider_code": "HAYAT",
            "certificate_no": "TEST-WAH-0001",
            "completed_on": "2026-09-01",
            "printed_expiry": "2028-08-31",
            "theory_score_pct": "85",
            "practical_result": "pass",
            "hours": "",
            "project_sponsored": "N",
            "name_as_printed": "Test Worker (fake)",
            "id_on_card": "",
        }
    else:
        ex = {"worker_no": "WKR-000019", "day_no": "1", "minutes": "420"}
    example = [ex.get(k, "") for k, _ar, _r in cols]
    return export_svc.encode(names, [example], fmt_, f"training-import-{t.value}-{headers}")
