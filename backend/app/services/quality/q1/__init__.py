"""Services of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Part B).

`register()` plugs Q1 into the Q0 registries (§3.2): record types `itp`, `ir`, `punch_item`,
`dossier`; NCR sources `ir` and `punch_item` (with their close checks); open / pending steps for
"Awaiting my sign-off"; attachment owners `q_itp`, `q_ir_round`, `q_punch`, `q_floor_plan`,
`q_dossier`; `HOLD_CHECKS["itp_point"]` for Q2 pours; the dossier sections; jobs; export datasets;
Quality home counts. `app.services.quality.ensure_registered` calls it once. The Part B seed is
called directly by `app.seed_quality.seed_quality_data` (`app.seed_quality_q1.seed`)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.core.quality.q1  # noqa: F401  (EN / AR labels of the Part B lists, D-327)
from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QDetectionStage, QNcrClass, QNcrSourceType, QRecordType
from app.core.quality.q1 import (
    IR_APPROVED,
    IR_FINAL,
    IR_PENDING,
    PUNCH_LIVE,
    QDossierStatus,
    QIrStatus,
    QItpStatus,
    QPunchStatus,
)
from app.models import Project
from app.models.quality import QNcr
from app.models.quality.q1 import QDossier, QFloorPlan, QIr, QIrRound, QItp, QPunchItem
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm

C = Capability
RT = QRecordType


def _getter(model: Any) -> Any:
    def get(db: Session, rid: uuid.UUID) -> Any:
        return db.get(model, rid)

    return get


# ---- record types ------------------------------------------------------------------------------


def _itp_scope(db: Session, p: Principal, r: QItp) -> bool:
    from app.services.quality.q1 import itp  # noqa: PLC0415

    return p.can_see_project(r.project_id) and itp.can_view(db, p, r)


def _ir_scope(db: Session, p: Principal, r: QIr) -> bool:
    from app.services.quality.q1 import ir  # noqa: PLC0415

    return p.can_see_project(r.project_id) and ir.can_view(db, p, r)


def _punch_scope(db: Session, p: Principal, r: QPunchItem) -> bool:
    from app.services.quality.q1 import punch  # noqa: PLC0415

    return p.can_see_project(r.project_id) and punch.can_view(db, p, r)


def _dossier_scope(db: Session, p: Principal, r: QDossier) -> bool:
    from app.services.quality.q1 import dossier  # noqa: PLC0415

    return p.can_see_project(r.project_id) and dossier.can_view(db, p, r)


def _ir_requesters(db: Session, r: QIr, _step: str) -> set[uuid.UUID]:
    from app.services.quality.q1 import ir  # noqa: PLC0415

    return set(ir.requesters(db, r))


def _record_types() -> None:
    reg.register_record_type(
        RT.itp,
        reg.RecordTypeAdapter(
            get=_getter(QItp),
            project_id=lambda r: r.project_id,
            scope=_itp_scope,
            ref=lambda r: f"{r.itp_no or 'ITP (draft)'} Rev.{r.revision}",
            link_path=lambda r: f"/quality/itps/{r.id}",
            title=lambda r: r.title_en,
            engagement=lambda _db, r: r.engagement_id,
            requesters=lambda _db, r, _s: {
                u for u in (r.prepared_by_user_id, r.submitted_by_user_id) if u
            },
            voided=lambda r: r.status in (QItpStatus.withdrawn, QItpStatus.rejected),
            record_date=lambda r: r.approved_at.date() if r.approved_at else None,
        ),
    )
    reg.register_record_type(
        RT.ir,
        reg.RecordTypeAdapter(
            get=_getter(QIr),
            project_id=lambda r: r.project_id,
            scope=_ir_scope,
            ref=lambda r: r.ir_no or "IR (draft)",
            link_path=lambda r: f"/quality/inspection-requests/{r.id}",
            title=lambda r: f"Points {', '.join(map(str, r.point_seqs or []))} — {r.location_ref}",
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.engagement_id,
            requesters=_ir_requesters,
            voided=lambda r: r.status in IR_FINAL,
            record_date=lambda r: r.decided_date,
        ),
    )
    reg.register_record_type(
        RT.punch_item,
        reg.RecordTypeAdapter(
            get=_getter(QPunchItem),
            project_id=lambda r: r.project_id,
            scope=_punch_scope,
            ref=lambda r: r.punch_no,
            link_path=lambda r: f"/quality/punch/{r.id}",
            title=lambda r: (r.description_en or r.description_ar or "")[:150],
            site_id=lambda r: r.site_id,
            engagement=lambda _db, r: r.responsible_engagement_id,
            requesters=lambda _db, r, _s: {r.ready_by_user_id} - {None},
            voided=lambda r: r.status == QPunchStatus.voided,
            record_date=lambda r: r.raised_date,
        ),
    )
    reg.register_record_type(
        RT.dossier,
        reg.RecordTypeAdapter(
            get=_getter(QDossier),
            project_id=lambda r: r.project_id,
            scope=_dossier_scope,
            ref=lambda r: f"{r.dossier_no} Rev.{r.revision}",
            link_path=lambda r: f"/quality/dossiers/{r.id}",
            title=lambda r: r.title_en,
            requesters=lambda _db, r, _s: {
                u for u in (r.compiled_by_user_id, r.submitted_by_user_id) if u
            },
        ),
    )


# ---- NCR sources (list NS: ir, punch_item) -----------------------------------------------------


def _itp_key(db: Session, ir: QIr) -> str:
    it = db.get(QItp, ir.itp_id)
    short = "-".join((it.itp_no or "").split("-")[-2:]) if it and it.itp_no else "ITP"
    seq = max(ir.point_seqs or [0])
    return f"ITP:{short}:{seq}"


def _ir_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    ir = db.get(QIr, source_id)
    if ir is None or ir.project_id != project.id:
        raise qc.field_err("source_id", "The inspection request is not on this project.")
    it = db.get(QItp, ir.itp_id)
    from app.services.quality.q1 import ir as irs  # noqa: PLC0415

    rnd = irs.current(db, ir)
    finding = (
        rnd.comment if rnd and rnd.comment else None
    ) or f"Round {ir.current_round} rejected."
    req = ", ".join(f"{pt.seq} {pt.characteristic_en}" for pt in irs.points(db, ir))
    return reg.SourceInfo(
        ref=ir.ir_no,
        title=f"{ir.ir_no} rejected — {ir.location_ref}"[:150],
        site_id=ir.site_id,
        zone_id=ir.zone_id,
        system_id=ir.system_id,
        engagement_id=ir.engagement_id,
        item_key=_itp_key(db, ir),
        detection_stage=QDetectionStage.in_process,
        requirement_en=f"{it.itp_no if it else 'ITP'} points: {req}"[:1000],
        finding_en=finding[:2000],
        proposed_class=QNcrClass.minor,
        location_ref=ir.location_ref,
        record_type=RT.ir,
    )


def _ir_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
    r = db.get(QIr, rid)
    return r is not None and _ir_scope(db, p, r)


def _ir_close_check(db: Session, n: QNcr) -> list[reg.Blocker]:
    """Q-NCR-15: an NCR raised from an IR closes once the rework IR is approved (or the IR was
    cancelled / voided)."""
    ir = db.get(QIr, n.source_id) if n.source_id else None
    if ir is None or ir.status in IR_APPROVED or ir.status in IR_FINAL:
        return []
    return [
        reg.Blocker(
            "REWORK_IR_NOT_APPROVED",
            f"The re-inspection of {ir.ir_no} is not approved yet ({ir.status.value}).",
            f"لم تعتمد إعادة فحص {ir.ir_no} بعد.",
        )
    ]


def _punch_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    it = db.get(QPunchItem, source_id)
    if it is None or it.project_id != project.id:
        raise qc.field_err("source_id", "The punch item is not on this project.")
    return reg.SourceInfo(
        ref=it.punch_no,
        title=f"{it.punch_no}: {(it.description_en or it.description_ar or '')}"[:150],
        site_id=it.site_id,
        zone_id=it.zone_id,
        system_id=it.system_id,
        engagement_id=it.responsible_engagement_id,
        item_key=f"PCH:{it.discipline.value}",
        detection_stage=QDetectionStage.final_inspection,
        requirement_en=f"Close {it.punch_no} (category {it.category.value}) to the specification "
        "and drawings before acceptance.",
        requirement_ar=f"إغلاق البند {it.punch_no} وفق المواصفات والمخططات قبل القبول.",
        finding_en=it.description_en,
        finding_ar=it.description_ar,
        proposed_class=QNcrClass.minor,
        location_ref=it.location_ref,
        record_type=RT.punch_item,
    )


def _punch_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
    r = db.get(QPunchItem, rid)
    return r is not None and _punch_scope(db, p, r)


def _punch_close_check(db: Session, n: QNcr) -> list[reg.Blocker]:
    it = db.get(QPunchItem, n.source_id) if n.source_id else None
    if it is None or it.status not in PUNCH_LIVE:
        return []
    return [
        reg.Blocker(
            "PUNCH_ITEM_OPEN",
            f"Punch item {it.punch_no} is still {it.status.value}.",
            f"بند النواقص {it.punch_no} لم يُغلق بعد.",
        )
    ]


# ---- open steps (Q-RPM-10, -11) -----------------------------------------------------------------


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    from app.services.quality.q1 import dossier, ir, itp, punch  # noqa: PLC0415

    out: list[reg.OpenStep] = []
    for it in db.scalars(
        select(QItp).where(QItp.project_id == project.id, QItp.status == QItpStatus.submitted)
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.itp,
                    it.id,
                    it.project_id,
                    itp.display_no(it),
                    it.title_en,
                    "approve",
                    it.submitted_at or it.updated_at,
                    f"/quality/itps/{it.id}",
                    "Q1",
                ),
                None,
                None,
                it.engagement_id,
                itp.requesters(it),
            )
        )
    for r in db.scalars(
        select(QIr).where(QIr.project_id == project.id, QIr.status.in_(list(IR_PENDING)))
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.ir,
                    r.id,
                    r.project_id,
                    r.ir_no or "IR",
                    f"{r.governing_type.value} · {r.location_ref}",
                    "inspect",
                    r.status_changed_at or r.submitted_at or r.updated_at,
                    f"/quality/inspection-requests/{r.id}",
                    "Q1",
                ),
                r.governing_type.value,
                r.site_id,
                r.engagement_id,
                ir.requesters(db, r),
            )
        )
    for pi in db.scalars(
        select(QPunchItem).where(
            QPunchItem.project_id == project.id, QPunchItem.status == QPunchStatus.ready_for_review
        )
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.punch_item,
                    pi.id,
                    pi.project_id,
                    pi.punch_no,
                    (pi.description_en or pi.description_ar or "")[:150],
                    "verify",
                    pi.ready_at or pi.updated_at,
                    f"/quality/punch/{pi.id}",
                    "Q1",
                ),
                None,
                pi.site_id,
                pi.responsible_engagement_id,
                punch.requesters(pi),
            )
        )
    for d in db.scalars(
        select(QDossier).where(
            QDossier.project_id == project.id, QDossier.status == QDossierStatus.submitted
        )
    ):
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT.dossier,
                    d.id,
                    d.project_id,
                    f"{d.dossier_no} Rev.{d.revision}",
                    d.title_en,
                    "accept",
                    d.submitted_at or d.updated_at,
                    f"/quality/dossiers/{d.id}",
                    "Q1",
                ),
                None,
                None,
                None,
                dossier.requesters(d),
            )
        )
    return out


def pending(db: Session, p: Principal, project_id: uuid.UUID) -> list[reg.PendingStep]:
    project = db.get(Project, project_id)
    if project is None:
        return []
    return rpm.pending_from_open(db, p, project, open_steps(db, project))


# ---- attachment owners (§A.8.7) ------------------------------------------------------------------


def _no_viewer(p: Principal, project_id: uuid.UUID) -> None:
    from app.services.quality.q1 import common as q1c  # noqa: PLC0415

    if q1c.viewer(p, project_id):
        raise forbidden_error("Photos and files are not shown to the Viewer / Client (P8-3).")


def _itp_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.q1 import itp  # noqa: PLC0415

    it = itp.get_itp(db, p, owner_id)
    _no_viewer(p, it.project_id)
    if write:
        qc.require_cover(p, it.project_id, C.itp_author, None, it.engagement_id)
    return it.project_id, it.status in itp.EDITABLE_STATES


def _round_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.q1 import ir  # noqa: PLC0415

    rnd = db.get(QIrRound, owner_id)
    if rnd is None:
        raise not_found("Attachment owner")
    r = ir.get_ir(db, p, rnd.ir_id)
    _no_viewer(p, r.project_id)
    if write:
        p.ensure_writer()
        mine = p.user.id == r.requested_by_user_id
        sub = qc.covers(p.grant(r.project_id, C.ir_submit), r.site_id, r.engagement_id)
        insp = (
            p.grant(r.project_id, C.ir_inspect) is not None and p.user.id in (rnd.inspector_id,)
        ) or rpm.resolves(
            db,
            p,
            qc.get_project(db, p, r.project_id),
            RT.ir,
            "inspect",
            ir.ctx(db, r),
            record_id=r.id,
        )
        if not (mine or sub or insp):
            raise forbidden_error()
    # evidence of a decided round stays as signed: files are added while the step is pending
    return r.project_id, (r.status in IR_PENDING or r.status == QIrStatus.draft) and (
        rnd.round_no == r.current_round
    )


def _punch_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.q1 import punch  # noqa: PLC0415

    it = punch.get_item(db, p, owner_id)
    _no_viewer(p, it.project_id)
    if write:
        g = p.grant(it.project_id, C.punch_record) or p.grant(it.project_id, C.punch_verify)
        if g is None:
            raise forbidden_error()
        p.ensure_writer()
    return it.project_id, it.status in PUNCH_LIVE


def _plan_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.q1 import punch  # noqa: PLC0415

    fp = db.get(QFloorPlan, owner_id)
    if fp is None:
        raise not_found("Attachment owner")
    if write:
        raise forbidden_error("Upload plan images through /quality/floor-plans.")
    punch.get_plan(db, p, fp.id)
    return fp.project_id, False


def _dossier_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.q1 import dossier  # noqa: PLC0415

    d = dossier.get_dossier(db, p, owner_id)
    _no_viewer(p, d.project_id)
    if write:
        qc.require_cover(p, d.project_id, C.dossier_compile, None, None)
    elif not dossier._package_reader(db, p, d):
        raise forbidden_error("Dossier files need capability 253 or 254 (Q-DOS-05).")
    return d.project_id, d.status not in (QDossierStatus.accepted, QDossierStatus.submitted)


# ---- datasets, home tiles ------------------------------------------------------------------------


def _datasets() -> None:
    from app.services.scorecard.datasets import Dataset  # noqa: PLC0415

    rows = [
        Dataset(
            "quality_itps",
            "8",
            C.quality_view,
            C.export_quality,
            "Inspection and test plans",
            "خطط الفحص والاختبار",
            model=QItp,
            aggregate=True,
            names_cap=C.itp_author,
        ),
        Dataset(
            "quality_irs",
            "8",
            C.quality_view,
            C.export_quality,
            "Inspection requests",
            "طلبات الفحص",
            model=QIr,
            date_attr="decided_date",
            aggregate=True,
            names_cap=C.ir_submit,
            where=lambda m: m.status != "draft",
        ),
        Dataset(
            "quality_punch",
            "8",
            C.quality_view,
            C.export_quality,
            "Punch items",
            "بنود قائمة النواقص",
            model=QPunchItem,
            date_attr="raised_date",
            aggregate=True,
            names_cap=C.punch_record,
        ),
        Dataset(
            "quality_dossiers",
            "8",
            C.quality_view,
            C.export_quality,
            "Handover dossiers",
            "ملفات التسليم",
            model=QDossier,
            aggregate=True,
            names_cap=C.dossier_compile,
        ),
    ]
    reg.DATASETS.update({d.code: d for d in rows})


def _home(db: Session, p: Principal, project: Project) -> list[reg.HomeCount]:
    from app.core.quality.common import profile_allows  # noqa: PLC0415

    if not profile_allows("construction", qc.profile_of(db, project.id)) and not db.scalar(
        select(QIr.id).where(QIr.project_id == project.id).limit(1)
    ):
        return []
    g = p.grant(project.id, C.quality_view)
    if g is None or g.scope.value == "responsible":
        return []
    day = qc.project_day(project)

    def n(stmt: Any) -> int:
        return int(db.scalar(stmt) or 0)

    return [
        reg.HomeCount(
            "ir_open",
            "Open inspection requests",
            "طلبات فحص مفتوحة",
            n(
                select(func.count())
                .select_from(QIr)
                .where(QIr.project_id == project.id, QIr.status.in_(list(IR_PENDING)))
            ),
            "/quality/inspection-requests",
        ),
        reg.HomeCount(
            "ir_to_schedule",
            "IRs to schedule",
            "طلبات بانتظار الجدولة",
            n(
                select(func.count())
                .select_from(QIr)
                .where(QIr.project_id == project.id, QIr.status == QIrStatus.submitted)
            ),
            "/quality/inspection-requests?status=submitted",
            "warning",
        ),
        reg.HomeCount(
            "punch_open_a",
            "Open punch items, category A",
            "بنود نواقص مفتوحة فئة A",
            n(
                select(func.count())
                .select_from(QPunchItem)
                .where(
                    QPunchItem.project_id == project.id,
                    QPunchItem.status.in_(list(PUNCH_LIVE)),
                    QPunchItem.category == "A",
                )
            ),
            "/quality/punch?category=A",
        ),
        reg.HomeCount(
            "punch_overdue",
            "Overdue punch items",
            "بنود نواقص متأخرة",
            n(
                select(func.count())
                .select_from(QPunchItem)
                .where(
                    QPunchItem.project_id == project.id,
                    QPunchItem.status.in_(list(PUNCH_LIVE)),
                    QPunchItem.target_date < day,
                )
            ),
            "/quality/punch?overdue=true",
            "danger",
        ),
    ]


def register() -> None:
    """Register Q1's providers (§3.2)."""
    from app.services.quality.q1 import dossier, holds, jobs  # noqa: PLC0415

    _record_types()
    reg.register_ncr_source(
        QNcrSourceType.ir,
        reg.NcrSource(_ir_source, visible=_ir_visible, close_check=_ir_close_check),
    )
    reg.register_ncr_source(
        QNcrSourceType.punch_item,
        reg.NcrSource(_punch_source, visible=_punch_visible, close_check=_punch_close_check),
    )
    reg.OPEN_STEPS["Q1"] = open_steps
    reg.PENDING_STEPS["Q1"] = pending
    reg.ATTACHMENT_OWNERS.update(
        {
            AttachmentOwner.q_itp: _itp_owner,
            AttachmentOwner.q_ir_round: _round_owner,
            AttachmentOwner.q_punch: _punch_owner,
            AttachmentOwner.q_floor_plan: _plan_owner,
            AttachmentOwner.q_dossier: _dossier_owner,
        }
    )
    reg.HOLD_CHECKS["itp_point"] = holds.released
    reg.HOLD_POINT_OF_IR["ir"] = holds.hold_point_of
    dossier.register_sections()
    reg.register_job("q1_ir_alerts", reg.JobDef("quality_alerts", jobs.ir_alerts, "Q1"))
    reg.register_job("q1_punch_digest", reg.JobDef("quality_weekly", jobs.punch_digest, "Q1"))
    _datasets()
    reg.HOME_TILES["Q1"] = _home
