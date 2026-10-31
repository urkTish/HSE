"""Services of package Q2 materials, testing and lab, welding, calibration, competence (spec
8-quality Part C). `register()` plugs Q2 into the shared registries of
`app.services.quality.registry` (§3.2): record types, NCR sources, open / pending steps, attachment
owners, criteria evaluators, the competence provider, jobs, export datasets, seeds and the EN / AR
labels of the Q2 lists; `app.services.quality.ensure_registered` calls it once."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import ApiError
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import LABELS, QNcrSourceType, QRecordType
from app.core.quality.q2 import (
    Q2_LABELS,
    QCalRecordStatus,
    QMarStatus,
    QMirStatus,
    QOotStatus,
    QPqrStatus,
    QQuarantineStatus,
    QTestStatus,
    QWeldStatus,
    QWpqStatus,
    QWpsStatus,
)
from app.models import Project
from app.models.quality import QMteItem
from app.models.quality.q2 import (
    QCalibration,
    QMar,
    QMir,
    QOotReview,
    QPour,
    QPqr,
    QQuarantineItem,
    QTestRequest,
    QWeld,
    QWpq,
    QWps,
)
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm

C = Capability
RT = QRecordType
A = AttachmentOwner


def _getter(model: Any) -> Any:
    def get(db: Session, rid: uuid.UUID) -> Any:
        return db.get(model, rid)

    return get


def _see(fn: Any) -> Any:
    def scope(db: Session, p: Principal, row: Any) -> bool:
        try:
            return bool(fn(db, p, row))
        except ApiError:
            return False

    return scope


def _record_types() -> None:
    from app.services.quality.q2 import (  # noqa: PLC0415
        calibration,
        materials,
        pours,
        testing,
        welding,
    )

    R = reg.RecordTypeAdapter  # noqa: N806
    reg.register_record_type(
        RT.mar,
        R(
            get=_getter(QMar),
            project_id=lambda r: r.project_id,
            scope=_see(materials.mar_can_view),
            ref=lambda r: f"{r.mar_no or 'MAR (draft)'} Rev.{r.revision}",
            link_path=lambda r: f"/quality/materials/{r.id}",
            title=lambda r: r.title_en,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda _db, r, _s: {
                u for u in (r.created_by_user_id, r.submitted_by_user_id) if u
            },
            voided=lambda r: r.status == QMarStatus.withdrawn,
            record_date=lambda r: r.submitted_at.date() if r.submitted_at else None,
        ),
    )
    reg.register_record_type(
        RT.mir,
        R(
            get=_getter(QMir),
            project_id=lambda r: r.project_id,
            scope=_see(materials.mir_can_view),
            ref=lambda r: r.mir_no or "MIR (draft)",
            link_path=lambda r: f"/quality/material-inspections/{r.id}",
            title=lambda r: r.material_description,
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda _db, r, _s: {
                u for u in (r.created_by_user_id, r.submitted_by_user_id) if u
            },
            voided=lambda r: r.status == QMirStatus.cancelled,
        ),
    )
    reg.register_record_type(
        RT.quarantine,
        R(
            get=_getter(QQuarantineItem),
            project_id=lambda r: r.project_id,
            scope=_see(materials.q_can_view),
            ref=lambda r: r.tag_no,
            link_path=lambda r: f"/quality/quarantine/{r.id}",
            title=lambda r: r.material_description,
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda db, r, _s: set(materials.q_ctx(db, r).requesters),
            record_date=lambda r: r.quarantined_on,
        ),
    )
    reg.register_record_type(
        RT.test_request,
        R(
            get=_getter(QTestRequest),
            project_id=lambda r: r.project_id,
            scope=_see(testing.can_view),
            ref=lambda r: r.test_no,
            link_path=lambda r: f"/quality/tests/{r.id}",
            title=lambda r: f"{r.test_type_code} — {r.location_ref}",
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda _db, r, _s: set(testing.ctx(r).requesters),
            voided=lambda r: r.status == QTestStatus.voided,
            record_date=lambda r: r.cast_date,
        ),
    )
    reg.register_record_type(
        RT.pour,
        R(
            get=_getter(QPour),
            project_id=lambda r: r.project_id,
            scope=_see(pours.can_view),
            ref=lambda r: r.pour_no,
            link_path=lambda r: f"/quality/pours/{r.id}",
            title=lambda r: r.element,
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            voided=lambda r: r.status.value == "cancelled",
            record_date=lambda r: r.started_at.date() if r.started_at else r.planned_on,
        ),
    )

    def _wscope(db: Session, p: Principal, r: Any) -> bool:
        return p.can_see_project(r.project_id) and any(
            p.grant(r.project_id, c) is not None
            for c in (C.quality_view, C.welding_record, C.welding_approve)
        )

    reg.register_record_type(
        RT.wps,
        R(
            get=_getter(QWps),
            project_id=lambda r: r.project_id,
            scope=_wscope,
            ref=lambda r: f"{r.wps_no} Rev.{r.revision}",
            link_path=lambda r: f"/quality/welding?tab=wps&id={r.id}",
            title=lambda r: r.wps_no,
            requesters=lambda _db, r, _s: {
                u for u in (r.created_by_user_id, r.submitted_by_user_id) if u
            },
            voided=lambda r: r.status == QWpsStatus.withdrawn,
        ),
    )
    reg.register_record_type(
        RT.pqr,
        R(
            get=_getter(QPqr),
            project_id=lambda r: r.project_id,
            scope=_wscope,
            ref=lambda r: r.pqr_no,
            link_path=lambda r: f"/quality/welding?tab=pqr&id={r.id}",
            title=lambda r: r.pqr_no,
            requesters=lambda _db, r, _s: {r.created_by_user_id} - {None},
        ),
    )
    reg.register_record_type(
        RT.wpq,
        R(
            get=_getter(QWpq),
            project_id=lambda r: r.project_id,
            scope=_wscope,
            ref=lambda r: r.wpq_no or "WPQ (draft)",
            link_path=lambda r: f"/quality/welding?tab=wpq&id={r.id}",
            title=lambda r: f"{r.process.value} WPQ",
            requesters=lambda _db, r, _s: {r.created_by_user_id} - {None},
            voided=lambda r: r.status == QWpqStatus.revoked,
        ),
    )
    reg.register_record_type(
        RT.weld,
        R(
            get=_getter(QWeld),
            project_id=lambda r: r.project_id,
            scope=_see(welding.weld_can_view),
            ref=lambda r: r.joint_id,
            link_path=lambda r: f"/quality/welding/welds/{r.id}",
            title=lambda r: f"Weld {r.joint_id}",
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda _db, r, _s: {r.created_by_user_id} - {None},
            voided=lambda r: r.status == QWeldStatus.voided,
            record_date=lambda r: r.welded_on,
        ),
    )

    def _cal_scope(db: Session, p: Principal, r: Any) -> bool:
        m = db.get(QMteItem, r.mte_id)
        return (
            m is not None
            and p.can_see_project(r.project_id)
            and any(
                p.grant(r.project_id, c) is not None
                for c in (C.quality_view, C.mte_manage, C.calibration_decide)
            )
        )

    reg.register_record_type(
        RT.calibration,
        R(
            get=_getter(QCalibration),
            project_id=lambda r: r.project_id,
            scope=_cal_scope,
            ref=lambda r: r.cal_no or "CAL (draft)",
            link_path=lambda r: f"/quality/calibration/{r.id}",
            title=lambda r: f"Calibration {r.cal_date.isoformat()}",
            requesters=lambda _db, r, _s: {r.created_by_user_id} - {None},
            voided=lambda r: r.status == QCalRecordStatus.rejected,
            record_date=lambda r: r.cal_date,
        ),
    )
    reg.register_record_type(
        RT.oot_review,
        R(
            get=_getter(QOotReview),
            project_id=lambda r: r.project_id,
            scope=_cal_scope,
            ref=lambda r: r.oot_no,
            link_path=lambda r: f"/quality/calibration/oot/{r.id}",
            title=lambda r: f"OOT review {r.oot_no}",
            record_date=lambda r: r.period_to,
        ),
    )
    _ = calibration


def _sources() -> None:
    from app.services.quality.q2 import calibration, materials, testing, welding  # noqa: PLC0415

    reg.register_ncr_source(
        QNcrSourceType.mir,
        reg.NcrSource(
            materials.mir_source,
            visible=materials.mir_visible,
            close_check=materials.mir_close_check,
        ),
    )
    reg.register_ncr_source(
        QNcrSourceType.test_result, reg.NcrSource(testing.ncr_source, visible=testing.ncr_visible)
    )
    reg.register_ncr_source(
        QNcrSourceType.weld, reg.NcrSource(welding.ncr_source, visible=welding.weld_visible)
    )

    def oot_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
        from app.core.quality.common import QDetectionStage, QNcrClass  # noqa: PLC0415

        r = db.get(QOotReview, source_id)
        if r is None or r.project_id != project.id:
            raise qc.field_err("source_id", "The out-of-tolerance review is not on this project.")
        m = db.get(QMteItem, r.mte_id)
        assert m is not None  # noqa: S101
        return reg.SourceInfo(
            ref=r.oot_no,
            title=f"{r.oot_no}: measurements with {m.mte_no} may be wrong "
            f"(as-found error {r.error_abs})",
            site_id=m.site_id,
            zone_id=m.zone_id,
            engagement_id=m.owner_engagement_id,
            item_key=f"MTE:{m.mte_no}",
            detection_stage=QDetectionStage.in_process,
            requirement_en=(
                f"{m.mte_no} within ±{m.tolerance_value} {m.tolerance_unit or ''}".strip()
            ),
            finding_en=(
                f"As-found error {r.error_abs} on the calibration of {r.period_to.isoformat()}; "
                f"period {r.period_from.isoformat()}…{r.period_to.isoformat()}."
            ),
            proposed_class=QNcrClass.major,
            record_type=RT.oot_review,
        )

    def oot_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
        try:
            calibration.get_review(db, p, rid)
        except ApiError:
            return False
        return True

    reg.register_ncr_source(
        QNcrSourceType.oot_review, reg.NcrSource(oot_source, visible=oot_visible)
    )


def _step(
    rt: QRecordType,
    rid: uuid.UUID,
    project_id: uuid.UUID,
    ref: str,
    title: str,
    step: str,
    since: datetime | None,
    path: str,
) -> reg.PendingStep:
    from app.core.clock import now  # noqa: PLC0415

    return reg.PendingStep(
        rt, rid, project_id, ref, title[:150], step, since or now(), path, part="Q2"
    )


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    """Every Q2 step waiting for a responsible person (Q-RPM-10 / -11)."""
    from app.services.quality.q2 import calibration, materials, testing, welding  # noqa: PLC0415

    out: list[reg.OpenStep] = []
    pid = project.id
    for m in db.scalars(
        select(QMar).where(QMar.project_id == pid, QMar.status == QMarStatus.submitted)
    ):
        c = materials.mar_ctx(m)
        out.append(
            reg.OpenStep(
                _step(
                    RT.mar,
                    m.id,
                    pid,
                    f"{m.mar_no} Rev.{m.revision}",
                    m.title_en,
                    "approve",
                    m.submitted_at,
                    f"/quality/materials/{m.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    for x in db.scalars(
        select(QMir).where(QMir.project_id == pid, QMir.status == QMirStatus.submitted)
    ):
        c = materials.mir_ctx(x)
        out.append(
            reg.OpenStep(
                _step(
                    RT.mir,
                    x.id,
                    pid,
                    x.mir_no or "MIR",
                    x.material_description,
                    "decide",
                    x.submitted_at,
                    f"/quality/material-inspections/{x.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    for q in db.scalars(
        select(QQuarantineItem).where(
            QQuarantineItem.project_id == pid,
            QQuarantineItem.status == QQuarantineStatus.quarantined,
        )
    ):
        c = materials.q_ctx(db, q)
        out.append(
            reg.OpenStep(
                _step(
                    RT.quarantine,
                    q.id,
                    pid,
                    q.tag_no,
                    q.material_description,
                    "dispose",
                    q.created_at,
                    f"/quality/quarantine/{q.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    for t in db.scalars(
        select(QTestRequest).where(
            QTestRequest.project_id == pid,
            QTestRequest.status.in_([QTestStatus.results_entered, QTestStatus.amended]),
        )
    ):
        c = testing.ctx(t)
        out.append(
            reg.OpenStep(
                _step(
                    RT.test_request,
                    t.id,
                    pid,
                    t.test_no,
                    f"{t.test_type_code} {t.location_ref}",
                    "verify",
                    t.results_entered_at,
                    f"/quality/tests/{t.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    for w in db.scalars(
        select(QWps).where(QWps.project_id == pid, QWps.status == QWpsStatus.submitted)
    ):
        c = welding.wps_ctx(w)
        out.append(
            reg.OpenStep(
                _step(
                    RT.wps,
                    w.id,
                    pid,
                    f"{w.wps_no} Rev.{w.revision}",
                    w.wps_no,
                    "approve",
                    w.updated_at,
                    f"/quality/welding?tab=wps&id={w.id}",
                ),
                None,
                None,
                None,
                c.requesters,
            )
        )
    for x in db.scalars(
        select(QPqr).where(QPqr.project_id == pid, QPqr.status == QPqrStatus.draft)
    ):
        out.append(
            reg.OpenStep(
                _step(
                    RT.pqr,
                    x.id,
                    pid,
                    x.pqr_no,
                    x.pqr_no,
                    "approve",
                    x.created_at,
                    f"/quality/welding?tab=pqr&id={x.id}",
                ),
                None,
                None,
                None,
                qc.ids(x.created_by_user_id),
            )
        )
    for x in db.scalars(
        select(QWpq).where(QWpq.project_id == pid, QWpq.status == QWpqStatus.draft)
    ):
        out.append(
            reg.OpenStep(
                _step(
                    RT.wpq,
                    x.id,
                    pid,
                    x.wpq_no or "WPQ",
                    f"{x.process.value} WPQ",
                    "approve",
                    x.created_at,
                    f"/quality/welding?tab=wpq&id={x.id}",
                ),
                None,
                None,
                None,
                qc.ids(x.created_by_user_id),
            )
        )
    for x in db.scalars(
        select(QWeld).where(
            QWeld.project_id == pid, QWeld.status == QWeldStatus.rejected, QWeld.repair_count == 1
        )
    ):
        if welding._awaits_r2(db, x):
            c = welding.weld_ctx(x)
            out.append(
                reg.OpenStep(
                    _step(
                        RT.weld,
                        x.id,
                        pid,
                        x.joint_id,
                        f"Weld {x.joint_id}",
                        "repair2_approve",
                        x.updated_at,
                        f"/quality/welding/welds/{x.id}",
                    ),
                    None,
                    c.site_id,
                    c.engagement_id,
                    c.requesters,
                )
            )
    for cal in db.scalars(
        select(QCalibration).where(
            QCalibration.project_id == pid, QCalibration.status == QCalRecordStatus.draft
        )
    ):
        m = db.get(QMteItem, cal.mte_id)
        c = calibration.ctx(cal, m)
        out.append(
            reg.OpenStep(
                _step(
                    RT.calibration,
                    cal.id,
                    pid,
                    m.mte_no if m else "CAL",
                    f"Calibration {cal.cal_date.isoformat()}",
                    "accept",
                    cal.created_at,
                    f"/quality/calibration/{cal.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    for r in db.scalars(
        select(QOotReview).where(QOotReview.project_id == pid, QOotReview.status == QOotStatus.open)
    ):
        m = db.get(QMteItem, r.mte_id)
        c = calibration.review_ctx(r, m)
        out.append(
            reg.OpenStep(
                _step(
                    RT.oot_review,
                    r.id,
                    pid,
                    r.oot_no,
                    f"OOT review {m.mte_no if m else ''}",
                    "decide",
                    r.created_at,
                    f"/quality/calibration/oot/{r.id}",
                ),
                None,
                c.site_id,
                c.engagement_id,
                c.requesters,
            )
        )
    return out


def pending(db: Session, p: Principal, project_id: uuid.UUID) -> list[reg.PendingStep]:
    project = db.get(Project, project_id)
    if project is None:
        return []
    return rpm.pending_from_open(db, p, project, open_steps(db, project))


# ---- attachment owners (§A.8.7) -----------------------------------------------------------------


def _owner(fetch: Any, write_cap: Capability, *, editable: Any = None) -> Any:
    def fn(db: Session, p: Principal, owner_id: uuid.UUID, write: bool) -> tuple[uuid.UUID, bool]:
        from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

        row, site, eng = fetch(db, p, owner_id)
        if read_only_viewer(p, row.project_id):
            raise forbidden_error("Files are not shown to the Viewer / Client (P8-3).")
        ok = editable(row) if editable else True
        if write:
            p.ensure_writer()
            g = p.grant(row.project_id, write_cap)
            if (
                not p.is_manager
                and not qc.covers(g, site, eng)
                and not (g is not None and g.scope.value == "responsible")
            ):
                raise forbidden_error()
        return row.project_id, ok

    return fn


def _attachments() -> None:
    from app.services.quality import mte  # noqa: PLC0415
    from app.services.quality.q2 import calibration, materials, testing, welding  # noqa: PLC0415

    def mar(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        m = materials.get_mar(db, p, rid)
        return m, None, m.engagement_id

    def mir(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        x = materials.get_mir(db, p, rid)
        return x, x.site_id, x.engagement_id

    def qtn(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        q = materials.get_quarantine(db, p, rid)
        return q, q.site_id, q.engagement_id

    def tst(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        t = testing.get_test(db, p, rid)
        return t, t.site_id, t.engagement_id

    def wps(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        row = db.get(QWps, rid) or db.get(QPqr, rid)  # PQR certificates use the WPS owner type
        if row is None or not p.can_see_project(row.project_id):
            from app.core.errors import not_found  # noqa: PLC0415

            raise not_found("WPS / PQR")
        return row, None, None

    def wpq(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        x = db.get(QWpq, rid)
        if x is None or not p.can_see_project(x.project_id):
            from app.core.errors import not_found  # noqa: PLC0415

            raise not_found("WPQ")
        return x, None, None

    def weld(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        x = welding.get_weld(db, p, rid)
        return x, x.site_id, x.engagement_id

    def cal(db: Session, p: Principal, rid: uuid.UUID) -> Any:
        c = calibration.get_cal(db, p, rid)
        m = mte.get_item(db, p, c.mte_id)
        return c, m.site_id, m.owner_engagement_id

    reg.ATTACHMENT_OWNERS.update(
        {
            A.q_mar: _owner(
                mar, C.material_submit, editable=lambda r: r.status == QMarStatus.draft
            ),
            A.q_mir: _owner(
                mir,
                C.material_submit,
                editable=lambda r: r.status in (QMirStatus.draft, QMirStatus.submitted),
            ),
            A.q_quarantine: _owner(
                qtn, C.material_submit, editable=lambda r: r.status == QQuarantineStatus.quarantined
            ),
            A.q_test_report: _owner(
                tst,
                C.test_record,
                editable=lambda r: r.status not in (QTestStatus.cancelled, QTestStatus.voided),
            ),
            A.q_wps: _owner(wps, C.welding_record),
            A.q_wpq: _owner(wpq, C.welding_record),
            A.q_weld: _owner(
                weld, C.welding_record, editable=lambda r: r.status != QWeldStatus.voided
            ),
            A.q_calibration_cert: _owner(
                cal, C.mte_manage, editable=lambda r: r.status == QCalRecordStatus.draft
            ),
        }
    )


# ---- datasets (Q-WLD-09 weld log export and the Q2 registers) ----------------------------------


def _datasets() -> None:
    from app.services.scorecard.datasets import Dataset  # noqa: PLC0415

    rows = [
        Dataset(
            "quality_tests",
            "8",
            C.quality_view,
            C.export_quality,
            "Test requests",
            "طلبات الاختبار",
            model=QTestRequest,
            date_attr="cast_date",
            aggregate=True,
            names_cap=C.test_record,
        ),
        Dataset(
            "quality_mars",
            "8",
            C.quality_view,
            C.export_quality,
            "Material approval requests",
            "طلبات اعتماد المواد",
            model=QMar,
            aggregate=True,
            names_cap=C.material_submit,
        ),
        Dataset(
            "quality_mirs",
            "8",
            C.quality_view,
            C.export_quality,
            "Material inspections",
            "فحوص المواد الموردة",
            model=QMir,
            aggregate=True,
            names_cap=C.material_submit,
        ),
        Dataset(
            "quality_quarantine",
            "8",
            C.quality_view,
            C.export_quality,
            "Quarantined material",
            "المواد المحجوزة",
            model=QQuarantineItem,
            date_attr="quarantined_on",
            aggregate=True,
            names_cap=C.material_submit,
        ),
        Dataset(
            "quality_pours",
            "8",
            C.quality_view,
            C.export_quality,
            "Concrete pours",
            "الصبّات الخرسانية",
            model=QPour,
            aggregate=True,
            names_cap=C.test_record,
        ),
        Dataset(
            "quality_welds",
            "8",
            C.quality_view,
            C.export_quality,
            "Weld log",
            "سجل اللحام",
            model=QWeld,
            date_attr="welded_on",
            aggregate=True,
            names_cap=C.welding_record,
        ),
        Dataset(
            "quality_wpqs",
            "8",
            C.quality_view,
            C.export_quality,
            "Welder qualifications",
            "تأهيل اللحّامين",
            model=QWpq,
            date_attr="test_date",
            aggregate=True,
            names_cap=C.welding_record,
        ),
        Dataset(
            "quality_calibrations",
            "8",
            C.quality_view,
            C.export_quality,
            "Calibrations",
            "سجلات المعايرة",
            model=QCalibration,
            date_attr="cal_date",
            aggregate=True,
            names_cap=C.mte_manage,
        ),
    ]
    reg.DATASETS.update({d.code: d for d in rows})


# ---- jobs (§4) ----------------------------------------------------------------------------------


def _daily(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q2 import calibration, competence, welding  # noqa: PLC0415

    return {
        "mte_status": calibration.daily_status(db, at),
        "wpq_continuity": welding.continuity_job(db, at),
        "competence_expiry": competence.expiry_alerts(db, at),
    }


def _alerts(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q2 import calibration, materials, testing  # noqa: PLC0415

    return {
        "mte_due": calibration.due_alerts(db, at),
        "oot_overdue": calibration.oot_overdue_alerts(db, at),
        "specimens_overdue": testing.overdue_specimen_alerts(db, at),
        "mar_overdue": materials.mar_overdue_alerts(db, at),
    }


def _weekly(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q2 import materials  # noqa: PLC0415

    return {"quarantine_ageing": materials.ageing_alerts(db, at)}


def register() -> None:
    """Register Q2's providers (§3.2)."""
    from app.services.quality.q2 import calibration, competence, evaluators  # noqa: PLC0415

    LABELS.update(Q2_LABELS)
    _record_types()
    _sources()
    reg.OPEN_STEPS["Q2"] = open_steps
    reg.PENDING_STEPS["Q2"] = pending
    _attachments()
    reg.CRITERIA_EVALUATORS.update(evaluators.EVALUATORS)
    reg.COMPETENCE[0] = competence.check
    reg.register_job("q2_daily", reg.JobDef("quality_daily", _daily, "Q2"))
    reg.register_job("q2_alerts", reg.JobDef("quality_alerts", _alerts, "Q2"))
    reg.register_job("q2_weekly", reg.JobDef("quality_weekly", _weekly, "Q2"))
    _datasets()

    def _seed(db: Session) -> None:
        from app.seed_quality_q2 import seed_after_parts  # noqa: PLC0415

        seed_after_parts(db)

    reg.SEEDS["Q2"] = _seed
    calibration.install_listener()
