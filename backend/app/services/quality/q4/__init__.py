"""Services of package Q4: documents, audits, suppliers, KPIs, SPC, COPQ, AI, report packs (spec
8-quality Part E). `register()` plugs Q4 into the Q0 registries (§3.2): record types (document,
transmittal, quality audit, management review, supplier evaluation), the NCR source
`q_audit_finding`, the supplier approval gate, attachment owners, open steps for "Awaiting me",
jobs, export datasets and Quality home tiles."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QNcrSourceType, QRecordType
from app.models import Project
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
RT = QRecordType
A = AttachmentOwner


def _adapter(
    get: Any,
    ref: Any,
    path: Any,
    title: Any,
    scope: Any,
    rdate: Any = None,
    requesters: Any = None,
    voided: Any = None,
    project_id: Any = None,
) -> reg.RecordTypeAdapter:
    return reg.RecordTypeAdapter(
        get=get,
        project_id=project_id or (lambda r: r.project_id),
        scope=scope,
        ref=ref,
        link_path=path,
        title=title,
        requesters=requesters
        or (lambda _db, r, _s: {u for u in (getattr(r, "created_by_user_id", None),) if u}),
        voided=voided or (lambda _r: False),
        record_date=rdate or (lambda _r: None),
    )


def _try(fn: Any) -> Any:
    def scope(db: Session, p: Principal, row: Any) -> bool:
        try:
            fn(db, p, row)
        except Exception:
            return False
        return True

    return scope


def _record_types() -> None:
    from app.models import FieldAudit  # noqa: PLC0415
    from app.models.quality.q4 import (  # noqa: PLC0415
        QDocument,
        QDocumentRevision,
        QManagementReview,
        QSupplierEvaluation,
        QTransmittal,
    )
    from app.services.quality.q4 import audits, documents, suppliers  # noqa: PLC0415

    def doc_get(db: Session, rid: uuid.UUID) -> Any:
        """A citation names a revision; a sign-off, a revision; a link may name the document."""
        return db.get(QDocumentRevision, rid) or db.get(QDocument, rid)

    def doc_project(r: Any) -> uuid.UUID:
        if isinstance(r, QDocumentRevision):
            return _doc_of(r).project_id  # type: ignore[no-any-return]
        return r.project_id  # type: ignore[no-any-return]

    def doc_ref(r: Any) -> str:
        if isinstance(r, QDocumentRevision):
            return f"{_doc_of(r).doc_no} Rev.{r.rev_code}"
        return str(r.doc_no)

    def doc_title(r: Any) -> str:
        from sqlalchemy.orm import object_session  # noqa: PLC0415

        s = object_session(r)
        if isinstance(r, QDocumentRevision) and s is not None:
            return documents.citation_title(s, r)
        return str(getattr(r, "title_en", ""))

    def doc_scope(db: Session, p: Principal, r: Any) -> bool:
        d = _doc_of(r) if isinstance(r, QDocumentRevision) else r
        return bool(_try(lambda db_, p_, row: documents._get(db_, p_, row.id))(db, p, d))

    reg.register_record_type(
        RT.document,
        _adapter(
            doc_get,
            doc_ref,
            lambda r: (
                f"/quality/documents/{_doc_of(r).id if isinstance(r, QDocumentRevision) else r.id}"
            ),
            doc_title,
            doc_scope,
            project_id=doc_project,
            requesters=lambda _db, r, _s: {
                u
                for u in (
                    getattr(r, "author_user_id", None),
                    getattr(r, "created_by_user_id", None),
                )
                if u
            },
            voided=lambda r: (
                getattr(r, "status", None) is not None and r.status.value == "obsolete"
            ),
        ),
    )
    reg.register_record_type(
        RT.transmittal,
        _adapter(
            lambda db, rid: db.get(QTransmittal, rid),
            lambda r: r.trm_no or "TRM (draft)",
            lambda r: f"/quality/transmittals/{r.id}",
            lambda r: r.subject,
            _try(lambda db, p, r: documents._get_trm(db, p, r.id)),
            rdate=lambda r: r.sent_at.date() if r.sent_at else None,
            voided=lambda r: r.status.value == "cancelled",
        ),
    )

    def audit_get(db: Session, rid: uuid.UUID) -> Any:
        a = db.get(FieldAudit, rid)
        return a if a is not None and a.domain.value == "quality" else None

    reg.register_record_type(
        RT.q_audit,
        _adapter(
            audit_get,
            lambda r: r.audit_no,
            lambda r: f"/quality/audits/{r.id}",
            lambda r: f"{r.audit_type.value.replace('_', ' ')} audit",
            _try(lambda db, p, r: audits._get(db, p, r.id)),
            rdate=lambda r: r.fieldwork_end,
            requesters=lambda _db, r, _s: {r.lead_auditor_id},
            voided=lambda r: r.status.value in ("voided", "cancelled"),
        ),
    )
    reg.register_record_type(
        RT.management_review,
        _adapter(
            lambda db, rid: db.get(QManagementReview, rid),
            lambda r: r.mrv_no or "MRV",
            lambda r: f"/quality/management-reviews/{r.id}",
            lambda r: (
                f"Management review {r.period_start.isoformat()} – {r.period_end.isoformat()}"
            ),
            _try(lambda db, p, r: audits._mrv(db, p, r.id)),
            rdate=lambda r: r.held_on,
        ),
    )
    reg.register_record_type(
        RT.supplier_evaluation,
        _adapter(
            lambda db, rid: db.get(QSupplierEvaluation, rid),
            lambda r: r.sev_no or "SEV (draft)",
            lambda r: f"/quality/supplier-scores?evaluation={r.id}",
            lambda r: f"Supplier evaluation {r.kind.value}",
            _try(lambda db, p, r: suppliers._get(db, p, r.id)),
            rdate=lambda r: r.evaluated_at,
            requesters=lambda _db, r, _s: {
                u for u in (r.created_by_user_id, r.submitted_by_user_id) if u
            },
            voided=lambda r: r.status.value == "cancelled",
        ),
    )


def _doc_of(r: Any) -> Any:
    from sqlalchemy.orm import object_session  # noqa: PLC0415

    from app.models.quality.q4 import QDocument  # noqa: PLC0415

    s = object_session(r)
    assert s is not None  # noqa: S101
    return s.get(QDocument, r.document_id)


def _ncr_sources() -> None:
    from app.services.quality.q4 import audits  # noqa: PLC0415

    reg.register_ncr_source(
        QNcrSourceType.q_audit_finding,
        reg.NcrSource(resolve=audits.finding_source, visible=audits.finding_visible),
    )


# ---- attachments -------------------------------------------------------------------------------


def _owner(getter: Any, cap: Capability, editable: Any) -> reg.AttachmentOwnerFn:
    def fn(db: Session, p: Principal, owner_id: uuid.UUID, write: bool) -> tuple[uuid.UUID, bool]:
        row, project_id = getter(db, p, owner_id)
        if write:
            p.ensure_writer()
            g = p.grant(project_id, cap)
            if g is None or g.scope.value == "responsible":
                raise forbidden_error()
        return project_id, bool(editable(row))

    return fn


def _attachment_owners() -> None:
    from app.models.quality.q4 import QDocumentRevision  # noqa: PLC0415
    from app.services.quality.q4 import audits, documents, suppliers  # noqa: PLC0415

    def rev(db: Session, p: Principal, rid: uuid.UUID) -> tuple[Any, uuid.UUID]:
        r, d = documents._get_rev(db, p, rid)
        return r, d.project_id

    def trm(db: Session, p: Principal, tid: uuid.UUID) -> tuple[Any, uuid.UUID]:
        t = documents._get_trm(db, p, tid)
        return t, t.project_id

    def aud(db: Session, p: Principal, aid: uuid.UUID) -> tuple[Any, uuid.UUID]:
        a = audits._get(db, p, aid)
        return a, a.project_id

    def mrv(db: Session, p: Principal, mid: uuid.UUID) -> tuple[Any, uuid.UUID]:
        m = audits._mrv(db, p, mid)
        return m, m.project_id

    def sev(db: Session, p: Principal, eid: uuid.UUID) -> tuple[Any, uuid.UUID]:
        e = suppliers._get(db, p, eid)
        return e, e.project_id

    _ = QDocumentRevision
    reg.ATTACHMENT_OWNERS.update(
        {
            A.q_document_file: _owner(rev, C.document_author, lambda r: r.status.value == "draft"),
            A.q_transmittal: _owner(trm, C.document_author, lambda t: t.status.value == "draft"),
            A.q_audit_report: _owner(
                aud,
                C.quality_audit_conduct,
                lambda a: a.status.value in ("planned", "in_progress", "fieldwork_complete"),
            ),
            A.q_mgmt_review: _owner(
                mrv, C.quality_audit_conduct, lambda m: m.status.value != "minutes_issued"
            ),
            A.q_supplier_eval: _owner(sev, C.supplier_manage, lambda e: e.status.value == "draft"),
        }
    )


# ---- open steps ("Awaiting my sign-off") --------------------------------------------------------


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    from app.models import FieldAudit  # noqa: PLC0415
    from app.models.quality.q4 import (  # noqa: PLC0415
        QDocument,
        QDocumentRevision,
        QManagementReview,
        QSupplierEvaluation,
    )
    from app.services.quality.q4 import audits, documents, suppliers  # noqa: PLC0415

    out: list[reg.OpenStep] = []
    for r, d in db.execute(
        select(QDocumentRevision, QDocument)
        .join(QDocument, QDocument.id == QDocumentRevision.document_id)
        .where(QDocument.project_id == project.id, QDocumentRevision.status == "for_review")
    ):
        ctx = documents._ctx(r)
        for step in ("review", "approve"):
            out.append(
                reg.OpenStep(
                    reg.PendingStep(
                        RT.document,
                        d.id,
                        project.id,
                        f"{d.doc_no} Rev.{r.rev_code}",
                        d.title_en,
                        step,
                        r.submitted_at or r.created_at,
                        f"/quality/documents/{d.id}",
                        "Q4",
                    ),
                    requesters=ctx.requesters,
                )
            )
    for a in db.scalars(
        select(FieldAudit).where(
            FieldAudit.project_id == project.id,
            FieldAudit.domain == "quality",
            FieldAudit.status == "fieldwork_complete",
        )
    ):
        c = audits._ctx(a)
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.q_audit,
                    a.id,
                    project.id,
                    a.audit_no,
                    "Quality audit report",
                    "issue",
                    a.updated_at,
                    f"/quality/audits/{a.id}",
                    "Q4",
                ),
                site_id=c.site_id,
                engagement_id=c.engagement_id,
                requesters=c.requesters,
            )
        )
    for m in db.scalars(
        select(QManagementReview).where(
            QManagementReview.project_id == project.id, QManagementReview.status == "held"
        )
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.management_review,
                    m.id,
                    project.id,
                    m.mrv_no or "MRV",
                    "Management review minutes",
                    "approve",
                    m.updated_at,
                    f"/quality/management-reviews/{m.id}",
                    "Q4",
                ),
                requesters=audits._mctx(m).requesters,
            )
        )
    for e in db.scalars(
        select(QSupplierEvaluation).where(
            QSupplierEvaluation.project_id == project.id, QSupplierEvaluation.status == "submitted"
        )
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.supplier_evaluation,
                    e.id,
                    project.id,
                    e.sev_no or "SEV",
                    "Supplier evaluation",
                    "approve",
                    e.submitted_at or e.updated_at,
                    "/quality/supplier-scores",
                    "Q4",
                ),
                requesters=suppliers._ctx(e).requesters,
            )
        )
    return out


def pending(db: Session, p: Principal, project_id: uuid.UUID) -> list[reg.PendingStep]:
    from app.services.quality import rpm  # noqa: PLC0415

    project = db.get(Project, project_id)
    if project is None or qc.profile_of(db, project.id) is None:
        return []
    return rpm.pending_from_open(db, p, project, open_steps(db, project))


# ---- jobs, datasets, home tiles -----------------------------------------------------------------


def _daily(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q4 import documents, suppliers  # noqa: PLC0415

    return {**documents.daily(db, at), **suppliers.daily(db, at)}


def _alerts(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q4 import audits, spc  # noqa: PLC0415

    return {**audits.alerts(db, at), **spc.signal_job(db, at)}


def _monthly(db: Session, at: datetime) -> dict[str, Any]:
    """Day 2: E26–E28 of the previous month to 239 holders and QA/QC managers (§E.7), and the
    management review due check (Q-MRV-03)."""
    from app.core.enums import Role  # noqa: PLC0415
    from app.kpi import quality as qk  # noqa: PLC0415
    from app.services.quality.q4 import audits  # noqa: PLC0415
    from app.services.quality.q4 import base as b  # noqa: PLC0415

    n = 0
    for project in db.scalars(select(Project)):
        if qc.profile_of(db, project.id) is None:
            continue
        day = qc.project_day(project, at)
        prev = day.replace(day=1) - timedelta(days=1)
        ws = qk.warnings(db, project, prev)
        if not ws:
            continue
        users = set(qc.holders_of(db, project, C.quality_settings, include_manager=False))
        users |= {a.user_id for a in qc.role_holders(db, project, Role.qa_qc_manager)}
        for w in ws:
            n += b.send(
                db,
                project,
                users,
                f"qwarn:{project.id}:{w['code']}:{w['month']}",
                f"{w['code']} {w['message_en']} — {w['month']}",
                f"{w['code']} {w['message_ar']} — {w['month']}",
                path="/quality/kpis",
                email=True,
            )
    return {"q4_warnings": n, **audits.mrv_due(db, at)}


def _datasets() -> None:
    from app.models import FieldAudit  # noqa: PLC0415
    from app.models.quality.q4 import QDocument, QSupplierScore  # noqa: PLC0415
    from app.services.scorecard.datasets import Dataset  # noqa: PLC0415

    rows = [
        Dataset(
            "quality_documents",
            "8",
            C.quality_view,
            C.export_quality,
            "Controlled documents",
            "الوثائق المضبوطة",
            model=QDocument,
            date_attr="review_due_on",
            aggregate=True,
            names_cap=C.document_author,
        ),
        Dataset(
            "quality_audits",
            "8",
            C.quality_view,
            C.export_quality,
            "Quality audits",
            "تدقيقات الجودة",
            model=FieldAudit,
            date_attr="planned_start",
            aggregate=True,
            names_cap=C.quality_audit_conduct,
            where=lambda m: m.domain == "quality",
        ),
        Dataset(
            "quality_supplier_scores",
            "8",
            C.quality_view,
            C.export_quality,
            "Supplier quality scores",
            "درجات جودة الموردين",
            model=QSupplierScore,
            date_attr="period_start",
            aggregate=True,
            project_required=False,
        ),
    ]
    for d in rows:
        reg.DATASETS[d.code] = d


def home_tiles(db: Session, p: Principal, project: Project) -> list[reg.HomeCount]:
    """Quality home: documents awaiting my acknowledgement and quality audit reports due."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.models.quality.q4 import QDocAck, QDocument, QDocumentRevision  # noqa: PLC0415

    acks = (
        db.scalar(
            select(func.count())
            .select_from(QDocAck)
            .join(QDocumentRevision, QDocumentRevision.id == QDocAck.revision_id)
            .join(QDocument, QDocument.id == QDocumentRevision.document_id)
            .where(
                QDocument.project_id == project.id,
                QDocAck.user_id == p.user.id,
                QDocAck.acked_at.is_(None),
            )
        )
        or 0
    )
    out = [
        reg.HomeCount(
            "q4_my_acks",
            "Documents to acknowledge",
            "وثائق بانتظار إقراري",
            int(acks),
            "/quality/documents?mine=1",
            "warning" if acks else "neutral",
        )
    ]
    g = p.grant(project.id, C.quality_view)
    if g is not None and g.scope.value != "responsible":
        overdue = (
            db.scalar(
                select(func.count())
                .select_from(QDocument)
                .where(
                    QDocument.project_id == project.id,
                    QDocument.status == "approved",
                    QDocument.review_due_on < qc.project_day(project),
                )
            )
            or 0
        )
        out.append(
            reg.HomeCount(
                "q4_docs_review_overdue",
                "Documents past review date",
                "وثائق تجاوزت موعد المراجعة",
                int(overdue),
                "/quality/documents",
                "danger" if overdue else "neutral",
            )
        )
        out.extend(kpi_home_tiles(db, p, project))
    return out


# (user, project, month end, today) → (stored at, tiles): the last complete month changes
# rarely, so the Quality home reuses its KPI tiles for `kpi_cache_seconds` (0 = off, as in the
# test suite; D-370).
_HOME_KPI_CACHE: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}


def _home_kpi_page(
    db: Session, p: Principal, project: Project, end: date, today: date
) -> list[dict[str, Any]]:
    import time  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.kpi import quality_views as qv  # noqa: PLC0415

    ttl = get_settings().kpi_cache_seconds
    key = (p.user.id, project.id, end, today)
    t = time.monotonic()
    if ttl > 0:
        hit = _HOME_KPI_CACHE.get(key)
        if hit is not None and t - hit[0] < ttl:
            return hit[1]
    tiles = list(qv.page(db, p, project, end.replace(day=1), end, today, charts=False)["tiles"])
    if ttl > 0:
        if len(_HOME_KPI_CACHE) > 1024:
            _HOME_KPI_CACHE.clear()
        _HOME_KPI_CACHE[key] = (t, tiles)
    return tiles


def kpi_home_tiles(db: Session, p: Principal, project: Project) -> list[reg.HomeCount]:
    """§E.7: the profile's KPI tiles with RAG for the last complete month, from the same page
    builder as `/quality/kpis` (grant narrowing and hidden tiles included, no charts)."""
    from app.services.quality.q4 import base as b  # noqa: PLC0415

    if qc.profile_of(db, project.id) is None:
        return []
    today = b.today(project)
    end = today.replace(day=1) - timedelta(days=1)
    pg = {"tiles": _home_kpi_page(db, p, project, end, today)}
    tone = {"red": "danger", "amber": "warning", "green": "success"}
    return [
        reg.HomeCount(
            f"kpi-{t['kpi']}",
            f"{t['kpi']} {t['name_en']}",
            f"{t['kpi']} {t['name_ar']}",
            0,
            "/quality/kpis",
            tone.get(t["rag"] or "", "neutral"),
            display=t["display"],
            rag=t["rag"],
        )
        for t in pg["tiles"]
    ]


def register() -> None:
    """Register Q4's providers (§3.2)."""
    from app.services.quality.q4 import suppliers  # noqa: PLC0415

    _record_types()
    _ncr_sources()
    reg.SUPPLIER_GATES.append(suppliers.gate)
    _attachment_owners()
    reg.OPEN_STEPS["Q4"] = open_steps
    reg.PENDING_STEPS["Q4"] = pending
    reg.register_job("q4_daily", reg.JobDef("quality_daily", _daily, "Q4"))
    reg.register_job("q4_alerts", reg.JobDef("quality_alerts", _alerts, "Q4"))
    reg.register_job("q4_monthly", reg.JobDef("quality_monthly", _monthly, "Q4"))
    reg.HOME_TILES["Q4"] = home_tiles
    _datasets()


_ = date
