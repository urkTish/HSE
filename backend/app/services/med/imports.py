"""Medical imports (spec 6a-occupational-health §3.11, IM6-1…IM6-5): template `fitness_records`,
dry-run first, commit a Validated batch ≤ 60 min old.

`clinic_register_file` (capability 157 holders, with the clinic as `provider_id`) commits
Accepted assessments verified with method `clinic_register_file`; `contractor_file` (Contractor
HSE Rep) commits Draft external certificates (a scan must be added before Submit). The parsed
rows are stored encrypted and erased at commit, discard or expiry; the audit keeps the sha256."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import WorkerIdType, WorkerStatus
from app.core.cert_enums import VerificationStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, ExportFormat, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.med_enums import (
    AssessmentSource,
    AssessmentStatus,
    AssessmentType,
    FitnessOutcome,
    FitnessVerificationMethod,
    FitnessVerificationOutcome,
    MedicalImportCode,
    MedicalImportSource,
    MedicalImportStatus,
    RestrictionCode,
)
from app.models import (
    FitnessAssessment,
    MedicalExaminer,
    MedicalImportBatch,
    MedicalProvider,
    Worker,
)
from app.schemas.medical import (
    FitnessLineInput,
    MedicalImportBatchPage,
    MedicalImportBatchRead,
    MedicalImportIssue,
    MedicalImportRow,
    RestrictionInput,
)
from app.services import audit
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.common import paginate
from app.services.med import alerts, assessments, common, engine
from app.services.permissions import Principal, forbidden_error
from app.services.workforce_import import _norm_header, _read_table, file_invalid

C = common.C
IC = MedicalImportCode
ST = MedicalImportStatus
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
TTL = timedelta(minutes=60)
COLS: list[tuple[str, str, bool]] = [
    ("worker_no", "رقم العامل", False),
    ("id_type", "نوع الهوية", False),
    ("id_number", "رقم الهوية", False),
    ("passport_country", "بلد الجواز", False),
    ("project_code", "رمز المشروع", False),
    ("provider_code", "رمز الجهة", True),
    ("examiner_no", "رقم الفاحص", True),
    ("assessment_type", "نوع التقييم", True),
    ("examined_on", "تاريخ الفحص", True),
    ("certificate_no", "رقم الشهادة", True),
    ("code", "الرمز", True),
    ("outcome", "النتيجة", True),
    ("restrictions", "القيود", False),
    ("restriction_review_date", "تاريخ مراجعة القيود", False),
    ("unfit_review_date", "تاريخ إعادة التقييم", False),
    ("printed_next_due", "الاستحقاق المطبوع", False),
]
DATES = ("examined_on", "restriction_review_date", "unfit_review_date", "printed_next_due")
TEXT: dict[MedicalImportCode, tuple[str, str]] = {
    IC.E01: ("Worker not found or anonymised.", "العامل غير موجود أو مجهّل."),
    IC.E02: ("Unknown or inactive fitness code.", "رمز لياقة غير معروف أو غير فعّال."),
    IC.E03: ("The clinic is not acceptable on the examination date.", "العيادة غير مقبولة."),
    IC.E04: ("The examiner is not valid or not qualified for the code.", "الفاحص غير مؤهل."),
    IC.E05: ("Duplicate certificate or code.", "شهادة أو رمز مكرر."),
    IC.E06: ("Outcome, restriction or review-date rules not met.", "قواعد النتيجة أو القيود."),
    IC.E07: ("Examination date in the future or every line expired.", "تاريخ الفحص غير صالح."),
    IC.E08: ("Row outside your scope.", "الصف خارج نطاقك."),
    IC.E09: ("ID mismatch.", "عدم تطابق الهوية."),
    IC.E10: ("Unparseable value.", "قيمة غير مقروءة."),
    IC.W01: (
        "Printed next-due later than the code validity.",
        "الاستحقاق المطبوع أبعد من الصلاحية.",
    ),
    IC.W02: ("A line expires within 30 days.", "بند ينتهي خلال 30 يوماً."),
    IC.W03: ("The same file was already committed.", "تم اعتماد الملف نفسه سابقاً."),
    IC.W04: ("Permanently unfit outcome.", "نتيجة عدم لياقة نهائية."),
}
MAP = {
    ErrorCode.MEDICAL_PROVIDER_NOT_ACCEPTABLE: IC.E03,
    ErrorCode.EXAMINER_LICENCE_INVALID: IC.E04,
    ErrorCode.EXAMINER_NOT_QUALIFIED: IC.E04,
    ErrorCode.DUPLICATE_CODE_LINE: IC.E05,
    ErrorCode.CERT_EXISTS: IC.E05,
    ErrorCode.CERT_NO_REUSED: IC.E05,
    ErrorCode.RESTRICTIONS_REQUIRED: IC.E06,
    ErrorCode.RESTRICTIONS_NOT_ALLOWED: IC.E06,
    ErrorCode.REVIEW_DATE_INVALID: IC.E06,
    ErrorCode.SECOND_OPINION_REQUIRED: IC.E06,
    ErrorCode.FITNESS_ALREADY_EXPIRED: IC.E07,
}


def _issue(code: IC, fld: str | None = None) -> dict[str, Any]:
    level = "warning" if code.value.startswith("W") else "error"
    return {"code": code.value, "level": level, "field": fld}


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ---- template / parse ----------------------------------------------------------------------------


def template(fmt_: ExportFormat, headers: str) -> tuple[bytes, str, str]:
    names = [ar if headers == "ar" else k for k, ar, _ in COLS]
    ex = {
        "worker_no": "WKR-000003",
        "provider_code": "SALAMA",
        "examiner_no": "EXR-0003",
        "assessment_type": "periodic",
        "examined_on": "2026-09-20",
        "certificate_no": "SAL-TEST-26-0001",
        "code": "GEN-FIT",
        "outcome": "fit",
    }
    return export_svc.encode(
        names,
        [[ex.get(k, "") for k, _a, _r in COLS]],
        fmt_,
        f"medical-import-fitness_records-{headers}",
    )


def parse(name: str, content: bytes) -> list[dict[str, Any]]:
    from app.services.cert.imports import _date  # noqa: PLC0415

    if len(content) > MAX_BYTES:
        raise file_invalid("The file is larger than 5 MB (E10).")
    table = _read_table(name, content)
    while table and all(c in (None, "") for c in table[-1]):
        table.pop()
    if not table:
        raise file_invalid("The file is empty (E10).")
    hm: dict[str, str] = {}
    for k, ar, _ in COLS:
        hm[k] = k
        hm[_norm_header(ar)] = k
        hm[ar] = k
    headers = [hm.get(_norm_header(h)) or hm.get(str(h or "").strip()) for h in table[0]]
    missing = [k for k, _, req in COLS if req and k not in headers]
    if "worker_no" not in headers and "id_number" not in headers:
        missing.append("worker_no")
    if missing:
        raise ApiError(
            422,
            ErrorCode.IMPORT_FILE_INVALID,
            "Missing required column(s): " + ", ".join(missing) + " (E10).",
            "أعمدة مطلوبة مفقودة: " + "، ".join(missing),
            meta={"code": IC.E10.value},
        )
    data = [r for r in table[1:] if any(c not in (None, "") for c in r)]
    if len(data) > MAX_ROWS:
        raise file_invalid(f"The file has more than {MAX_ROWS:,} data rows (E10).")
    rows = []
    for i, raw in enumerate(data, start=1):
        vals = {h: raw[j] if j < len(raw) else None for j, h in enumerate(headers) if h}
        row: dict[str, Any] = {"row_no": i, "issues": []}
        for k, _ar, _req in COLS:
            v = vals.get(k)
            if k in DATES:
                d, ok = _date(v)
                if not ok:
                    row["issues"].append(_issue(IC.E10, k))
                row[k] = d.isoformat() if d else None
            elif k == "id_number":
                s = _s(v)
                row["id_number_enc"] = crypto.encrypt(s).hex() if s else None
            else:
                row[k] = _s(v)
        rows.append(row)
    return rows


# ---- validation ----------------------------------------------------------------------------------


def _worker(db: Session, r: dict[str, Any]) -> Worker | None:
    if r.get("worker_no"):
        w = db.scalar(select(Worker).where(Worker.worker_no == r["worker_no"]))
    elif r.get("id_number_enc"):
        number = crypto.decrypt(bytes.fromhex(r["id_number_enc"]))
        try:
            bidx = acommon.blind_index(
                WorkerIdType(r.get("id_type") or "iqama"), number, r.get("passport_country")
            )
        except Exception:
            return None
        w = db.scalar(select(Worker).where(Worker.id_number_bidx == bidx))
    else:
        return None
    if w is None or w.status == WorkerStatus.anonymised:
        return None
    return w


def _restrictions(text: str | None) -> list[RestrictionInput]:
    out = []
    for raw in (text or "").split(";"):
        part = raw.strip()
        if not part:
            continue
        code, _, val = part.partition(":")
        rc = RestrictionCode(code.strip())
        if rc == RestrictionCode.lifting_limit_kg:
            out.append(RestrictionInput(code=rc, value=int(val)))
        elif rc == RestrictionCode.other_functional:
            out.append(RestrictionInput(code=rc, text=val.strip() or None))
        else:
            out.append(RestrictionInput(code=rc))
    return out


def _line(r: dict[str, Any]) -> FitnessLineInput:
    def dd(k: str) -> date | None:
        return date.fromisoformat(r[k]) if r.get(k) else None

    return FitnessLineInput(
        code=r["code"],
        outcome=FitnessOutcome(r["outcome"]),
        restrictions=_restrictions(r.get("restrictions")),
        restriction_review_date=dd("restriction_review_date"),
        unfit_review_date=dd("unfit_review_date"),
        printed_next_due=dd("printed_next_due"),
    )


def validate(
    db: Session, p: Principal, b: MedicalImportBatch, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    g = p.grant(b.project_id, C.fitness_import)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if any(i["level"] == "error" for i in r["issues"]):
            continue
        w = _worker(db, r)
        if w is None:
            r["issues"].append(_issue(IC.E01, "worker_no"))
            continue
        r["worker_id"] = str(w.id)
        r["worker_no"] = w.worker_no
        dep = common.deployment(db, w.id, b.project_id)
        if dep is None or not common.covers_dep(g, dep):
            r["issues"].append(_issue(IC.E08, "worker_no"))
            continue
        fc = common.code(db, r.get("code") or "")
        if fc is None or not fc.active:
            r["issues"].append(_issue(IC.E02, "code"))
            continue
        try:
            FitnessOutcome(r.get("outcome") or "")
            AssessmentType(r.get("assessment_type") or "")
            _restrictions(r.get("restrictions"))
        except ValueError:
            r["issues"].append(_issue(IC.E10, "outcome"))
            continue
        groups[(r.get("provider_code") or "", r.get("certificate_no") or "")].append(r)
    sha_seen = db.scalar(
        select(MedicalImportBatch.id).where(
            MedicalImportBatch.project_id == b.project_id,
            MedicalImportBatch.file_sha256 == b.file_sha256,
            MedicalImportBatch.status == ST.committed,
        )
    )
    for (pcode, cert_no), grp in groups.items():
        pv = db.scalar(select(MedicalProvider).where(MedicalProvider.provider_code == pcode))
        if pv is None or (b.provider_id is not None and pv.id != b.provider_id):
            for r in grp:
                r["issues"].append(_issue(IC.E03, "provider_code"))
            continue
        first = grp[0]
        wids = {r["worker_id"] for r in grp}
        if len(wids) > 1:
            for r in grp:
                r["issues"].append(_issue(IC.E05, "certificate_no"))
            continue
        x = db.scalar(
            select(MedicalExaminer).where(MedicalExaminer.examiner_no == first.get("examiner_no"))
        )
        if x is None:
            for r in grp:
                r["issues"].append(_issue(IC.E04, "examiner_no"))
            continue
        examined = date.fromisoformat(first["examined_on"])
        wid = uuid.UUID(first["worker_id"])
        for r in grp:
            try:
                prep = assessments.prepare(
                    db,
                    p,
                    b.project_id,
                    wid,
                    AssessmentSource.import_,
                    pv,
                    x,
                    examined,
                    [_line(r)],
                )
                assessments._cert_unique(db, None, pv, cert_no, wid, b.project_id)
            except ApiError as e:
                code = MAP.get(e.code)
                if code is None:
                    code = IC.E07 if "future" in (e.message or "") else IC.E06
                r["issues"].append(_issue(code))
                continue
            ln = prep.lines[0]
            if (
                ln["printed_next_due"]
                and ln["limiting_factor"] is not None
                and ln["limiting_factor"].value != "printed_next_due"
            ):
                r["issues"].append(_issue(IC.W01, "printed_next_due"))
            vu = ln["valid_until"]
            if vu is not None and vu < today():
                r["issues"].append(_issue(IC.E07, "examined_on"))
            elif vu is not None and vu <= today() + timedelta(days=30):
                r["issues"].append(_issue(IC.W02))
            if ln["outcome"] == FitnessOutcome.permanently_unfit:
                r["issues"].append(_issue(IC.W04, "outcome"))
            if sha_seen:
                r["issues"].append(_issue(IC.W03))
            r["provider_id"] = str(pv.id)
            r["examiner_id"] = str(x.id)
    for r in rows:
        errs = [i for i in r["issues"] if i["level"] == "error"]
        r["status"] = "error" if errs else ("warning" if r["issues"] else "ok")
    return rows


# ---- batches -------------------------------------------------------------------------------------


def _require(db: Session, p: Principal, project_id: uuid.UUID, source: MedicalImportSource) -> None:
    common.visible_project(db, p, project_id)
    p.require(project_id, C.fitness_import)
    if (
        source == MedicalImportSource.clinic_register_file
        and p.grant(project_id, C.fitness_clinical_view) is None
    ):
        raise forbidden_error("A clinic register file needs capability 157 (IM6-3).")


def _rows(b: MedicalImportBatch) -> list[dict[str, Any]]:
    if b.rows_enc is None:
        return []
    data: list[dict[str, Any]] = json.loads(crypto.decrypt(b.rows_enc))
    return data


def _expire(db: Session, b: MedicalImportBatch) -> None:
    if b.status in (ST.uploaded, ST.validated) and now() > b.expires_at:
        b.status = ST.expired
        b.rows_enc = None
        db.flush()


def to_read(db: Session, b: MedicalImportBatch) -> MedicalImportBatchRead:
    rows = []
    for r in b.report or []:
        rows.append(
            MedicalImportRow(
                row_no=r["row_no"],
                worker_no=r.get("worker_no"),
                id_masked=r.get("id_masked"),
                certificate_no=r.get("certificate_no"),
                code=r.get("code"),
                status=r.get("status", "ok"),
                issues=[
                    MedicalImportIssue(
                        code=IC(i["code"]),
                        level=i["level"],
                        message_en=TEXT[IC(i["code"])][0],
                        message_ar=TEXT[IC(i["code"])][1],
                        field=i.get("field"),
                    )
                    for i in r.get("issues", [])
                ],
            )
        )
    nos = []
    if b.committed_assessment_ids:
        nos = list(
            db.scalars(
                select(FitnessAssessment.assessment_no).where(
                    FitnessAssessment.id.in_(b.committed_assessment_ids)
                )
            )
        )
    return MedicalImportBatchRead(
        id=b.id,
        project_id=b.project_id,
        source=b.source,
        provider_id=b.provider_id,
        file_name=b.file_name,
        file_sha256=b.file_sha256,
        status=b.status,
        counts=dict(b.counts or {}),
        file_issues=[],
        rows=rows,
        uploaded_by=common.user_ref(db, b.uploaded_by_user_id),
        created_at=b.created_at,
        expires_at=b.expires_at,
        committed_at=b.committed_at,
        committed_assessment_nos=sorted(nos),
    )


def _report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        masked = None
        if r.get("id_number_enc"):
            n = crypto.decrypt(bytes.fromhex(r["id_number_enc"]))
            masked = acommon.mask_worker_id(WorkerIdType(r.get("id_type") or "iqama"), n)
        out.append(
            {
                "row_no": r["row_no"],
                "worker_no": r.get("worker_no"),
                "id_masked": masked,
                "certificate_no": r.get("certificate_no"),
                "code": r.get("code"),
                "status": r.get("status", "ok"),
                "issues": r["issues"],
            }
        )
    return out


def upload(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    file: UploadFile,
    source: MedicalImportSource,
    provider_id: uuid.UUID | None,
) -> MedicalImportBatchRead:
    _require(db, p, project_id, source)
    p.ensure_writer()
    if source == MedicalImportSource.clinic_register_file:
        if provider_id is None:
            from app.core.errors import validation_error  # noqa: PLC0415

            raise validation_error("provider_id", "Name the clinic whose register this is.")
        common.provider_or_404(db, provider_id)
    content = file.file.read()
    name = file.filename or "import.csv"
    sha = hashlib.sha256(content).hexdigest()
    rows = parse(name, content)
    at = now()
    b = MedicalImportBatch(
        id=uuid.uuid4(),
        project_id=project_id,
        source=source,
        provider_id=provider_id,
        file_name=name[:255],
        file_sha256=sha,
        file_size=len(content),
        status=ST.uploaded,
        uploaded_by_user_id=p.user.id,
        created_at=at,
        expires_at=at + TTL,
        committed_assessment_ids=[],
    )
    db.add(b)
    db.flush()
    rows = validate(db, p, b, rows)
    b.rows_enc = crypto.encrypt(json.dumps(rows))
    b.report = _report(rows)
    b.counts = {
        "rows": len(rows),
        "ok": sum(1 for r in rows if r["status"] == "ok"),
        "warnings": sum(1 for r in rows if r["status"] == "warning"),
        "errors": sum(1 for r in rows if r["status"] == "error"),
    }
    b.status = ST.validated
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.medical_import_batch,
        entity_id=b.id,
        project_id=project_id,
        details={"sha256": sha, "source": source.value, "rows": len(rows)},
    )
    return to_read(db, b)


def list_batches(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[MedicalImportStatus] | None,
) -> MedicalImportBatchPage:
    common.visible_project(db, p, project_id)
    p.require(project_id, C.fitness_import)
    stmt = (
        select(MedicalImportBatch)
        .where(MedicalImportBatch.project_id == project_id)
        .order_by(MedicalImportBatch.created_at.desc())
    )
    if not (p.is_manager or common.is_oh(p, project_id)):
        stmt = stmt.where(MedicalImportBatch.uploaded_by_user_id == p.user.id)
    if status:
        stmt = stmt.where(MedicalImportBatch.status.in_(status))
    rows, total = paginate(db, stmt, page, page_size)
    for b in rows:
        _expire(db, b)
    return MedicalImportBatchPage(
        items=[to_read(db, b) for b in rows], total=total, page=page, page_size=page_size
    )


def _batch(db: Session, p: Principal, batch_id: uuid.UUID) -> MedicalImportBatch:
    b = db.get(MedicalImportBatch, batch_id)
    if b is None or not p.can_see_project(b.project_id):
        raise not_found("Import batch")
    p.require(b.project_id, C.fitness_import)
    if b.uploaded_by_user_id != p.user.id and not (p.is_manager or common.is_oh(p, b.project_id)):
        raise forbidden_error()
    _expire(db, b)
    return b


def get(db: Session, p: Principal, batch_id: uuid.UUID) -> MedicalImportBatchRead:
    return to_read(db, _batch(db, p, batch_id))


def discard(db: Session, p: Principal, batch_id: uuid.UUID) -> MedicalImportBatchRead:
    b = _batch(db, p, batch_id)
    if b.status not in (ST.uploaded, ST.validated):
        raise ApiError(409, ErrorCode.IMPORT_EXPIRED, "The batch is closed.", "الدفعة مغلقة.")
    b.status = ST.discarded
    b.rows_enc = None
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(b.project_id),
        entity_type=EntityType.medical_import_batch,
        entity_id=b.id,
        project_id=b.project_id,
        details={"discarded": True, "sha256": b.file_sha256},
    )
    return to_read(db, b)


def commit(db: Session, p: Principal, batch_id: uuid.UUID) -> MedicalImportBatchRead:
    b = _batch(db, p, batch_id)
    p.ensure_writer()
    if b.status != ST.validated:
        raise ApiError(
            409,
            ErrorCode.IMPORT_EXPIRED,
            "Only a Validated batch less than 60 minutes old can be committed.",
            "يمكن اعتماد دفعة متحقق منها خلال 60 دقيقة فقط.",
        )
    rows = [r for r in _rows(b) if r.get("status") in ("ok", "warning")]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["provider_code"], r["certificate_no"])].append(r)
    at = now()
    clinic = b.source == MedicalImportSource.clinic_register_file
    created: list[uuid.UUID] = []
    unfit = False
    for (_pc, cert_no), grp in groups.items():
        first = grp[0]
        pv = common.provider_or_404(db, uuid.UUID(first["provider_id"]))
        x = common.examiner_or_404(db, uuid.UUID(first["examiner_id"]))
        wid = uuid.UUID(first["worker_id"])
        examined = date.fromisoformat(first["examined_on"])
        prep = assessments.prepare(
            db,
            p,
            b.project_id,
            wid,
            AssessmentSource.import_,
            pv,
            x,
            examined,
            [_line(r) for r in grp],
        )
        y, seq, a_no, _c = assessments._number(db, b.project_id)
        dep = common.deployment(db, wid, b.project_id)
        a = FitnessAssessment(
            id=uuid.uuid4(),
            year=y,
            seq=seq,
            assessment_no=a_no,
            worker_id=wid,
            project_id=b.project_id,
            engagement_id=dep.engagement_id if dep else None,
            assessment_type=AssessmentType(first["assessment_type"]),
            source=AssessmentSource.import_,
            provider_id=pv.id,
            examiner_id=x.id,
            examined_on=examined,
            certificate_no=cert_no,
            purpose_notice_given=True,
            purpose_notice_version=common.settings(db, b.project_id).worker_purpose_notice_version,
            historic=False,
            status=AssessmentStatus.draft,
            status_changed_at=at,
            recorded_by_user_id=p.user.id,
            submitted_by_user_id=p.user.id,
            import_batch_id=b.id,
            alerts_sent=[],
        )
        db.add(a)
        db.flush()
        assessments._write_lines(db, a, prep.lines)
        if clinic:
            a.verification_status = VerificationStatus.verified
            a.verified_at = at
            assessments._verification_row(
                db,
                a,
                p,
                FitnessVerificationMethod.clinic_register_file,
                b.file_name,
                FitnessVerificationOutcome.confirmed,
                b.file_sha256[:32],
                at,
                True,
                VerificationStatus.verified,
            )
            assessments.accept(db, p, a, at)
        else:
            engine.refresh_states(db, wid)
        unfit |= any(ln["outcome"] == FitnessOutcome.permanently_unfit for ln in prep.lines)
        created.append(a.id)
    b.committed_assessment_ids = created
    b.committed_at = at
    b.status = ST.committed
    b.rows_enc = None
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(b.project_id),
        entity_type=EntityType.medical_import_batch,
        entity_id=b.id,
        project_id=b.project_id,
        details={"committed": len(created), "sha256": b.file_sha256},
    )
    if unfit and not clinic:
        alerts.send(
            db,
            alerts.managers(db),
            NotificationKind.fitness_permanently_unfit,
            "Fitness outcome imported (no detail)",
            "تم استيراد نتيجة لياقة",
            b.project_id,
            email=False,
        )
    return to_read(db, b)
