"""Quality kinds of the Phase 1 expiring-items list and action panel (spec 8-quality §E.7):
calibration due, WPQ continuity, competence expiry, document review, mapping validity, supplier
re-evaluation and NCR target dates. Only for users who also hold 238 on the project (not scope N);
no person names (references and record titles only)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import API_PREFIX
from app.core.enums import Capability, CapabilityScope, EntityType
from app.core.hse_enums import ExpiringItemKind as K
from app.core.quality.common import NCR_LIVE
from app.models import Project, Zone
from app.models.quality import QMteItem, QNcr, QSupplier
from app.schemas.dashboard import ExpiringItem
from app.services.permissions import Principal


def expiring(
    db: Session, p: Principal, project: Project, day: date, horizon: date, include_overdue: bool
) -> list[ExpiringItem]:
    g = p.grant(project.id, Capability.quality_view)
    if g is None or g.scope == CapabilityScope.responsible:
        return []
    out: list[ExpiringItem] = []

    def keep(d: date | None) -> bool:
        return d is not None and d <= horizon and (include_overdue or d >= day)

    def add(
        kind: K,
        et: EntityType,
        rid: Any,
        ref: str | None,
        en: str,
        ar: str,
        d: date | None,
        path: str,
    ) -> None:
        assert d is not None  # noqa: S101
        out.append(
            ExpiringItem(
                kind=kind,
                entity_type=et,
                entity_id=rid,
                ref=ref,
                title_en=en,
                title_ar=ar,
                due_date=d,
                days_left=(d - day).days,
                engagement=None,
                detail_path=path,
            )
        )

    for m in db.scalars(
        select(QMteItem).where(
            QMteItem.project_id == project.id,
            QMteItem.status == "active",
            QMteItem.check_kind != "none",
        )
    ):
        if keep(m.cal_due_on):
            add(
                K.q_mte_calibration_due,
                EntityType.q_mte,
                m.id,
                m.mte_no,
                f"Calibration due: {m.description}",
                f"استحقاق المعايرة: {m.description}",
                m.cal_due_on,
                f"{API_PREFIX}/quality/mte/{m.id}",
            )
    from app.models.quality.q2 import QCompetenceCell, QWpq  # noqa: PLC0415
    from app.models.quality.q3 import QStorageZone  # noqa: PLC0415
    from app.models.quality.q4 import QDocument, QSupplierEvaluation  # noqa: PLC0415

    for w in db.scalars(select(QWpq).where(QWpq.project_id == project.id, QWpq.status == "active")):
        if keep(w.continuity_until):
            add(
                K.q_wpq_continuity,
                EntityType.q_wpq,
                w.id,
                w.wpq_no,
                f"WPQ continuity ends ({w.process.value})",
                f"انتهاء استمرارية تأهيل اللحام ({w.process.value})",
                w.continuity_until,
                f"{API_PREFIX}/quality/wpqs/{w.id}",
            )
    for c in db.scalars(
        select(QCompetenceCell).where(
            QCompetenceCell.project_id == project.id, QCompetenceCell.state.in_(["met", "expiring"])
        )
    ):
        if keep(c.valid_until):
            add(
                K.q_competence_expiry,
                EntityType.q_settings,
                None,
                c.requirement_code,
                f"Competence {c.requirement_code} expires",
                f"انتهاء الكفاءة {c.requirement_code}",
                c.valid_until,
                f"{API_PREFIX}/projects/{project.id}/quality/competence-matrix",
            )
    for d in db.scalars(
        select(QDocument).where(QDocument.project_id == project.id, QDocument.status == "approved")
    ):
        if keep(d.review_due_on):
            add(
                K.q_document_review,
                EntityType.q_document,
                d.id,
                d.doc_no,
                f"Document review: {d.title_en}",
                f"مراجعة الوثيقة: {d.title_ar or d.title_en}",
                d.review_due_on,
                f"{API_PREFIX}/quality/documents/{d.id}",
            )
    for sz, z in db.execute(
        select(QStorageZone, Zone)
        .join(Zone, Zone.id == QStorageZone.zone_id)
        .where(QStorageZone.project_id == project.id, QStorageZone.active.is_(True))
    ):
        if keep(sz.mapped_until):
            add(
                K.q_mapping_validity,
                EntityType.q_mapping_study,
                None,
                z.code,
                f"Temperature mapping valid until ({z.code})",
                f"صلاحية دراسة التوزيع الحراري ({z.code})",
                sz.mapped_until,
                f"{API_PREFIX}/quality/storage-zones/{z.id}",
            )
    sids = set(
        db.scalars(
            select(QSupplierEvaluation.supplier_id).where(
                QSupplierEvaluation.project_id == project.id
            )
        )
    )
    for s in db.scalars(select(QSupplier).where(QSupplier.id.in_(list(sids)))) if sids else []:
        if keep(s.next_evaluation_due):
            add(
                K.q_supplier_evaluation,
                EntityType.q_supplier,
                s.id,
                s.supplier_code,
                f"Supplier re-evaluation: {s.legal_name_en}",
                f"إعادة تقييم المورد: {s.legal_name_ar}",
                s.next_evaluation_due,
                f"{API_PREFIX}/quality/suppliers/{s.id}",
            )
    for n in db.scalars(
        select(QNcr).where(QNcr.project_id == project.id, QNcr.status.in_(list(NCR_LIVE)))
    ):
        if keep(n.target_close_date):
            add(
                K.q_ncr_target,
                EntityType.q_ncr,
                n.id,
                n.ncr_no,
                f"NCR target close: {n.title}",
                f"موعد إغلاق التقرير: {n.title}",
                n.target_close_date,
                f"{API_PREFIX}/quality/ncrs/{n.id}",
            )
    return out


_: Callable[..., Any] = expiring
