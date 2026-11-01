"""Demo seed of package Q4 (spec 8-quality Appendix A.7, §E.10 seed consolidation).

* Quality audit checklists `Q9K` (ISO 9001:2015, 56 items), `QSUP` (30) and `QGDP` (40) on the 6d
  engine (kind `quality`).
* Documents (PQP Rev.1 and Rev.B for review, MS-004 Rev.2 cited by ITP-STC-001, the RUH-CCH SOPs
  with read-and-acknowledge 2 of 3), processes, the 2026 audit programme, the quality audits
  QAU-ANIA-EXP-2026-0003 / -0004 and QAU-RUH-CCH-2026-0006, the management review
  MRV-RUH-CCH-2026-0001, supplier evaluations and the Q3 2026 scores (QX19), KPI targets, the
  September work value (QX26) and SPC charts (QX22 sets of the C40 mix).
* Consolidation of the parts' generators to Appendix A.8 (D-367): one more September test of
  ANIA-EXP (212 with a verdict), competence evidence and Q4 awareness requirements (64 pairs,
  60 met), calibrations of the spare mapping loggers MTE-0123 … 0127, the QX11 OOT `ncr` item
  re-pointed to the receiving NCR it opened, and three September RUH-CCH NCRs re-pointed to the
  minor NCs of QAU-RUH-CCH-2026-0006 (so A.8's NCR counts stay)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.quality.common import QRecordType

RT = QRecordType
TZ = ZoneInfo("Asia/Riyadh")
D = Decimal
PUBLISHED = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def at(d: date, hh: int = 9, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=TZ).astimezone(UTC)


# ---- checklists (Q-AUD-07) -----------------------------------------------------------------------

CLAUSES = [
    ("4", "Context of the organization", "سياق المنظمة", ["4.1", "4.2", "4.3", "4.4"]),
    ("5", "Leadership", "القيادة", ["5.1", "5.2", "5.3"]),
    ("6", "Planning", "التخطيط", ["6.1", "6.2", "6.3"]),
    (
        "7",
        "Support",
        "الدعم",
        [
            "7.1.2",
            "7.1.3",
            "7.1.4",
            "7.1.5",
            "7.1.6",
            "7.2",
            "7.3",
            "7.4",
            "7.5.1",
            "7.5.2",
            "7.5.3",
        ],
    ),
    (
        "8",
        "Operation",
        "التشغيل",
        [
            "8.1",
            "8.2.1",
            "8.2.2",
            "8.2.3",
            "8.3",
            "8.4.1",
            "8.4.2",
            "8.4.3",
            "8.5.1",
            "8.5.2",
            "8.5.3",
            "8.5.4",
            "8.5.5",
            "8.5.6",
            "8.6",
            "8.7",
        ],
    ),
    ("9", "Performance evaluation", "تقييم الأداء", ["9.1.1", "9.1.2", "9.1.3", "9.2", "9.3"]),
    ("10", "Improvement", "التحسين", ["10.1", "10.2", "10.3"]),
]
CRITICAL = {"8.5.1", "8.7", "10.2"}


def _items(code: str, refs: list[tuple[str, str, str, str]]) -> tuple[list[Any], list[Any]]:
    secs, items, seen = [], [], set()
    for n, (sec, sec_en, sec_ar, ref) in enumerate(refs, start=1):
        if sec not in seen:
            seen.add(sec)
            secs.append({"code": sec, "title_en": sec_en, "title_ar": sec_ar, "order": len(seen)})
        crit = ref.split(" ")[0] in CRITICAL
        items.append(
            {
                "item_code": f"{code}-{n:02d}",
                "section_code": sec,
                "order": n,
                "text_en": f"Requirement {ref} is met and evidenced",
                "text_ar": f"المتطلب {ref} مستوفى وموثق بالأدلة",
                "item_type": "rating_0_3",
                "weight": 3 if crit else 1,
                "critical": crit,
                "stop_rule": "none",
                "na_allowed": not crit,
                "photo_required_on_fail": False,
                "default_severity": "minor",
                "airside_only": False,
                "numeric_rule": None,
                "options": None,
                "suggested_ca_en": None,
                "suggested_ca_ar": None,
                "suggested_control_level": None,
                "reference": f"ISO 9001:2015 {ref}",
                "guidance_en": None,
                "guidance_ar": None,
            }
        )
    return secs, items


def _q9k_refs(count: int) -> list[tuple[str, str, str, str]]:
    base = [(s, en, ar, r) for s, en, ar, refs in CLAUSES for r in refs]
    out = list(base)
    i = 0
    while len(out) < count:  # second look at operation clauses (evidence on site)
        s, en, ar, r = base[(i % 16) + 21]
        out.append((s, en, ar, f"{r} (site evidence)"))
        i += 1
    return out[:count]


def ensure_templates(db: Session) -> dict[str, Any]:
    from app.core.field_enums import TemplateKind, VersionStatus  # noqa: PLC0415
    from app.models.field import ChecklistTemplate  # noqa: PLC0415

    fa = db.scalar(
        select(_user_model().id).where(_user_model().email == "faisal.harbi@example.com")
    )
    specs = {
        "Q9K": (
            "q_audit",
            "both",
            "ISO 9001:2015 internal audit",
            "التدقيق الداخلي ISO 9001:2015",
            _q9k_refs(56),
        ),
        "QSUP": (
            "supplier_audit",
            "both",
            "Supplier quality audit",
            "تدقيق جودة المورد",
            [(s, en, ar, r) for s, en, ar, refs in CLAUSES[3:5] for r in refs][:27]
            + [("8", "Operation", "التشغيل", f"8.4.{k} (supplier)") for k in (1, 2, 3)],
        ),
        "QGDP": (
            "q_audit",
            "logistics",
            "Cold-chain warehouse audit (GDP)",
            "تدقيق مستودع سلسلة التبريد",
            _q9k_refs(40),
        ),
    }
    out = {}
    for code, (qt, prof, en, ar, refs) in specs.items():
        t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == code))
        if t is None:
            secs, items = _items(code, refs)
            t = ChecklistTemplate(
                id=uuid.uuid4(),
                template_code=code,
                version=1,
                kind=TemplateKind.quality,
                quality_type=qt,
                sector_profiles=prof,
                title_en=en,
                title_ar=ar,
                sections=secs,
                items=items,
                zone_types=[],
                project_ids=[],
                pass_mark_pct=80,
                authored_by_user_id=fa,
                published_by_user_id=fa,
                published_at=PUBLISHED,
                status=VersionStatus.published,
                created_by_user_id=fa,
                seed_fake=True,
            )
            db.add(t)
            db.flush()
        out[code] = t
    return out


def _user_model() -> Any:
    from app.models import User  # noqa: PLC0415

    return User


class _W:
    def __init__(self, db: Session) -> None:
        from app.models import Project  # noqa: PLC0415

        self.db = db
        self.p = {
            x.code: x
            for x in db.scalars(select(Project).where(Project.code.in_(["ANIA-EXP", "RUH-CCH"])))
        }

    def u(self, key: str) -> uuid.UUID:
        U = _user_model()  # noqa: N806
        uid = self.db.scalar(select(U.id).where(U.email == f"{key}@example.com"))
        assert uid is not None, key  # noqa: S101
        return uid  # type: ignore[no-any-return]

    def sup(self, code: str) -> Any:
        from app.models.quality import QSupplier  # noqa: PLC0415

        return self.db.scalar(select(QSupplier).where(QSupplier.supplier_code == code))

    def site(self, project: Any, code: str) -> uuid.UUID:
        from app.models import Site  # noqa: PLC0415

        sid = self.db.scalar(
            select(Site.id).where(Site.project_id == project.id, Site.code == code)
        )
        assert sid is not None, code  # noqa: S101
        return sid

    def ncr(self, project: Any, no: str) -> Any:
        from app.models.quality import QNcr  # noqa: PLC0415

        return self.db.scalar(
            select(_ncr()).where(QNcr.project_id == project.id, QNcr.ncr_no == no)
        )


def _ncr() -> Any:
    from app.models.quality import QNcr  # noqa: PLC0415

    return QNcr


def _bump(
    db: Session, project: Any, rt: Any, prefix: str, seq: int, yearly: bool = True, year: int = 2026
) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    row = numbering._row(db, project.id, rt, lock=True)
    key = f"{year if yearly else 'all'}||{prefix}"
    counters = dict(row.counters or {})
    counters[key] = max(int(counters.get(key, 0)), seq)
    row.counters = counters
    db.flush()


def _link(
    db: Session, project: Any, ft: Any, fid: uuid.UUID, tt: Any, tid: uuid.UUID, kind: str
) -> None:
    from app.core.quality.common import QLinkKind  # noqa: PLC0415
    from app.services.quality import links  # noqa: PLC0415

    links.add(db, project.id, ft, fid, tt, tid, QLinkKind(kind), None)


# ---- documents -----------------------------------------------------------------------------------


def _pdf(db: Session, project: Any, rev: Any, name: str, by: uuid.UUID) -> uuid.UUID:
    from app.core.hse_enums import AttachmentOwner  # noqa: PLC0415
    from app.services import attachments  # noqa: PLC0415

    return attachments.store(
        db,
        AttachmentOwner.q_document_file,
        rev.id,
        project.id,
        name,
        PDF,
        "application/pdf",
        by,
        generated=True,
    ).id


def _doc(
    w: _W,
    project: Any,
    no: str,
    dtype: str,
    en: str,
    ar: str,
    owner: str,
    revs: list[tuple[str, str, date | None, str]],
    **kw: Any,
) -> Any:
    """revs: (code, status, approved_on, author) oldest first."""
    from app.core.quality.q4 import QDocType, QRevStatus  # noqa: PLC0415
    from app.models.quality.q4 import QDocument, QDocumentRevision  # noqa: PLC0415
    from app.services.quality.q4 import base as qb  # noqa: PLC0415

    db = w.db
    approver = kw.pop("approver", "hatem.shehri")
    d = QDocument(
        id=uuid.uuid4(),
        project_id=project.id,
        doc_no=no,
        doc_type=QDocType(dtype),
        title_en=en,
        title_ar=ar,
        owner_user_id=w.u(owner),
        status=QRevStatus.draft,
        created_by_user_id=w.u(owner),
        alerts_sent=[],
        seed_fake=True,
        **kw,
    )
    db.add(d)
    db.flush()
    out = []
    for i, (code, st, on, author) in enumerate(revs, start=1):
        r = QDocumentRevision(
            id=uuid.uuid4(),
            document_id=d.id,
            rev_code=code,
            rev_index=i,
            status=QRevStatus(st),
            author_user_id=w.u(author),
            change_summary="Issued for use" if i == 1 else f"Revision {code}",
            created_by_user_id=w.u(author),
            seed_fake=True,
            submitted_at=at(on - timedelta(days=10)) if on else at(date(2026, 9, 28)),
            approved_at=at(on, 11) if on else None,
            approved_date=on,
            approved_by_user_id=w.u(approver) if on else None,
            effective_date=on,
        )
        db.add(r)
        db.flush()
        r.file_attachment_id = _pdf(db, project, r, f"{no}-Rev{code}.pdf", w.u(author))
        out.append(r)
        if st in ("approved", "superseded") and on:
            d.current_revision_id = r.id if st == "approved" else d.current_revision_id
            if st == "approved":
                d.status = QRevStatus.approved
                d.review_due_on = qb.due_after(on, 24)
    if d.current_revision_id is None and out:
        d.status = out[-1].status
    db.flush()
    return d, out


def _signoff(
    db: Session,
    project: Any,
    rt: Any,
    rid: uuid.UUID,
    step: str,
    decision: str,
    uid: uuid.UUID,
    on: datetime,
    capacity: str = "qa_qc_manager",
) -> None:
    from app.models.quality import QSignoff  # noqa: PLC0415

    db.add(
        QSignoff(
            id=uuid.uuid4(),
            project_id=project.id,
            record_type=rt.value,
            record_id=rid,
            step=step,
            decision=decision,
            signed_by_user_id=uid,
            signed_at=on,
            signer_capacity=capacity,
            evidence_attachment_ids=[],
            seed_fake=True,
        )
    )


def _documents(w: _W) -> None:
    from app.models.quality.q4 import QDocAck, QDocDistribution  # noqa: PLC0415

    db = w.db
    ania, ruh = w.p["ANIA-EXP"], w.p["RUH-CCH"]
    _pqp, pr = _doc(
        w,
        ania,
        "ANIA-EXP-QA-PQP-001",
        "pqp",
        "Project Quality Plan",
        "خطة الجودة للمشروع",
        "hatem.shehri",
        [
            ("0", "superseded", date(2026, 1, 12), "hatem.shehri"),
            ("1", "approved", date(2026, 3, 2), "hatem.shehri"),
            ("B", "for_review", None, "hatem.shehri"),
        ],
        profile="both",
    )
    pr[0].superseded_at = at(date(2026, 3, 2), 11)
    _signoff(
        db,
        ania,
        RT.document,
        pr[2].id,
        "review",
        "approved",
        w.u("rania.zahrani"),
        at(date(2026, 9, 29)),
        "quality_engineer",
    )
    for r in pr[:2]:
        _signoff(
            db,
            ania,
            RT.document,
            r.id,
            "review",
            "approved",
            w.u("rania.zahrani"),
            (r.approved_at or at(date(2026, 3, 1))) - timedelta(days=2),
            "quality_engineer",
        )
        _signoff(
            db,
            ania,
            RT.document,
            r.id,
            "approve",
            "approved",
            w.u("faisal.harbi"),
            r.approved_at or at(date(2026, 3, 2)),
            "hse_manager",
        )
    _ms, ms = _doc(
        w,
        ania,
        "ANIA-EXP-QA-MS-004",
        "method_statement",
        "Method statement — concreting",
        "بيان طريقة العمل — صب الخرسانة",
        "bilal.qureshi",
        [
            ("0", "superseded", date(2026, 2, 1), "bilal.qureshi"),
            ("1", "superseded", date(2026, 4, 5), "bilal.qureshi"),
            ("2", "approved", date(2026, 6, 14), "bilal.qureshi"),
        ],
        discipline="STC",
    )
    from app.models.quality.q1 import QItp  # noqa: PLC0415

    itp = db.scalar(
        select(QItp).where(
            QItp.project_id == ania.id,
            QItp.itp_no == "ITP-ANIA-EXP-STC-001",
            QItp.status == "approved",
        )
    )
    if itp is not None:
        _link(db, ania, RT.itp, itp.id, RT.document, ms[2].id, "relates")
    _doc(
        w,
        ruh,
        "RUH-CCH-QA-SOP-001",
        "sop",
        "Receiving SOP",
        "إجراء الاستلام",
        "reem.mutairi",
        [("0", "approved", date(2026, 1, 20), "imran.siddiq")],
        approver="reem.mutairi",
        profile="logistics",
    )
    sop7, s7 = _doc(
        w,
        ruh,
        "RUH-CCH-QA-SOP-007",
        "sop",
        "Temperature excursion SOP",
        "إجراء الانحرافات الحرارية",
        "reem.mutairi",
        [
            ("0", "superseded", date(2026, 2, 10), "imran.siddiq"),
            ("1", "approved", date(2026, 9, 1), "imran.siddiq"),
        ],
        approver="reem.mutairi",
        profile="logistics",
    )
    db.add(
        QDocDistribution(
            id=uuid.uuid4(),
            document_id=sop7.id,
            roles=["warehouse_qc"],
            positions=["WAREHOUSE_MGR"],
            engagement_ids=[],
            user_ids=[],
            ack_required=True,
            seed_fake=True,
        )
    )
    rev = s7[1]
    rev.ack_due_on = date(2026, 9, 8)
    for key, acked in (
        ("imran.siddiq", at(date(2026, 9, 2), 10)),
        ("saad.anazi", at(date(2026, 9, 4), 12)),
        ("naveen.kumar", None),
    ):
        db.add(
            QDocAck(
                id=uuid.uuid4(),
                revision_id=rev.id,
                user_id=w.u(key),
                due_on=date(2026, 9, 8),
                acked_at=acked,
                reminded=acked is None,
            )
        )
    from app.core.quality.q4 import DOC_PREFIX, QDocType  # noqa: PLC0415

    _bump(db, ania, RT.document, DOC_PREFIX[QDocType.pqp], 1, yearly=False)
    _bump(db, ania, RT.document, DOC_PREFIX[QDocType.method_statement], 4, yearly=False)
    _bump(db, ruh, RT.document, DOC_PREFIX[QDocType.sop], 7, yearly=False)
    db.flush()


# ---- processes, programme, audits ----------------------------------------------------------------


def _processes(w: _W) -> dict[str, Any]:
    from app.core.quality.common import QProfileScope  # noqa: PLC0415
    from app.core.quality.q4 import QRisk  # noqa: PLC0415
    from app.models.quality.q4 import QProcess  # noqa: PLC0415

    rows = [
        ("RUH-CCH", "RCV", "Receiving", "الاستلام", "imran.siddiq", "high"),
        ("RUH-CCH", "STO", "Storage", "التخزين", "saad.anazi", "high"),
        ("RUH-CCH", "DSP", "Dispatch and transport", "الإرسال والنقل", "naveen.kumar", "medium"),
        ("RUH-CCH", "CAL", "Calibration", "المعايرة", "imran.siddiq", "low"),
        (
            "RUH-CCH",
            "NCR",
            "Nonconformity and CAPA",
            "عدم المطابقة والإجراءات التصحيحية",
            "reem.mutairi",
            "medium",
        ),
        ("ANIA-EXP", "CON", "Concreting", "صب الخرسانة", "bilal.qureshi", "high"),
        ("ANIA-EXP", "WLD", "Structural welding", "اللحام الإنشائي", "joseph.mathew.qc", "medium"),
    ]
    out = {}
    for pc, code, en, ar, owner, risk in rows:
        x = QProcess(
            id=uuid.uuid4(),
            project_id=w.p[pc].id,
            code=code,
            name_en=en,
            name_ar=ar,
            owner_user_id=w.u(owner),
            risk=QRisk(risk),
            document_ids=[],
            profile=QProfileScope.logistics if pc == "RUH-CCH" else QProfileScope.construction,
            active=True,
            seed_fake=True,
        )
        w.db.add(x)
        out[f"{pc}:{code}"] = x
    w.db.flush()
    return out


def _audit(
    w: _W,
    project: Any,
    no: str,
    atype: str,
    tcode: str,
    lead: str,
    issuer: str,
    fw: tuple[date, date],
    issued: date,
    procs: list[Any],
    ratings: dict[int, str],
    supplier: Any = None,
    team: list[str] | None = None,
    summary: str = "",
) -> Any:
    from app.core.field_enums import AuditDomain, AuditStatus, AuditType  # noqa: PLC0415
    from app.models import FieldAudit, FieldFinding  # noqa: PLC0415
    from app.models.field import ChecklistResponse, ChecklistTemplate  # noqa: PLC0415
    from app.schemas.field import AnswerInput  # noqa: PLC0415
    from app.services.field import audits as fa  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    db = w.db
    t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == tcode))
    assert t is not None  # noqa: S101
    site = db.scalar(
        select(_site_model().id)
        .where(_site_model().project_id == project.id)
        .order_by(_site_model().code)
        .limit(1)
    )
    a = FieldAudit(
        id=uuid.uuid4(),
        audit_no=no,
        year=2026,
        seq=fc.next_seq(db, FieldAudit, project.id, 2026),
        project_id=project.id,
        audit_type=AuditType(atype),
        template_code=tcode,
        template_id=t.id,
        site_ids=[site],
        lead_auditor_id=w.u(lead),
        team_ids=[w.u(x) for x in team or []],
        planned_start=fw[0],
        planned_end=fw[1],
        fieldwork_start=fw[0],
        fieldwork_end=fw[1],
        opening_meeting_at=at(fw[0], 8),
        closing_meeting_at=at(fw[1], 15),
        status=AuditStatus.in_progress,
        created_by_user_id=w.u(lead),
        domain=AuditDomain.quality,
        auditee_supplier_id=supplier.id if supplier else None,
        process_ids=[x.id for x in procs],
        summary_en=summary,
        summary_ar=summary,
        alerts_sent=[],
        seed_fake=True,
    )
    db.add(a)
    db.flush()
    answers = []
    for i, it in enumerate(t.items, start=1):
        r = ratings.get(i, "3")
        answers.append(
            AnswerInput(
                item_code=it["item_code"],
                answer=r,
                note=None if r == "3" else f"Evidence gap against {it['reference']}",
            )
        )
    fa.apply_answers(db, project, a, answers, [], w.u(lead))
    resp = db.get(ChecklistResponse, a.response_id)
    assert resp is not None  # noqa: S101
    resp.completed_at = resp.received_at = at(fw[1], 16)
    resp.completed_date = fw[1]
    resp.submitted = True
    for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == resp.id)):
        f.completed_date = fw[1]
    a.status = AuditStatus.issued
    a.issued_by_user_id = w.u(issuer)
    a.issued_at = at(issued, 13)

    _signoff(
        db,
        project,
        RT.q_audit,
        a.id,
        "issue",
        "approved",
        w.u(issuer),
        at(issued, 13),
        "hse_manager" if issuer == "faisal.harbi" else "qa_qc_manager",
    )
    db.flush()
    return a


def _site_model() -> Any:
    from app.models import Site  # noqa: PLC0415

    return Site


def _audits(w: _W, procs: dict[str, Any]) -> None:
    from app.core.quality.common import QDetectionStage, QNcrSourceType  # noqa: PLC0415
    from app.core.quality.q4 import QProgrammeStatus, QProgrammeSubject, QRisk  # noqa: PLC0415
    from app.models import FieldFinding  # noqa: PLC0415
    from app.models.quality.q4 import QAuditProgrammeLine  # noqa: PLC0415
    from app.services.quality.q4 import audits as qa  # noqa: PLC0415

    db = w.db
    ania, ruh = w.p["ANIA-EXP"], w.p["RUH-CCH"]
    for pr in (ania, ruh):
        qa.generate_programme(db, pr, 2026, None)
    rmx = w.sup("RMX")
    ln_rmx = QAuditProgrammeLine(
        id=uuid.uuid4(),
        project_id=ania.id,
        year=2026,
        subject_kind=QProgrammeSubject.supplier,
        supplier_id=rmx.id,
        risk=QRisk.high,
        planned_month=9,
        status=QProgrammeStatus.planned,
        alerts_sent=[],
        seed_fake=True,
    )
    db.add(ln_rmx)
    db.flush()
    # RUH-CCH: QMS internal audit on RCV and STO (3 minor NCs at items 9, 31 and 44)
    a6 = _audit(
        w,
        ruh,
        "QAU-RUH-CCH-2026-0006",
        "qms_internal",
        "Q9K",
        "reem.mutairi",
        "faisal.harbi",
        (date(2026, 9, 15), date(2026, 9, 16)),
        date(2026, 9, 21),
        [procs["RUH-CCH:RCV"], procs["RUH-CCH:STO"]],
        {9: "1", 31: "1", 44: "1", 20: "2"},
        summary="Receiving and storage meet ISO 9001 with three minor nonconformities.",
    )
    a4 = _audit(
        w,
        ania,
        "QAU-ANIA-EXP-2026-0004",
        "supplier_quality",
        "QSUP",
        "bilal.qureshi",
        "hatem.shehri",
        (date(2026, 9, 8), date(2026, 9, 8)),
        date(2026, 9, 12),
        [],
        {12: "2"},
        supplier=rmx,
        summary="Riyadh Readymix batching plant audit: one observation on water addition records.",
    )
    a3 = _audit(
        w,
        ania,
        "QAU-ANIA-EXP-2026-0003",
        "process_quality",
        "Q9K",
        "rania.zahrani",
        "hatem.shehri",
        (date(2026, 9, 16), date(2026, 9, 17)),
        date(2026, 9, 20),
        [procs["ANIA-EXP:CON"]],
        {30: "2"},
        summary="Concreting process audit on Pier B: controlled; one opportunity for improvement.",
    )
    for ln in db.scalars(
        select(QAuditProgrammeLine).where(
            QAuditProgrammeLine.year == 2026, QAuditProgrammeLine.planned_month == 9
        )
    ):
        if ln.supplier_id == rmx.id:
            ln.audit_id = a4.id
        elif ln.process_id in (procs["RUH-CCH:RCV"].id, procs["RUH-CCH:STO"].id):
            ln.audit_id = a6.id
        elif ln.process_id == procs["ANIA-EXP:CON"].id:
            ln.audit_id = a3.id
        if ln.audit_id:
            ln.status = QProgrammeStatus.done
    for ln in db.scalars(
        select(QAuditProgrammeLine).where(
            QAuditProgrammeLine.year == 2026, QAuditProgrammeLine.planned_month == 3
        )
    ):
        ln.status = QProgrammeStatus.done  # March audits held before the module went live
        ln.status_reason = "Held on paper before the Quality module (records in the archive)."
    from app.models.field import ChecklistResponse  # noqa: PLC0415

    findings = list(
        db.scalars(
            select(FieldFinding)
            .join(ChecklistResponse, ChecklistResponse.id == FieldFinding.response_id)
            .where(ChecklistResponse.audit_id == a6.id, FieldFinding.severity == "minor_nc")
            .order_by(FieldFinding.finding_no)
        )
    )
    for f, no in zip(
        findings,
        ("NCR-RUH-CCH-2026-0032", "NCR-RUH-CCH-2026-0033", "NCR-RUH-CCH-2026-0035"),
        strict=False,
    ):
        n = w.ncr(ruh, no)
        if n is None:
            continue
        n.source_type, n.source_id, n.source_ref = (
            QNcrSourceType.q_audit_finding,
            f.id,
            f.finding_no,
        )
        n.detection_stage = QDetectionStage.internal_audit
        n.title = f"{a6.audit_no} {f.finding_no}: {n.title}"[:150]
        _link(db, ruh, RT.ncr, n.id, RT.q_audit, a6.id, "raised_from")
    _bump(db, ruh, RT.q_audit, "QAU", 6)
    _bump(db, ania, RT.q_audit, "QAU", 4)
    db.flush()


def _mrv(w: _W) -> None:
    from app.core.quality.q4 import MRV_INPUT_KEYS, QMrvStatus  # noqa: PLC0415
    from app.kpi import quality as qk  # noqa: PLC0415
    from app.models.quality.q4 import QManagementReview  # noqa: PLC0415

    ruh = w.p["RUH-CCH"]
    from app.core.quality.common import QAssigneeKind  # noqa: PLC0415
    from app.models.quality import QRpRule  # noqa: PLC0415

    # RUH-CCH: like `q_audit.issue` (A.5), the minutes are approved by Faisal (top management),
    # not by the QA/QC Manager who prepares the review
    rule = w.db.scalar(
        select(QRpRule).where(
            QRpRule.project_id == ruh.id,
            QRpRule.record_type == RT.management_review.value,
            QRpRule.step == "approve",
            QRpRule.record_id.is_(None),
            QRpRule.qualifier.is_(None),
        )
    )
    if rule is not None:
        rule.assignee_kind, rule.assignee = QAssigneeKind.user, str(w.u("faisal.harbi"))
    else:
        w.db.add(
            QRpRule(
                project_id=ruh.id,
                record_type=RT.management_review.value,
                step="approve",
                assignee_kind="user",
                assignee=str(w.u("faisal.harbi")),
                active=True,
                paper_allowed=True,
                self_approval_allowed=False,
                own_tree_allowed=False,
                seed_fake=True,
            )
        )
    w.db.flush()
    m = QManagementReview(
        id=uuid.uuid4(),
        project_id=ruh.id,
        mrv_no="MRV-RUH-CCH-2026-0001",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        held_on=date(2026, 7, 30),
        chair_user_id=w.u("reem.mutairi"),
        attendee_user_ids=[w.u("saad.anazi"), w.u("lama.qarni"), w.u("imran.siddiq")],
        external_attendees=["Al-Wahat Logistics operations director"],
        inputs={
            k: {
                "note": f"Reviewed ({k.replace('_', ' ')}); see the H1 2026 pack.",
                "not_applicable": False,
            }
            for k in MRV_INPUT_KEYS
        },
        outputs=[
            {
                "id": str(uuid.uuid4()),
                "kind": "resource",
                "text": "Add two spare mapping loggers.",
                "owner_user_id": None,
                "due_date": "2026-09-30",
                "ca_id": None,
            },
            {
                "id": str(uuid.uuid4()),
                "kind": "improvement",
                "text": "Reduce dock dwell for chilled receipts below 30 minutes.",
                "owner_user_id": None,
                "due_date": "2026-12-31",
                "ca_id": None,
            },
        ],
        status=QMrvStatus.minutes_issued,
        issued_at=at(date(2026, 8, 3), 12),
        created_by_user_id=w.u("reem.mutairi"),
        seed_fake=True,
    )
    m.kpi_snapshot = qk.snapshot(w.db, ruh, m.period_start, m.period_end)
    w.db.add(m)
    w.db.flush()
    _signoff(
        w.db,
        ruh,
        RT.management_review,
        m.id,
        "approve",
        "approved",
        w.u("faisal.harbi"),
        at(date(2026, 8, 3), 12),
        "hse_manager",
    )
    _bump(w.db, ruh, RT.management_review, "MRV", 1)


# ---- suppliers -----------------------------------------------------------------------------------

QX19 = {"M1": "97.50", "M2": "1.20", "M3": "91.00", "M4": "95.80", "M5": "100.00", "M6": None}
SCORES = {"RMX": "72.2", "ARS": "88.4", "LAB-RGM": "91.0", "COOLRD": "66.5", "NDCF": "79.0"}


def _suppliers(w: _W) -> None:
    from app.core.quality.common import QSupplierStatus  # noqa: PLC0415
    from app.core.quality.q4 import (  # noqa: PLC0415
        QScorePeriod,
        QScoreStatus,
        QSevKind,
        QSevMethod,
        QSevRecommendation,
        QSevStatus,
    )
    from app.models.quality import QSupplier  # noqa: PLC0415
    from app.models.quality.q4 import QSupplierEvaluation, QSupplierScore  # noqa: PLC0415
    from app.services.quality.q4 import suppliers as qs  # noqa: PLC0415

    db = w.db
    logistics = {"COOLRD", "SHIELD", "BRIGHT", "NDCF"}
    n = {"ANIA-EXP": 0, "RUH-CCH": 0}
    for s in db.scalars(select(QSupplier).order_by(QSupplier.supplier_code)):
        if s.status not in (QSupplierStatus.approved, QSupplierStatus.conditional):
            continue
        pc = "RUH-CCH" if s.supplier_code in logistics else "ANIA-EXP"
        pr = w.p[pc]
        n[pc] += 1
        crit = [
            {"criterion": "Quality system", "weight": "40", "score": "85"},
            {"criterion": "Technical capability", "weight": "40", "score": "80"},
            {"criterion": "References", "weight": "20", "score": "90"},
        ]
        rec = (
            QSevRecommendation.conditional
            if s.status == QSupplierStatus.conditional
            else QSevRecommendation.approve
        )
        e = QSupplierEvaluation(
            id=uuid.uuid4(),
            project_id=pr.id,
            sev_no=f"SEV-{pr.code}-2026-{n[pc]:04d}",
            supplier_id=s.id,
            kind=QSevKind.initial,
            method=QSevMethod.document_review,
            criteria=crit,
            total=qs.total_of(crit),
            recommendation=rec,
            evaluated_at=date(2026, 1, 15),
            submitted_at=at(date(2026, 1, 15)),
            submitted_by_user_id=w.u("bilal.qureshi" if pc == "ANIA-EXP" else "imran.siddiq"),
            approved_at=at(date(2026, 1, 20)),
            approved_date=date(2026, 1, 20),
            next_evaluation_due=date(2027, 1, 19),
            status=QSevStatus.approved,
            created_by_user_id=w.u("bilal.qureshi" if pc == "ANIA-EXP" else "imran.siddiq"),
            seed_fake=True,
        )
        db.add(e)
        s.next_evaluation_due = date(2027, 1, 19)
        _signoff(
            db,
            pr,
            RT.supplier_evaluation,
            e.id,
            "approve",
            "approved",
            w.u("hatem.shehri" if pc == "ANIA-EXP" else "reem.mutairi"),
            at(date(2026, 1, 20)),
        )
    for pc, k in n.items():
        _bump(db, w.p[pc], RT.supplier_evaluation, "SEV", k)
    w_, anc, bands, _kind = qs._cfg(db, w.p["ANIA-EXP"].id)
    for code, score in SCORES.items():
        s = w.sup(code)
        if s is None:
            continue
        metrics: dict[str, Any] = {"values": {}, "counts": {}}
        if code == "RMX":
            res = qs.score_of({k: D(v) if v else None for k, v in QX19.items()}, w_, anc, bands)
            metrics = {
                "values": QX19,
                "counts": {},
                **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in res.items()},
            }
        band = "A" if D(score) >= 85 else "B" if D(score) >= 70 else "C" if D(score) >= 50 else "D"
        db.add(
            QSupplierScore(
                id=uuid.uuid4(),
                supplier_id=s.id,
                period_kind=QScorePeriod.quarter,
                period_start=date(2026, 7, 1),
                period_end=date(2026, 9, 30),
                metrics=metrics,
                score=D(score),
                band=band,
                recommendation={"A": "keep", "B": "keep", "C": "improvement_plan", "D": "suspend"}[
                    band
                ],
                status=QScoreStatus.final,
                computed_at=at(date(2026, 10, 1)),
                finalised_at=at(date(2026, 10, 1)),
                seed_fake=True,
            )
        )
    db.flush()


# ---- KPI targets, work value, SPC ----------------------------------------------------------------

TARGETS = [
    ("K-141", "90"),
    ("K-146", "85"),
    ("K-148", "0.5"),
    ("K-160", "2"),
    ("K-162", "0.5"),
    ("K-163", "95"),
    ("K-165", "98"),
]


def _targets(w: _W) -> None:
    from app.models.quality.q4 import QKpiTarget, QWorkValue  # noqa: PLC0415

    for pr in w.p.values():
        for k, v in TARGETS:
            w.db.add(
                QKpiTarget(
                    id=uuid.uuid4(),
                    project_id=pr.id,
                    kpi_id=k,
                    target=D(v),
                    valid_from=date(2026, 1, 1),
                    seed_fake=True,
                )
            )
    for month, v in ((8, "45200000.00"), (9, "48500000.00")):
        w.db.add(
            QWorkValue(
                id=uuid.uuid4(),
                project_id=w.p["ANIA-EXP"].id,
                month=date(2026, month, 1),
                value_sar=D(v),
                seed_fake=True,
            )
        )
    w.db.flush()


DEV = [
    0.5,
    -0.3,
    0.2,
    -0.6,
    0.1,
    -0.2,
    0.4,
    -0.5,
    0.3,
    0.1,
    -0.4,
    0.6,
    -0.1,
    0.2,
    -0.3,
    0.5,
    -0.2,
    0.0,
    -0.4,
    0.1,
]
RNG = [
    3.0,
    3.2,
    2.8,
    3.4,
    3.1,
    3.0,
    3.3,
    2.9,
    3.1,
    3.2,
    3.0,
    3.1,
    2.9,
    3.3,
    3.1,
    3.0,
    3.2,
    3.1,
    3.0,
    3.2,
]


def qx22_sets() -> list[list[float]]:
    """20 subgroups of n = 3 with X̿ = 46.80 and R̄ = 3.10 exactly (QX22)."""
    dev = list(DEV)
    dev[-1] -= round(sum(dev), 6)
    rng = list(RNG)
    rng[-1] += round(62.0 - sum(rng), 6)
    return [
        [round(46.8 + d - r / 2, 2), round(46.8 + d, 2), round(46.8 + d + r / 2, 2)]
        for d, r in zip(dev, rng, strict=True)
    ]


def _spc(w: _W) -> None:
    from app.core.quality.q4 import QSpcBaseline, QSpcSource, QSpcType  # noqa: PLC0415
    from app.models import Zone  # noqa: PLC0415
    from app.models.quality.q2 import QTestSpecimen  # noqa: PLC0415
    from app.models.quality.q4 import QSpcChart  # noqa: PLC0415
    from app.seed_quality_q2 import _Ctx, _test  # noqa: PLC0415

    db = w.db
    ania, ruh = w.p["ANIA-EXP"], w.p["RUH-CCH"]
    c = _Ctx(db)
    tt = c.tt("CONC-CYL")
    from app.models.quality.q2 import QTestRequest  # noqa: PLC0415

    ref = db.scalar(
        select(QTestRequest)
        .where(QTestRequest.project_id == ania.id, QTestRequest.test_type_code == "CONC-CYL")
        .limit(1)
    )
    mix = ref.mix_key if ref is not None else "C40"
    rawabi = c.eng(ania, "RAWABI")
    for i, vals in enumerate(qx22_sets()):
        cast = date(2026, 3, 2) + timedelta(days=7 * i)
        t = _test(
            c,
            ania,
            433 + i,
            tt,
            "CONC-ACI-40",
            cast,
            site="S-LAND",
            loc=f"Pier B grid {i + 1}",
            eng=rawabi,
            values=["30.5", "31.0", f"{vals[0]:.2f}", f"{vals[1]:.2f}"],
            mix_key=mix,
        )
        spare = db.scalar(
            select(QTestSpecimen).where(
                QTestSpecimen.test_request_id == t.id, QTestSpecimen.spare.is_(True)
            )
        )
        if spare is not None:
            spare.spare, spare.age_days = False, 28
            spare.due_on = spare.tested_on = cast + timedelta(days=28)
            spare.values = {"strength": f"{vals[2]:.2f}"}
    _bump(db, ania, RT.test_request, "TST", 452)
    frz = db.scalar(select(Zone.id).where(Zone.project_id == ruh.id, Zone.code == "Z-FRZ1"))
    rows = [
        (
            ania,
            "C40-STRENGTH",
            "C40 cylinder strength (28 d)",
            "مقاومة أسطوانات C40 (28 يوماً)",
            QSpcType.xbar_r,
            QSpcSource.conc_strength_28d,
            {"mix": "C40"},
            3,
            D("40"),
            None,
            "rania.zahrani",
        ),
        (
            ania,
            "IR-REJECT-WK",
            "IR rejection by week",
            "رفض طلبات الفحص أسبوعياً",
            QSpcType.p,
            QSpcSource.ir_rejection_weekly,
            {},
            None,
            None,
            None,
            "bilal.qureshi",
        ),
        (
            ruh,
            "RCV-REJECT-WK",
            "Receiving rejection by week",
            "رفض الاستلام أسبوعياً",
            QSpcType.p,
            QSpcSource.receiving_rejection_weekly,
            {},
            None,
            None,
            None,
            "reem.mutairi",
        ),
        (
            ruh,
            "FRZ1-DAILY",
            "Z-FRZ1 daily mean temperature",
            "متوسط حرارة Z-FRZ1 اليومي",
            QSpcType.imr,
            QSpcSource.zone_daily_mean_temp,
            {"zone_id": str(frz)},
            None,
            None,
            D("-18"),
            "reem.mutairi",
        ),
    ]
    for pr, code, en, ar, typ, src, flt, n, lsl, usl, owner in rows:
        db.add(
            QSpcChart(
                id=uuid.uuid4(),
                project_id=pr.id,
                code=code,
                title_en=en,
                title_ar=ar,
                chart_type=typ,
                source=src,
                filters=flt,
                subgroup_size=n,
                baseline=QSpcBaseline.rolling,
                baseline_keys=[],
                lsl=lsl,
                usl=usl,
                owner_user_id=w.u(owner),
                active=True,
                signals_sent=[],
                seed_fake=True,
            )
        )
    db.flush()


# ---- consolidation (§E.10) -----------------------------------------------------------------------

Q4_REQS = [
    ("QMS-AWARE", "ISO 9001 awareness", "التوعية بمعيار ISO 9001"),
    ("PQP-BRIEF", "Project Quality Plan briefing", "إحاطة خطة الجودة للمشروع"),
    ("ITP-IR-PROC", "ITP and inspection request procedure", "إجراء خطط الفحص وطلبات الفحص"),
    ("NCR-PROC", "NCR and CAPA procedure", "إجراء تقارير عدم المطابقة والإجراءات التصحيحية"),
    ("PDPL-AWARE", "Personal data protection awareness", "التوعية بحماية البيانات الشخصية"),
    ("SBC-INTRO", "Saudi Building Code introduction", "مقدمة في كود البناء السعودي"),
]


def _competence(w: _W) -> None:
    """K-155 ANIA-EXP at 2026-09-30: 64 pairs, 60 met (A.4). Six construction requirements for
    every quality person (8 × 6 = 48), one lead-auditor requirement for Hatem, and the evidence
    the Q2 seed lacks (Bilal ISO9001-IA, Arun CONC-FIELD-TECH, NDT-UT level 2 for the three
    inspectors); still not met: CWI for Joseph and Mazen, NDT-RT for Joseph and Arun."""
    from app.core.quality.common import QProfileScope  # noqa: PLC0415
    from app.core.train_enums import CourseCategory  # noqa: PLC0415
    from app.models import TrainingCourse  # noqa: PLC0415
    from app.models.quality.q2 import QCompetenceReq  # noqa: PLC0415
    from app.seed_quality_q2 import ensure_worker, personnel_cert, training_record  # noqa: PLC0415

    db = w.db
    ania = w.p["ANIA-EXP"]
    people = [
        "hatem.shehri",
        "bilal.qureshi",
        "joseph.mathew.qc",
        "abdullah.dossary",
        "sultan.mutlaq",
        "arun.pillai",
        "rania.zahrani",
        "mazen.harbi",
    ]
    reqs: list[tuple[str, str, str, list[str], dict[str, Any]]] = [
        (*r, ["other"], {}) for r in Q4_REQS
    ]
    reqs.append(
        (
            "ISO9001-LA",
            "ISO 9001 lead auditor",
            "مدقق رئيسي ISO 9001",
            ["auditor"],
            {"user_ids": [str(w.u("hatem.shehri"))]},
        )
    )
    for code, en, ar, applies, flt in reqs:
        if db.scalar(select(TrainingCourse.id).where(TrainingCourse.code == code)) is None:
            db.add(
                TrainingCourse(
                    code=code,
                    name_en=en,
                    name_ar=ar,
                    category=CourseCategory.professional_qualification,
                    validity_months=36,
                    delivery_modes=[],
                    prerequisite_codes=[],
                    satisfies=[],
                    accreditation_bodies_required=[],
                    languages_offered=["en", "ar"],
                    active=True,
                    seeded=True,
                )
            )
        if db.scalar(select(QCompetenceReq.id).where(QCompetenceReq.code == code)) is None:
            db.add(
                QCompetenceReq(
                    code=code,
                    title_en=en,
                    title_ar=ar,
                    applies_to=applies,
                    filters=flt,
                    any_of=[{"kind": "training_course", "code": code}],
                    all_of=[],
                    policy="inherit",
                    profile=QProfileScope.construction,
                    seed_fake=True,
                )
            )
    db.flush()
    wk = {k: ensure_worker(db, w.u(k)) for k in people}
    for k in people:
        for code, _en, _ar in Q4_REQS:
            training_record(db, wk[k], code, date(2026, 1, 20), date(2029, 1, 19))
    training_record(db, wk["hatem.shehri"], "ISO9001-LA", date(2025, 5, 10), date(2028, 5, 9))
    training_record(db, wk["bilal.qureshi"], "ISO9001-IA", date(2026, 2, 1), date(2029, 1, 31))
    training_record(db, wk["arun.pillai"], "CONC-FIELD-TECH", date(2025, 11, 3), date(2030, 11, 2))
    for k in ("joseph.mathew.qc", "mazen.harbi", "arun.pillai"):
        personnel_cert(db, wk[k], ania.id, "NDT-UT", date(2025, 4, 1), date(2030, 3, 31), "2")
    from app.services.quality.q2 import competence  # noqa: PLC0415

    competence.refresh_cells(db, ania, date(2026, 10, 6))
    db.flush()


def _consolidate(w: _W) -> None:
    from app.core.quality.common import QDetectionStage, QNcrSourceType  # noqa: PLC0415
    from app.core.quality.q2 import QCalKind, QCalRecordStatus  # noqa: PLC0415
    from app.models.quality import QMteItem  # noqa: PLC0415
    from app.models.quality.q2 import QCalibration, QOotItem, QOotReview  # noqa: PLC0415
    from app.seed_quality_q2 import _Ctx, _test  # noqa: PLC0415
    from app.services.quality.q2.calibration import due_on  # noqa: PLC0415

    db = w.db
    ania, ruh = w.p["ANIA-EXP"], w.p["RUH-CCH"]
    c = _Ctx(db)
    # K-152: 212 September test requests with a verdict (the Q2 generator counts the October cores)
    _test(
        c,
        ania,
        432,
        c.tt("SLUMP"),
        "SLUMP-100",
        date(2026, 9, 12),
        site="S-LAND",
        loc="Grid 7",
        eng=c.eng(ania, "RAWABI"),
        results={"slump": "100"},
    )
    # spare mapping loggers MTE-0123 … 0127: calibrated with the March batch (QX: CAL-NMS)
    nms = w.sup("CAL-NMS")
    seq = len(list(db.scalars(select(QCalibration.id).where(QCalibration.project_id == ruh.id))))
    for no in range(123, 128):
        m = db.scalar(
            select(QMteItem).where(
                QMteItem.project_id == ruh.id, QMteItem.mte_no == f"MTE-{no:04d}"
            )
        )
        if m is None or m.last_calibration_id is not None:
            continue
        seq += 1
        cal = QCalibration(
            id=uuid.uuid4(),
            project_id=ruh.id,
            cal_no=f"CAL-RUH-CCH-2026-{seq:04d}",
            mte_id=m.id,
            kind=QCalKind.calibration,
            cal_date=date(2026, 7, 1),
            provider_supplier_id=nms.id if nms else None,
            certificate_no=f"NMS-2026-07-01-MTE-{no:04d}",
            points=[
                {
                    "nominal": str(n),
                    "as_found": str(n),
                    "as_left": None,
                    "tolerance": "0.5",
                    "error": "0.0",
                    "in_tolerance": True,
                    "as_left_in_tolerance": True,
                }
                for n in (-25, 0, 5, 25)
            ],
            as_found_ok=True,
            as_left_ok=True,
            max_found_error=D("0.1"),
            traceability="Traceable to SI [VERIFY] SASO NMCC",
            next_due=due_on(date(2026, 7, 1), m.interval_months or 12),
            decided_at=at(date(2026, 7, 2)),
            decided_by_user_id=w.u("reem.mutairi"),
            status=QCalRecordStatus.accepted,
            created_by_user_id=w.u("imran.siddiq"),
            seed_fake=True,
        )
        db.add(cal)
        db.flush()
        m.last_calibration_id, m.cal_due_on = cal.id, cal.next_due
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, ruh, RT.calibration, 2026, seq)
    # QX11: the OOT `ncr` decision opened a receiving NCR (source oot_review), not the yoghurt NCR
    rv = db.scalar(select(QOotReview).where(QOotReview.oot_no == "OOT-RUH-CCH-2026-0003"))
    n30 = w.ncr(ruh, "NCR-RUH-CCH-2026-0030")
    if rv is not None and n30 is not None:
        for it in db.scalars(
            select(QOotItem).where(QOotItem.review_id == rv.id, QOotItem.decision == "ncr")
        ):
            it.ncr_id = n30.id
            it.decided_at = at(date(2026, 9, 15), 10)
        n30.source_type, n30.source_id, n30.source_ref = QNcrSourceType.oot_review, rv.id, rv.oot_no
        n30.detection_stage = QDetectionStage.receiving
        n30.title = (
            "Frozen-line receiving check with out-of-tolerance probe MTE-0042 "
            "(OOT-RUH-CCH-2026-0003)"
        )
        _link(db, ruh, RT.ncr, n30.id, RT.oot_review, rv.id, "raised_from")
    db.flush()


def seed(db: Session) -> None:
    """Seed Q4's Appendix A.7 records and the §E.10 consolidation (idempotent)."""
    from app.models.quality.q4 import QDocument  # noqa: PLC0415

    if db.scalar(select(QDocument.id).limit(1)) is not None:
        return
    w = _W(db)
    if (
        set(w.p) != {"ANIA-EXP", "RUH-CCH"}
        or w.ncr(w.p["ANIA-EXP"], "NCR-ANIA-EXP-2026-0044") is None
    ):
        return
    ensure_templates(db)
    _consolidate(w)
    _competence(w)
    _documents(w)
    procs = _processes(w)
    _audits(w, procs)
    _suppliers(w)
    _targets(w)
    _spc(w)
    _mrv(w)
    db.flush()
