"""Services of package Q3 logistics: receiving, storage and cold chain, stock, recalls, transport
(spec 8-quality Part D).

`register()` plugs Q3 into the Q0 registries (§3.2): record types, NCR sources, open / pending
steps, attachment owners, criteria evaluators, jobs, export datasets, home tiles, the Q3 labels
of `/quality/reference` and the seed. `app.services.quality.ensure_registered` calls it once."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import LABELS, QNcrSourceType, QRecordType
from app.core.quality.q3 import LABELS_Q3
from app.models import Project
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
RT = QRecordType
A = AttachmentOwner


# ---- record types --------------------------------------------------------------------------------


def _adapter(
    model: Any,
    rt: QRecordType,
    ref: str,
    path: str,
    title: Any,
    site: str | None = "site_id",
    date_attr: str | None = None,
    requesters: Any = None,
) -> reg.RecordTypeAdapter:
    def get(db: Session, rid: uuid.UUID) -> Any:
        return db.get(model, rid)

    def scope(db: Session, p: Principal, row: Any) -> bool:
        from app.services.quality.q3 import base as b  # noqa: PLC0415

        if not p.can_see_project(row.project_id):
            return False
        project = db.get(Project, row.project_id)
        return project is not None and b.can_view(
            db, p, project, rt, row.id, getattr(row, site) if site else None
        )

    def rdate(row: Any) -> Any:
        v = getattr(row, date_attr, None) if date_attr else None
        return v.date() if isinstance(v, datetime) else v

    return reg.RecordTypeAdapter(
        get=get,
        project_id=lambda r: r.project_id,
        scope=scope,
        ref=lambda r: getattr(r, ref) or f"{rt.value} (draft)",
        link_path=lambda r: path.format(id=r.id),
        title=title,
        site_id=lambda r: getattr(r, site) if site else None,
        requesters=requesters
        or (lambda _db, r, _s: {u for u in (getattr(r, "created_by_user_id", None),) if u}),
        record_date=rdate,
    )


def _record_types() -> None:
    from app.models.quality.q3 import (  # noqa: PLC0415
        QCycleCount,
        QDamageReport,
        QExcursion,
        QFefoCheck,
        QHold,
        QMappingStudy,
        QRecall,
        QReceipt,
        QReturn,
        QTrip,
    )

    rows = [
        (
            QReceipt,
            RT.receipt,
            "rcv_no",
            "/quality/receiving/{id}",
            lambda r: f"Receipt {r.asn_ref or ''}",
            "site_id",
            "arrived_at",
        ),
        (
            QExcursion,
            RT.excursion,
            "exc_no",
            "/quality/excursions/{id}",
            lambda r: f"{r.kind.value} excursion {r.severity.value}",
            "site_id",
            "started_at",
        ),
        (
            QMappingStudy,
            RT.mapping_study,
            "map_no",
            "/quality/mapping/{id}",
            lambda r: f"Mapping study {r.purpose.value}",
            None,
            "approved_on",
        ),
        (
            QHold,
            RT.hold,
            "hold_no",
            "/quality/holds/{id}",
            lambda r: f"{r.reason.value} hold",
            "site_id",
            "placed_at",
        ),
        (
            QReturn,
            RT.return_,
            "ret_no",
            "/quality/returns/{id}",
            lambda r: f"Return {r.rma_ref or ''}",
            "site_id",
            "received_at",
        ),
        (
            QRecall,
            RT.recall,
            "rcl_no",
            "/quality/recalls/{id}",
            lambda r: f"Recall {r.recall_type.value}",
            "site_id",
            "initiated_at",
        ),
        (
            QDamageReport,
            RT.damage_report,
            "dmg_no",
            "/quality/stock?tab=damage&id={id}",
            lambda r: f"Damage {r.batch}",
            "site_id",
            "reported_at",
        ),
        (
            QFefoCheck,
            RT.fefo_check,
            "check_no",
            "/quality/stock?tab=fefo&id={id}",
            lambda r: f"FEFO {r.picked_batch}",
            "site_id",
            "checked_at",
        ),
        (
            QCycleCount,
            RT.cycle_count,
            "cc_no",
            "/quality/stock?tab=counts&id={id}",
            lambda r: "Cycle count",
            "site_id",
            "counted_at",
        ),
        (
            QTrip,
            RT.trip,
            "trip_no",
            "/quality/transport/{id}",
            lambda r: f"Trip {r.plate_text or ''}",
            "site_id",
            "planned_departure",
        ),
    ]
    for model, rt, ref, path, title, site, dattr in rows:
        reg.register_record_type(rt, _adapter(model, rt, ref, path, title, site, dattr))


# ---- NCR sources ---------------------------------------------------------------------------------


def _stock_check(db: Session, project: Project, sid: uuid.UUID) -> reg.SourceInfo:
    from app.core.quality.common import QDetectionStage, QNcrClass  # noqa: PLC0415
    from app.models.quality.q3 import (  # noqa: PLC0415
        QCycleCount,
        QDamageReport,
        QFefoCheck,
        QProduct,
    )
    from app.services.quality.q3 import base as b  # noqa: PLC0415

    models: tuple[tuple[Any, QRecordType, str], ...] = (
        (QFefoCheck, RT.fefo_check, "check_no"),
        (QDamageReport, RT.damage_report, "dmg_no"),
        (QCycleCount, RT.cycle_count, "cc_no"),
    )
    for model, rt, ref in models:
        row: Any = db.get(model, sid)
        if row is None or row.project_id != project.id:
            continue
        prod = (
            db.get(QProduct, getattr(row, "product_id", None))
            if getattr(row, "product_id", None)
            else None
        )
        return reg.SourceInfo(
            ref=getattr(row, ref),
            title=f"Stock check — {getattr(row, ref)}",
            site_id=row.site_id,
            engagement_id=b.operator_engagement(db, project),
            item_key=f"STK:{prod.sku if prod else rt.value}",
            detection_stage=QDetectionStage.storage,
            requirement_en="Stock quality rules (FEFO, damage, inventory accuracy).",
            requirement_ar="قواعد جودة المخزون.",
            finding_en=f"{rt.value} {getattr(row, ref)}",
            finding_ar=f"{getattr(row, ref)}",
            proposed_class=QNcrClass.minor,
            record_type=rt,
        )
    raise qc.field_err(
        "source_id", "The stock check is not on this project.", "فحص المخزون ليس في المشروع."
    )


def _visible(rt_get: Any) -> Any:
    def visible(db: Session, p: Principal, sid: uuid.UUID) -> bool:
        try:
            rt_get(db, p, sid)
        except Exception:
            return False
        return True

    return visible


def _ncr_sources() -> None:
    from app.services.quality.q3 import (  # noqa: PLC0415
        excursions,
        hygiene,
        recalls,
        receiving,
        returns,
        transport,
    )

    reg.register_ncr_source(
        QNcrSourceType.receipt,
        reg.NcrSource(receiving.ncr_source, visible=_visible(receiving.get_receipt)),
    )
    reg.register_ncr_source(
        QNcrSourceType.excursion,
        reg.NcrSource(
            excursions.ncr_source,
            visible=_visible(excursions.get_exc),
            on_ncr_status=excursions.on_ncr_status,
            close_check=excursions.ncr_close_check,
        ),
    )
    reg.register_ncr_source(QNcrSourceType.stock_check, reg.NcrSource(_stock_check))
    reg.register_ncr_source(
        QNcrSourceType.return_,
        reg.NcrSource(returns.ncr_source, visible=_visible(returns.get_return)),
    )
    reg.register_ncr_source(
        QNcrSourceType.recall,
        reg.NcrSource(recalls.ncr_source, visible=_visible(recalls.get_recall)),
    )
    reg.register_ncr_source(
        QNcrSourceType.trip,
        reg.NcrSource(transport.ncr_source, visible=_visible(transport.get_trip)),
    )
    reg.register_ncr_source(QNcrSourceType.hygiene_pest, reg.NcrSource(hygiene.ncr_source))


# ---- steps ---------------------------------------------------------------------------------------


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    from app.services.quality.q3 import (  # noqa: PLC0415
        excursions,
        holds,
        mapping,
        recalls,
        receiving,
        returns,
        transport,
    )

    out: list[reg.OpenStep] = []
    for mod in (receiving, excursions, mapping, holds, returns, recalls, transport):
        out += mod.open_steps(db, project)
    return out


def pending(db: Session, p: Principal, project_id: uuid.UUID) -> list[reg.PendingStep]:
    from app.services.quality import rpm  # noqa: PLC0415

    project = db.get(Project, project_id)
    if project is None or qc.profile_of(db, project.id) is None:
        return []
    return rpm.pending_from_open(db, p, project, open_steps(db, project))


# ---- attachment owners ---------------------------------------------------------------------------


def _owner(
    getter: Any, cap: Capability, editable: Any, allow_n: bool = False
) -> reg.AttachmentOwnerFn:
    def fn(db: Session, p: Principal, owner_id: uuid.UUID, write: bool) -> tuple[uuid.UUID, bool]:
        from app.services.quality.q3 import base as b  # noqa: PLC0415

        row, project = getter(db, p, owner_id)
        if b.hide_names(p, project.id):
            raise forbidden_error("Photos and files are not shown to the Viewer / Client (P8-3).")
        if write:
            p.ensure_writer()
            g = p.grant(project.id, cap)
            if g is None or (g.scope.value == "responsible" and not allow_n):
                raise forbidden_error()
        return project.id, bool(editable(row))

    return fn


def _import_get(db: Session, p: Principal, bid: uuid.UUID) -> tuple[Any, Project]:
    from app.models.quality.q3 import QImportBatch  # noqa: PLC0415
    from app.services.quality.q3 import base as b  # noqa: PLC0415

    x = db.get(QImportBatch, bid)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, RT.excursion, bid, None)
    project = qc.get_project(db, p, x.project_id)
    b.list_grant(p, project.id)
    return x, project


def _damage_get(db: Session, p: Principal, did: uuid.UUID) -> tuple[Any, Project]:
    from app.models.quality.q3 import QDamageReport  # noqa: PLC0415
    from app.services.quality.q3 import base as b  # noqa: PLC0415

    x = db.get(QDamageReport, did)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, RT.damage_report, did, None)
    project = qc.get_project(db, p, x.project_id)
    b.list_grant(p, project.id)
    return x, project


def _visit_get(db: Session, p: Principal, vid: uuid.UUID) -> tuple[Any, Project]:
    from app.models.quality.q3 import QPestVisit  # noqa: PLC0415
    from app.services.quality.q3 import base as b  # noqa: PLC0415

    x = db.get(QPestVisit, vid)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, RT.excursion, vid, None)
    project = qc.get_project(db, p, x.project_id)
    b.list_grant(p, project.id)
    return x, project


def _attachment_owners() -> None:
    from app.core.quality.q3 import (  # noqa: PLC0415
        QHoldStatus,
        QMappingStatus,
        QRecallStatus,
        QReceiptStatus,
        QReturnStatus,
        QTripStatus,
    )
    from app.services.quality.q3 import (  # noqa: PLC0415
        holds,
        mapping,
        recalls,
        receiving,
        returns,
        transport,
    )

    reg.ATTACHMENT_OWNERS.update(
        {
            A.q_receipt: _owner(
                receiving.get_receipt,
                C.receiving_record,
                lambda r: r.status in (QReceiptStatus.draft, QReceiptStatus.inspected),
            ),
            A.q_import_file: _owner(_import_get, C.reading_record, lambda _r: False),
            A.q_mapping_report: _owner(
                mapping.get_study, C.storage_manage, lambda m: m.status != QMappingStatus.rejected
            ),
            A.q_pest_visit: _owner(_visit_get, C.storage_manage, lambda _v: True),
            A.q_hold: _owner(
                holds.get_hold,
                C.hold_manage,
                lambda h: h.status != QHoldStatus.closed,
                allow_n=True,
            ),
            A.q_damage: _owner(_damage_get, C.stock_record, lambda _d: True),
            A.q_return: _owner(
                returns.get_return, C.stock_record, lambda r: r.status != QReturnStatus.confirmed
            ),
            A.q_recall: _owner(
                recalls.get_recall,
                C.recall_manage,
                lambda r: r.status not in (QRecallStatus.closed, QRecallStatus.cancelled),
            ),
            A.q_trip: _owner(
                transport.get_trip,
                C.transport_record,
                lambda t: t.status not in (QTripStatus.closed, QTripStatus.cancelled),
            ),
            A.q_pod: _owner(
                transport.get_trip, C.transport_record, lambda t: t.status == QTripStatus.dispatched
            ),
        }
    )


# ---- jobs, home tiles, datasets ------------------------------------------------------------------


def _daily(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q3 import holds, mapping, transport  # noqa: PLC0415

    return {
        "mapping_validity": mapping.validity_alerts(db, at),
        "hold_deadlines": holds.deadlines(db, at),
        "transit_data_due": transport.transit_due(db, at),
    }


def _alerts(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q3 import holds, hygiene, stock  # noqa: PLC0415

    return {
        "expired_not_on_hold": stock.expired_alerts(db, at),
        "hygiene_overdue": hygiene.overdue_alerts(db, at),
        "hold_deadlines": holds.deadlines(db, at),
    }


def _weekly(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q3 import holds  # noqa: PLC0415

    return {"hold_ageing": holds.ageing(db, at)}


def _monthly(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.q3 import recalls  # noqa: PLC0415

    return {"mock_recall_due": recalls.mock_due(db, at)}


def home_tiles(db: Session, p: Principal, project: Project) -> list[reg.HomeCount]:
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.core.quality.common import QSectorProfile  # noqa: PLC0415
    from app.core.quality.q3 import EXCURSION_LIVE, QHoldStatus  # noqa: PLC0415
    from app.models.quality.q3 import QExcursion, QHold, QReceiptLine  # noqa: PLC0415
    from app.services.quality.q3 import mapping, stock  # noqa: PLC0415

    if qc.profile_of(db, project.id) != QSectorProfile.logistics:
        return []
    g = p.grant(project.id, C.quality_view)
    if g is None or g.scope.value == "responsible":
        return []
    live = (
        db.scalar(
            select(func.count())
            .select_from(QExcursion)
            .where(
                QExcursion.project_id == project.id,
                QExcursion.transient.is_(False),
                QExcursion.status.in_(list(EXCURSION_LIVE)),
            )
        )
        or 0
    )
    held = (
        db.scalar(
            select(func.count())
            .select_from(QHold)
            .where(QHold.project_id == project.id, QHold.status == QHoldStatus.on_hold)
        )
        or 0
    )
    zone_level = (
        db.scalar(
            select(func.count())
            .select_from(QHold)
            .where(
                QHold.project_id == project.id,
                QHold.status == QHoldStatus.on_hold,
                QHold.zone_level.is_(True),
            )
        )
        or 0
    )
    pend = (
        db.scalar(
            select(func.count())
            .select_from(QReceiptLine)
            .where(QReceiptLine.requested_decision.is_not(None), QReceiptLine.decision.is_(None))
        )
        or 0
    )
    ne = stock._near_expiry(db, project)["items"]
    expired = sum(1 for x in ne if x["kind"] == "expired" and not x["on_hold"])
    unmapped = mapping.pharma_unmapped(db, project)
    out = [
        reg.HomeCount(
            "q3_excursions",
            "Open excursions",
            "انحرافات مفتوحة",
            live,
            "/quality/excursions",
            "danger" if live else "neutral",
        ),
        reg.HomeCount(
            "q3_holds",
            "Holds on hold",
            "حجوزات قائمة",
            held,
            "/quality/holds",
            "warning" if held else "neutral",
        ),
        reg.HomeCount(
            "q3_zone_holds",
            "Zone-level holds without lines",
            "حجوزات منطقة بلا بنود",
            zone_level,
            "/quality/holds",
            "danger" if zone_level else "neutral",
        ),
        reg.HomeCount(
            "q3_receipt_signoffs",
            "Receipt decisions awaiting sign-off",
            "قرارات استلام بانتظار التوقيع",
            pend,
            "/quality/receiving",
            "warning" if pend else "neutral",
        ),
        reg.HomeCount(
            "q3_expired",
            "Expired stock not on hold",
            "مخزون منتهي غير محجوز",
            expired,
            "/quality/stock",
            "danger" if expired else "neutral",
        ),
        reg.HomeCount(
            "q3_near_expiry",
            "Near-expiry lines",
            "بنود قريبة الانتهاء",
            sum(1 for x in ne if x["kind"] == "near_expiry"),
            "/quality/stock",
            "neutral",
        ),
    ]
    if unmapped:
        out.append(
            reg.HomeCount(
                "q3_pharma_unmapped",
                "Medicines zones not mapped",
                "مناطق أدوية غير مدروسة",
                len(unmapped),
                "/quality/mapping",
                "danger",
            )
        )
    return out


def _datasets() -> None:
    from app.core.scorecard_enums import XpMaskMode, XpPdpl  # noqa: PLC0415
    from app.models.quality.q3 import (  # noqa: PLC0415
        QDamageReport,
        QExcursion,
        QFefoCheck,
        QHold,
        QRecall,
        QReceipt,
        QTrip,
    )
    from app.services.scorecard.datasets import Col, Dataset  # noqa: PLC0415

    def ds(
        code: str, en: str, ar: str, model: Any, dattr: str, special: list[Any] | None = None
    ) -> Any:
        return Dataset(
            code,
            "8",
            C.quality_view,
            C.export_quality,
            en,
            ar,
            model=model,
            date_attr=dattr,
            aggregate=True,
            names_cap=C.stock_record,
            special=special or [],
        )

    rows = [
        ds("quality_receipts", "Receiving inspections", "فحوص الاستلام", QReceipt, "arrived_at"),
        ds(
            "quality_excursions",
            "Temperature excursions",
            "الانحرافات الحرارية",
            QExcursion,
            "started_at",
        ),
        ds("quality_holds", "Holds", "الحجوزات", QHold, "placed_at"),
        ds("quality_fefo_checks", "FEFO checks", "فحوص الأقدم انتهاءً", QFefoCheck, "checked_at"),
        ds(
            "quality_damage_reports", "Damage reports", "بلاغات التلف", QDamageReport, "reported_at"
        ),
        ds("quality_recalls", "Recalls", "الاستدعاءات", QRecall, "initiated_at"),
        ds(
            "quality_trips",
            "Transport trips",
            "رحلات النقل",
            QTrip,
            "planned_departure",
            [
                Col(
                    "driver_name",
                    "Driver",
                    "السائق",
                    XpPdpl.personal,
                    C.transport_record,
                    XpMaskMode.omit,
                    False,
                )
            ],
        ),
    ]
    reg.DATASETS.update({d.code: d for d in rows})


def register() -> None:
    """Register Q3's providers (§3.2)."""
    from app import seed_quality_q3  # noqa: PLC0415
    from app.services.quality.q3 import rules  # noqa: PLC0415

    for kind, values in LABELS_Q3.items():
        LABELS.setdefault(kind, {}).update(values)
    _record_types()
    _ncr_sources()
    reg.OPEN_STEPS["Q3"] = open_steps
    reg.PENDING_STEPS["Q3"] = pending
    _attachment_owners()
    rules.register()
    reg.register_job("q3_daily", reg.JobDef("quality_daily", _daily, "Q3"))
    reg.register_job("q3_alerts", reg.JobDef("quality_alerts", _alerts, "Q3"))
    reg.register_job("q3_weekly", reg.JobDef("quality_weekly", _weekly, "Q3"))
    reg.register_job("q3_monthly", reg.JobDef("quality_monthly", _monthly, "Q3"))
    reg.HOME_TILES["Q3"] = home_tiles
    _datasets()
    _ = seed_quality_q3
