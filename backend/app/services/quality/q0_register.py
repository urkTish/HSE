"""Q0's registry entries (spec 8-quality §3.2): record types, NCR sources, open / pending steps,
attachment owners and export datasets of the Q0 records. Called once by
`app.services.quality.ensure_registered()`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.quality.common import (
    QAlertStatus,
    QComplaintStatus,
    QNcrSourceType,
    QObservationStatus,
    QRecordType,
)
from app.models import Project
from app.models.quality import QAlert, QComplaint, QMteItem, QNcr, QObservation, QSupplier
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import files, rpm
from app.services.quality import registry as reg

RT = QRecordType


def _ncr_scope(db: Session, p: Principal, n: QNcr) -> bool:
    from app.services.quality.ncr import core  # noqa: PLC0415

    return p.can_see_project(n.project_id) and core.can_view(db, p, n)


def _obs_scope(db: Session, p: Principal, o: QObservation) -> bool:
    from app.services.quality import observations  # noqa: PLC0415

    return p.can_see_project(o.project_id) and observations.can_view(p, o)


def _alert_scope(db: Session, p: Principal, a: QAlert) -> bool:
    from app.services.quality import alerts  # noqa: PLC0415

    return p.can_see_project(a.project_id) and alerts.can_view(p, a)


def _complaint_scope(db: Session, p: Principal, c: QComplaint) -> bool:
    from app.core.enums import Capability as C  # noqa: PLC0415, N817

    return p.can_see_project(c.project_id) and (
        p.grant(c.project_id, C.complaint_manage) is not None
        or p.grant(c.project_id, C.quality_view) is not None
    )


def _mte_scope(db: Session, p: Principal, m: QMteItem) -> bool:
    from app.core.enums import Capability as C  # noqa: PLC0415, N817

    return p.can_see_project(m.project_id) and (
        p.grant(m.project_id, C.quality_view) is not None
        or p.grant(m.project_id, C.mte_manage) is not None
    )


def _getter(model: Any) -> Any:
    def get(db: Session, rid: uuid.UUID) -> Any:
        return db.get(model, rid)

    return get


def _complaint_open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    for c in db.scalars(
        select(QComplaint).where(
            QComplaint.project_id == project.id,
            QComplaint.status.in_(
                [QComplaintStatus.under_investigation, QComplaintStatus.responded]
            ),
        )
    ):
        step = "response" if c.status == QComplaintStatus.under_investigation else "close"
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.complaint,
                    c.id,
                    c.project_id,
                    c.complaint_no,
                    c.description[:150],
                    step,
                    c.responded_at or c.received_at,
                    f"/quality/complaints/{c.id}",
                ),
                None,
                c.site_id,
                None,
                qc.ids(c.created_by_user_id),
            )
        )
    return out


def _alert_open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    return [
        reg.OpenStep(
            reg.PendingStep(
                RT.quality_alert,
                a.id,
                a.project_id,
                a.alert_no or "QAL",
                a.title_en,
                "issue",
                a.created_at,
                f"/quality/alerts/{a.id}",
            ),
            None,
            None,
            None,
            qc.ids(a.created_by_user_id),
        )
        for a in db.scalars(
            select(QAlert).where(
                QAlert.project_id == project.id, QAlert.status == QAlertStatus.draft
            )
        )
    ]


def _obs_open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    return [
        reg.OpenStep(
            reg.PendingStep(
                RT.observation,
                o.id,
                o.project_id,
                o.obs_no,
                o.description[:150],
                "close",
                o.updated_at,
                f"/quality/observations/{o.id}",
            ),
            None,
            o.site_id,
            o.engagement_id,
            qc.ids(o.raised_by_user_id),
        )
        for o in db.scalars(
            select(QObservation).where(
                QObservation.project_id == project.id,
                QObservation.status == QObservationStatus.actioned,
            )
        )
    ]


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    from app.services.quality.ncr import core  # noqa: PLC0415

    return [
        *core.open_steps(db, project),
        *_complaint_open_steps(db, project),
        *_alert_open_steps(db, project),
        *_obs_open_steps(db, project),
    ]


def pending(db: Session, p: Principal, project_id: uuid.UUID) -> list[reg.PendingStep]:
    project = db.get(Project, project_id)
    if project is None:
        return []
    return rpm.pending_from_open(db, p, project, open_steps(db, project))


def _datasets() -> None:
    from app.core.enums import Capability as C  # noqa: PLC0415, N817
    from app.core.scorecard_enums import XpMaskMode, XpPdpl  # noqa: PLC0415
    from app.services.scorecard.datasets import Col, Dataset  # noqa: PLC0415

    money = [
        Col(k, en, ar, XpPdpl.sensitive, C.ncr_manage, XpMaskMode.omit, True)
        for k, en, ar in (
            ("cost_gross_sar", "Cost SAR", "التكلفة"),
            ("cost_recovered_sar", "Recovered SAR", "المسترد"),
        )
    ]
    rows = [
        Dataset(
            "quality_ncrs",
            "8",
            C.quality_view,
            C.export_quality,
            "Quality NCRs",
            "تقارير عدم المطابقة",
            model=QNcr,
            date_attr="opened_date",
            aggregate=True,
            names_cap=C.ncr_manage,
            where=lambda m: m.status != "draft",
            special=money,
        ),
        Dataset(
            "quality_observations",
            "8",
            C.quality_view,
            C.export_quality,
            "Quality observations",
            "ملاحظات الجودة",
            model=QObservation,
            date_attr="raised_date",
            aggregate=True,
            names_cap=C.ncr_manage,
        ),
        Dataset(
            "quality_complaints",
            "8",
            C.quality_view,
            C.export_quality,
            "Customer complaints",
            "شكاوى العملاء",
            model=QComplaint,
            aggregate=True,
            names_cap=C.complaint_manage,
        ),
        Dataset(
            "quality_mte",
            "8",
            C.quality_view,
            C.export_quality,
            "M&TE register",
            "سجل أجهزة القياس والاختبار",
            model=QMteItem,
            aggregate=True,
            names_cap=C.mte_manage,
        ),
        Dataset(
            "quality_suppliers",
            "8",
            C.quality_view,
            C.export_quality,
            "Suppliers",
            "الموردون",
            model=QSupplier,
            project_required=False,
            names_cap=C.supplier_manage,
            special=[
                Col(k, en, ar, XpPdpl.personal, C.supplier_manage, XpMaskMode.omit, False)
                for k, en, ar in (
                    ("contact_name", "Contact", "جهة الاتصال"),
                    ("contact_mobile", "Mobile", "الجوال"),
                    ("contact_email", "Email", "البريد"),
                )
            ],
        ),
    ]
    reg.DATASETS.update({d.code: d for d in rows})


def register() -> None:
    from app.services.quality.ncr import sources  # noqa: PLC0415

    reg.register_record_type(
        RT.ncr,
        reg.RecordTypeAdapter(
            get=_getter(QNcr),
            project_id=lambda r: r.project_id,
            scope=_ncr_scope,
            ref=lambda r: r.ncr_no or "NCR (draft)",
            link_path=lambda r: f"/quality/ncrs/{r.id}",
            title=lambda r: r.title,
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.responsible_engagement_id,
            requesters=lambda _db, r, _s: {u for u in (r.raised_by_user_id, r.owner_id) if u},
            voided=lambda r: r.status.value == "voided",
            record_date=lambda r: r.opened_date,
        ),
    )
    reg.register_record_type(
        RT.observation,
        reg.RecordTypeAdapter(
            get=_getter(QObservation),
            project_id=lambda r: r.project_id,
            scope=_obs_scope,
            ref=lambda r: r.obs_no,
            link_path=lambda r: f"/quality/observations/{r.id}",
            title=lambda r: r.description[:150],
            site_id=lambda r: r.site_id,
            requesters=lambda _db, r, _s: {r.raised_by_user_id} - {None},
            record_date=lambda r: r.raised_date,
        ),
    )
    reg.register_record_type(
        RT.quality_alert,
        reg.RecordTypeAdapter(
            get=_getter(QAlert),
            project_id=lambda r: r.project_id,
            scope=_alert_scope,
            ref=lambda r: r.alert_no or "QAL (draft)",
            link_path=lambda r: f"/quality/alerts/{r.id}",
            title=lambda r: r.title_en,
            voided=lambda r: r.status.value == "withdrawn",
        ),
    )
    reg.register_record_type(
        RT.complaint,
        reg.RecordTypeAdapter(
            get=_getter(QComplaint),
            project_id=lambda r: r.project_id,
            scope=_complaint_scope,
            ref=lambda r: r.complaint_no,
            link_path=lambda r: f"/quality/complaints/{r.id}",
            title=lambda r: r.description[:150],
            site_id=lambda r: r.site_id,
            voided=lambda r: r.status.value == "withdrawn",
        ),
    )
    reg.register_record_type(
        RT.mte,
        reg.RecordTypeAdapter(
            get=_getter(QMteItem),
            project_id=lambda r: r.project_id,
            scope=_mte_scope,
            ref=lambda r: r.mte_no,
            link_path=lambda r: f"/quality/mte/{r.id}",
            title=lambda r: r.description,
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.owner_engagement_id,
        ),
    )
    reg.register_ncr_source(QNcrSourceType.observation, reg.NcrSource(sources.observation))
    reg.register_ncr_source(QNcrSourceType.complaint, reg.NcrSource(sources.complaint))
    reg.OPEN_STEPS["Q0"] = open_steps
    reg.PENDING_STEPS["Q0"] = pending
    files.register()
    _datasets()
