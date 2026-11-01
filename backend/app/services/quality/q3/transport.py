"""Transport (spec 8-quality §D.9, Q-TRN-01…08): trips with compartments and their strictest
range, incompatible loads, the reefer pre-load check `QRPL` with pre-cooling, loading
temperatures, dispatch with the override of the matrix step `trip.dispatch_override`, the
read-only link to 7b vehicle readiness (never blocking), proofs of delivery, transit
excursions from the trip logger file and the transit-data-due alert."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QDetectionStage, QNcrClass, QRecordType
from app.core.quality.q3 import (
    STORAGE_CLASSES,
    QExcursionKind,
    QExcursionStatus,
    QPodException,
    QReadingTarget,
    QStorageClass,
    QTripStatus,
    incompatible,
)
from app.models import Project, Vehicle, Worker
from app.models.field import ChecklistResponse
from app.models.quality.q3 import QExcursion, QPod, QReading, QShipment, QShipmentLine, QTrip
from app.schemas.hse_common import ApiWarning
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import mte as mte_svc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b
from app.services.quality.q3 import checklists

C = Capability
RT = QRecordType.trip
ST = QTripStatus
A = AttachmentOwner
ORDER = (
    QStorageClass.pharma_2_8,
    QStorageClass.chilled,
    QStorageClass.frozen,
    QStorageClass.dock_controlled,
    QStorageClass.ambient_controlled,
    QStorageClass.dry,
)


def strictest(comp: dict[str, Any]) -> QStorageClass:
    classes = [QStorageClass(c) for c in comp.get("classes") or []]
    for c in ORDER:
        if c in classes:
            return c
    return QStorageClass(comp.get("class") or QStorageClass.chilled)


def ctx(t: QTrip, db: Session | None = None) -> rpm.Ctx:
    who = {t.override_requested_by_user_id}
    if db is not None and t.preload_response_id:
        r = db.get(ChecklistResponse, t.preload_response_id)
        if r is not None:
            who.add(r.inspector_id)
    return rpm.Ctx(site_id=t.site_id, requesters=qc.ids(*who))


def get_trip(db: Session, p: Principal, tid: uuid.UUID) -> tuple[QTrip, Project]:
    t = db.get(QTrip, tid)
    if t is None or not p.can_see_project(t.project_id):
        raise b.not_found(db, p, RT, tid, t.project_id if t else None)
    project = qc.get_project(db, p, t.project_id)

    def steps() -> b.StepList:
        if t.override_requested_at and t.status == ST.preload_checked:
            return [("dispatch_override", ctx(t, db), None)]
        return []

    if not b.can_view(db, p, project, RT, t.id, t.site_id, steps):
        raise b.not_found(db, p, RT, tid, project.id)
    return t, project


def shipments_of(db: Session, t: QTrip) -> list[QShipment]:
    return list(
        db.scalars(
            select(QShipment).where(QShipment.trip_id == t.id).order_by(QShipment.shipment_ref)
        )
    )


def _classes_of(db: Session, s: QShipment) -> set[QStorageClass]:
    return {
        ln.storage_class
        for ln in db.scalars(select(QShipmentLine).where(QShipmentLine.shipment_id == s.id))
        if ln.storage_class
    }


def compute_compartments(
    db: Session, t: QTrip, raw: list[dict[str, Any]], assign: dict[uuid.UUID, str]
) -> list[dict[str, Any]]:
    """Q-TRN-01 and the strictest range per compartment."""
    comps: dict[str, dict[str, Any]] = {}
    for c in raw:
        code = str(c["code"]).strip().upper()
        comps[code] = {
            "code": code,
            "setpoint": str(c["setpoint"]) if c.get("setpoint") is not None else None,
            "interval_minutes": int(c.get("interval_minutes") or 5),
            "classes": [],
        }
    if not comps:
        raise qc.field_err(
            "compartments", "A trip has at least one compartment.", "للرحلة حجرة واحدة على الأقل."
        )
    for sid, code in assign.items():
        if code not in comps:
            raise qc.field_err(
                "shipments",
                f"Compartment {code} is not on the trip.",
                "الحجرة غير موجودة في الرحلة.",
            )
        s = db.get(QShipment, sid)
        if s is None:
            continue
        cls = comps[code]["classes"]
        for k in _classes_of(db, s):
            if k.value not in cls:
                cls.append(k.value)
    for c in comps.values():
        classes = [QStorageClass(x) for x in c["classes"]]
        for i, a in enumerate(classes):
            for z in classes[i + 1 :]:
                if incompatible(a, z):
                    raise qc.err(
                        422,
                        ErrorCode.INCOMPATIBLE_LOAD,
                        f"Compartment {c['code']}: {a.value} and {z.value} cannot share one "
                        "compartment (Q-TRN-01).",
                        f"الحجرة {c['code']}: لا يمكن جمع {a.value} و{z.value} في حجرة واحدة.",
                    )
        lo: Decimal | None = None
        hi: Decimal | None = None
        for k in classes:
            d = STORAGE_CLASSES[k]
            if d.temp_min is not None:
                lo = d.temp_min if lo is None else max(lo, d.temp_min)
            if d.temp_max is not None:
                hi = d.temp_max if hi is None else min(hi, d.temp_max)
        if lo is not None and hi is not None and lo > hi:
            raise qc.err(
                422,
                ErrorCode.INCOMPATIBLE_LOAD,
                f"Compartment {c['code']}: the classes loaded have no common range (Q-TRN-01).",
                f"الحجرة {c['code']}: الفئات المحملة بلا نطاق مشترك.",
            )
        c["range_min"] = str(lo) if lo is not None else None
        c["range_max"] = str(hi) if hi is not None else None
    return list(comps.values())


def readiness(db: Session, t: QTrip) -> tuple[dict[str, Any] | None, list[ApiWarning]]:
    """Q-TRN-04: 7b readiness of a named Phase 2 vehicle and the driver's authorisation, read
    only; never blocks and never creates a 7b record."""
    if t.vehicle_id is None:
        return None, []
    from app.services.site_vehicle import common as sv  # noqa: PLC0415

    v = db.get(Vehicle, t.vehicle_id)
    if v is None or not sv.is_site(v):
        return {"vehicle_no": v.vehicle_no if v else None, "has_7b": False}, []
    day = sv.local_day()
    state, reasons = sv.readiness(db, v, day)
    from app.models.site_vehicle import VehicleCheck  # noqa: PLC0415

    chk = db.scalar(
        select(VehicleCheck).where(VehicleCheck.vehicle_id == v.id, VehicleCheck.check_date == day)
    )
    auth = None
    if t.driver_worker_id is not None:
        auth = sv.covering_auth(db, t.project_id, t.driver_worker_id, v.driver_group, day)
    info = {
        "vehicle_no": v.vehicle_no,
        "has_7b": True,
        "readiness": state.value,
        "reasons": reasons,
        "pre_use_today": None if chk is None else ("passed" if chk.passed else "failed"),
        "driver_authorised": None if t.driver_worker_id is None else auth is not None,
    }
    warnings = []
    if (
        state.value != "ready"
        or (chk is not None and not chk.passed)
        or (t.driver_worker_id is not None and auth is None)
    ):
        warnings.append(
            qc.warning(
                ErrorCode.VEHICLE_NOT_READY,
                f"{v.vehicle_no}: 7b readiness {state.value}"
                + (f" ({', '.join(reasons)})" if reasons else "")
                + ".",
                f"{v.vehicle_no}: جاهزية المركبة {state.value}.",
                "vehicle_id",
            )
        )
    return info, warnings


def _assign(
    db: Session, project: Project, t: QTrip, rows: list[dict[str, Any]]
) -> dict[uuid.UUID, str]:
    out: dict[uuid.UUID, str] = {}
    for r in rows:
        s = db.get(QShipment, r["shipment_id"])
        if s is None or s.project_id != project.id:
            raise qc.field_err(
                "shipments", "A shipment is not on this project.", "شحنة ليست في المشروع."
            )
        if s.trip_id is not None and s.trip_id != t.id:
            raise qc.field_err(
                "shipments", f"{s.shipment_ref} is on another trip.", "الشحنة ضمن رحلة أخرى."
            )
        out[s.id] = str(r.get("compartment") or "C1").strip().upper()
    return out


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.transport_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    if not body.get("shipments"):
        raise qc.field_err("shipments", "Link the shipments of the trip.", "اربط شحنات الرحلة.")
    t = QTrip(
        id=uuid.uuid4(),
        project_id=project.id,
        trip_no=b.number(db, project, RT, body.get("planned_departure")),
        site_id=site.id,
        carrier_id=body.get("carrier_id"),
        own_fleet=bool(body.get("own_fleet")),
        vehicle_id=body.get("vehicle_id"),
        plate_text=body.get("plate_text"),
        reefer_serial=body.get("reefer_serial"),
        driver_worker_id=body.get("driver_worker_id"),
        driver_name=body.get("driver_name"),
        logger_mte_ids=list(body.get("logger_mte_ids") or []),
        seal_numbers=list(body.get("seal_numbers") or []),
        planned_departure=body.get("planned_departure"),
        loading_temps=[],
        preload_failures=[],
        status=ST.planned,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    if t.vehicle_id is not None:
        v = db.get(Vehicle, t.vehicle_id)
        if v is None or v.project_id != project.id:
            raise qc.field_err(
                "vehicle_id", "The vehicle is not on this project.", "المركبة ليست في المشروع."
            )
    if t.driver_worker_id is not None and db.get(Worker, t.driver_worker_id) is None:
        raise qc.field_err("driver_worker_id", "Unknown worker.", "عامل غير معروف.")
    for mid in t.logger_mte_ids:
        b.mte_of(db, project, mid, "logger_mte_ids")
    assign = _assign(db, project, t, body["shipments"])
    t.compartments = compute_compartments(
        db, t, body.get("compartments") or [{"code": "C1"}], assign
    )
    db.add(t)
    db.flush()
    for sid, code in assign.items():
        s = db.get(QShipment, sid)
        assert s is not None  # noqa: S101
        s.trip_id = t.id
        s.compartment = code
    info, warnings = readiness(db, t)
    t.readiness = info
    warnings += b.supplier_warnings(db, t.carrier_id)
    for mid in t.logger_mte_ids:
        _, w = mte_svc.record_usage(
            db, project, mid, RT, t.id, p.user.id, t.planned_departure, "trip logger"
        )
        warnings += w
    b.audit_create(db, p, project, RT, t.id, trip_no=t.trip_no)
    return {**read(db, p, t), "warnings": b.warn_dump(warnings)}


def preload(db: Session, p: Principal, tid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Planned → Preload Checked: the QRPL response, pre-cooling (box temperature within the
    compartment range; frozen ≤ setpoint + 2.0 °C, criterion PRECOOL-FRZ) and loading
    temperatures ≥ 1 per shipment with an M&TE (Q-TRN-02, -03)."""
    t, project = get_trip(db, p, tid)
    _, g = b.project_for_progress(db, p, project.id, C.transport_record)
    b.require_site(g, t.site_id)
    if t.status != ST.planned:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "Only a planned trip.", "رحلة مخططة فقط.")
    out = checklists.respond(
        db,
        p.user.id,
        project,
        ResponseOwnerType.q_trip_preload,
        "reefer_preload",
        t.site_id,
        body["answers"],
        code=body.get("template_code"),
    )
    failures = list(out.critical_failures)
    box = body.get("box_temp_c")
    if box is not None:
        box = Decimal(str(box))
        for comp in t.compartments:
            lo = Decimal(comp["range_min"]) if comp.get("range_min") else None
            hi = Decimal(comp["range_max"]) if comp.get("range_max") else None
            sp = Decimal(comp["setpoint"]) if comp.get("setpoint") else None
            ok = (lo is None or box >= lo) and (hi is None or box <= hi)
            if strictest(comp) == QStorageClass.frozen and sp is not None:
                from app.services.quality.q3 import rules  # noqa: PLC0415

                pv = rules.precool_setpoint(
                    _precool_params(db), {"box_temp_c": box, "setpoint_c": sp}
                )
                ok = ok and pv.verdict.value == "pass"
            if not ok:
                failures.append(f"PRECOOL:{comp['code']}")
    t.preload_box_temp_c = box
    temps = []
    ships = {s.id: s for s in shipments_of(db, t)}
    seen: set[uuid.UUID] = set()
    for lt in body.get("loading_temps") or []:
        sid = uuid.UUID(str(lt["shipment_id"]))
        s = ships.get(sid)
        if s is None:
            raise qc.field_err(
                "loading_temps", "A shipment is not on this trip.", "شحنة ليست في الرحلة."
            )
        if lt.get("mte_id") is None:
            raise qc.err(
                422,
                ErrorCode.MTE_REQUIRED,
                "Each loading temperature needs the instrument used (Q-TRN-03).",
                "كل حرارة تحميل تحتاج الجهاز المستخدم.",
            )
        b.mte_of(db, project, lt["mte_id"])
        comp = next((c for c in t.compartments if c["code"] == s.compartment), t.compartments[0])
        v = Decimal(str(lt["temp_c"]))
        lo = Decimal(comp["range_min"]) if comp.get("range_min") else None
        hi = Decimal(comp["range_max"]) if comp.get("range_max") else None
        ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        if not ok:
            s.stopped = True  # Q-TRN-03: the shipment is stopped (hold proposed)
        mte_svc.record_usage(
            db,
            project,
            lt["mte_id"],
            RT,
            t.id,
            p.user.id,
            None,
            f"loading {s.shipment_ref} {v} °C",
            value=v,
            limit_low=lo,
            limit_high=hi,
            unit="°C",
        )
        temps.append(
            {
                "shipment_id": str(sid),
                "compartment": s.compartment,
                "temp_c": str(v),
                "mte_id": str(lt["mte_id"]),
                "ok": ok,
            }
        )
        seen.add(sid)
    missing = [s.shipment_ref for s in ships.values() if s.id not in seen]
    if missing:
        raise qc.field_err(
            "loading_temps",
            f"Loading temperature missing for: {', '.join(missing)} (Q-TRN-03).",
            "حرارة التحميل ناقصة لبعض الشحنات.",
        )
    t.loading_temps = temps
    t.preload_response_id = out.response.id
    t.preload_passed = not failures
    t.preload_failures = failures
    t.status = ST.preload_checked
    b.audit_status(
        db, p, project, RT, t.id, ST.planned, ST.preload_checked, passed=str(t.preload_passed)
    )
    if failures:
        users = b.resolvers(
            db, project, RT, "dispatch_override", rpm.Ctx(site_id=t.site_id), record_id=t.id
        )
        b.send(
            db,
            project,
            users,
            f"trp:{t.id}:preload_failed",
            f"Pre-load failed: {t.trip_no}",
            f"فشل فحص ما قبل التحميل: {t.trip_no}",
            rt=RT,
            rid=t.id,
            path=f"/quality/transport/{t.id}",
            email=False,
        )
    return read(db, p, t)


def _precool_params(db: Session) -> dict[str, Any]:
    """The published PRECOOL criterion's params (Q-CRT-03: the margin is data)."""
    from app.core.quality.common import QCriterionStatus  # noqa: PLC0415
    from app.models.quality import QCriterion  # noqa: PLC0415

    c = db.scalar(
        select(QCriterion)
        .where(
            QCriterion.rule_code == "precool_setpoint",
            QCriterion.status == QCriterionStatus.published,
        )
        .order_by(QCriterion.version.desc())
        .limit(1)
    )
    return dict(c.params or {}) if c else {"margin": "2.0"}


def override_allowed(t: QTrip) -> bool:
    return all(
        STORAGE_CLASSES[QStorageClass(c)].dispatch_override_allowed
        for comp in t.compartments
        for c in comp.get("classes") or []
    )


def dispatch(db: Session, p: Principal, tid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Preload Checked → Dispatched (Q-TRN-02): a critical failure blocks (PRELOAD_FAILED) unless
    the responsible person of `trip.dispatch_override` overrides with a reason ≥ 20 chars; no
    override for a class with `dispatch_override_allowed` = no (OVERRIDE_NOT_ALLOWED)."""
    t, project = get_trip(db, p, tid)
    project, g = b.project_for_progress(db, p, project.id, C.transport_record, allow_n=True)
    if t.status != ST.preload_checked:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Complete the pre-load check first.",
            "أكمل فحص ما قبل التحميل أولاً.",
        )
    if not t.preload_passed:
        reason = (body.get("override_reason") or "").strip()
        if not reason and not body.get("request_override"):
            raise qc.err(
                422,
                ErrorCode.PRELOAD_FAILED,
                "The pre-load check failed ("
                + ", ".join(t.preload_failures)
                + "); dispatch needs an override by the transport responsible person.",
                "فشل فحص ما قبل التحميل؛ الإرسال يتطلب تجاوزاً من المسؤول.",
                failures=t.preload_failures,
            )
        if not override_allowed(t):
            raise qc.err(
                422,
                ErrorCode.OVERRIDE_NOT_ALLOWED,
                "A loaded class does not allow a dispatch override (medicines 2–8 °C).",
                "إحدى الفئات المحملة لا تسمح بتجاوز منع الإرسال.",
            )
        if body.get("request_override") and not b.resolves(
            db, p, project, RT, t.id, "dispatch_override", ctx(t, db)
        ):
            t.override_requested_at = now()
            t.override_requested_by_user_id = p.user.id
            users = b.resolvers(
                db, project, RT, "dispatch_override", rpm.Ctx(site_id=t.site_id), record_id=t.id
            )
            b.send(
                db,
                project,
                users,
                f"trp:{t.id}:override_req",
                f"Override requested: {t.trip_no}",
                f"طلب تجاوز: {t.trip_no}",
                rt=RT,
                rid=t.id,
                path=f"/quality/transport/{t.id}",
                email=False,
            )
            return read(db, p, t)
        why = qc.reason(reason, 20, "override_reason")
        b.sign(db, p, project, RT, t.id, "dispatch_override", ctx(t, db), comment=why)
        t.override_reason = why
        t.override_by_user_id = p.user.id
    elif g.scope.value == "responsible":
        raise forbidden_error()
    info, warnings = readiness(db, t)
    t.readiness = info
    t.departed_at = body.get("departed_at") or now()
    for s in shipments_of(db, t):
        if not s.stopped:
            s.dispatched_at = s.dispatched_at or t.departed_at
    t.status = ST.dispatched
    b.audit_status(
        db,
        p,
        project,
        RT,
        t.id,
        ST.preload_checked,
        ST.dispatched,
        override=str(bool(t.override_reason)),
    )
    return {**read(db, p, t), "warnings": b.warn_dump(warnings)}


def add_pod(db: Session, p: Principal, tid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    t, project = get_trip(db, p, tid)
    _, g = b.project_for_progress(db, p, project.id, C.transport_record)
    b.require_site(g, t.site_id)
    if t.status != ST.dispatched:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "PODs are recorded on a dispatched trip.",
            "يُسجل إثبات التسليم لرحلة منطلقة.",
        )
    s = db.get(QShipment, body["shipment_id"])
    if s is None or s.trip_id != t.id:
        raise qc.field_err(
            "shipment_id", "The shipment is not on this trip.", "الشحنة ليست في الرحلة."
        )
    if db.scalar(select(QPod.id).where(QPod.shipment_id == s.id)):
        raise qc.field_err("shipment_id", "This shipment already has a POD.", "للشحنة إثبات تسليم.")
    sig = b.attachment_on(
        db, body.get("signature_attachment_id"), A.q_pod, t.id, "signature_attachment_id"
    )
    if sig is None:
        raise qc.field_err(
            "signature_attachment_id",
            "Capture the signature or a photo of the signed delivery note.",
            "التقط التوقيع أو صورة مذكرة التسليم الموقعة.",
        )
    exc = [
        {
            "kind": QPodException(x["kind"]).value,
            "qty": str(x.get("qty")) if x.get("qty") is not None else None,
            "note": x.get("note"),
        }
        for x in body.get("exceptions") or []
    ]
    pod = QPod(
        trip_id=t.id,
        shipment_id=s.id,
        delivered_at=body.get("delivered_at") or now(),
        receiver_name=body["receiver_name"],
        receiver_role=body.get("receiver_role"),
        signature_attachment_id=sig,
        seal_intact=bool(body.get("seal_intact", True)),
        product_temp_c=body.get("product_temp_c"),
        mte_id=body.get("mte_id"),
        exceptions=exc,
        photo_ids=list(body.get("photo_ids") or []),
        recorded_by_user_id=p.user.id,
        created_at=now(),
    )
    if pod.product_temp_c is not None and pod.mte_id is None:
        raise qc.err(
            422,
            ErrorCode.MTE_REQUIRED,
            "A delivery temperature needs the instrument used.",
            "حرارة التسليم تحتاج الجهاز.",
        )
    db.add(pod)
    s.delivered_at = pod.delivered_at
    for ln in db.scalars(select(QShipmentLine).where(QShipmentLine.shipment_id == s.id)):
        if ln.delivered_qty is None:
            short = sum(
                Decimal(x["qty"])
                for x in exc
                if x["kind"] in ("shortage", "refused", "damage") and x["qty"]
            )
            ln.delivered_qty = max(ln.ordered_qty - short, Decimal(0)) if short else ln.ordered_qty
    db.flush()
    out = read(db, p, t)
    if exc:
        out["proposals"] = [
            {
                "kind": "ncr",
                "source_type": "trip",
                "source_id": t.id,
                "shipment_ref": s.shipment_ref,
            }
        ]
    return out


def deliver(db: Session, p: Principal, tid: uuid.UUID) -> dict[str, Any]:
    """Dispatched → Delivered: a POD for every shipment (Q-TRN-06)."""
    t, project = get_trip(db, p, tid)
    _, g = b.project_for_progress(db, p, project.id, C.transport_record)
    b.require_site(g, t.site_id)
    if t.status != ST.dispatched:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Only a dispatched trip.", "رحلة منطلقة فقط."
        )
    pods = {x.shipment_id: x for x in db.scalars(select(QPod).where(QPod.trip_id == t.id))}
    missing = [s.shipment_ref for s in shipments_of(db, t) if not s.stopped and s.id not in pods]
    if missing:
        raise qc.err(
            422,
            ErrorCode.POD_REQUIRED,
            f"Proof of delivery missing for: {', '.join(missing)} (Q-TRN-06).",
            f"إثبات التسليم ناقص للشحنات: {', '.join(missing)}.",
            shipments=missing,
        )
    t.delivered_at = max((x.delivered_at for x in pods.values()), default=now())
    t.status = ST.delivered
    b.audit_status(db, p, project, RT, t.id, ST.dispatched, ST.delivered)
    maybe_close(db, t)
    return read(db, p, t)


def cancel(db: Session, p: Principal, tid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    t, project = get_trip(db, p, tid)
    _, g = b.project_for_progress(db, p, project.id, C.transport_record)
    b.require_site(g, t.site_id)
    if t.status not in (ST.planned, ST.preload_checked):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a planned or pre-load-checked trip.",
            "رحلة مخططة أو مفحوصة فقط.",
        )
    t.cancel_reason = qc.reason(body.get("reason"))
    before = t.status
    t.status = ST.cancelled
    for s in shipments_of(db, t):
        s.trip_id = None
    b.audit_status(db, p, project, RT, t.id, before, ST.cancelled, reason=t.cancel_reason)
    return read(db, p, t)


def has_transit_data(db: Session, t: QTrip) -> bool:
    return (
        db.scalar(
            select(QReading.id)
            .where(
                QReading.target_type == QReadingTarget.trip,
                QReading.target_id == t.id,
                QReading.voided.is_(False),
            )
            .limit(1)
        )
        is not None
    )


def on_transit_data(db: Session, t: QTrip) -> None:
    t.transit_data = has_transit_data(db, t)
    maybe_close(db, t)


def maybe_close(db: Session, t: QTrip) -> None:
    """Delivered → Closed (System): PODs in and, when a logger is named, readings imported."""
    if t.status != ST.delivered:
        return
    if t.logger_mte_ids and not has_transit_data(db, t):
        return
    t.status = ST.closed
    t.closed_at = now()


def transit_due(db: Session, at: datetime) -> int:
    """Q-TRN-07: a trip with a logger and no readings `transit_data_due_hours` after delivery."""
    n = 0
    for t in db.scalars(select(QTrip).where(QTrip.status == ST.delivered)):
        if not t.logger_mte_ids or t.delivered_at is None or has_transit_data(db, t):
            continue
        project = db.get(Project, t.project_id)
        if project is None:
            continue
        hours = int(b.setting(db, project.id, "transit_data_due_hours"))
        if at < t.delivered_at + timedelta(hours=hours):
            continue
        users = b.resolvers(
            db, project, RT, "dispatch_override", rpm.Ctx(site_id=t.site_id), record_id=t.id
        )
        n += b.send(
            db,
            project,
            users,
            f"trp:{t.id}:nodata",
            f"{t.trip_no}: no transit data {hours} h after delivery",
            f"{t.trip_no}: لا توجد بيانات نقل بعد {hours} ساعة من التسليم",
            rt=RT,
            rid=t.id,
            path=f"/quality/transport/{t.id}",
            email=False,
        )
    return n


# ---- NCR source (list NS `trip`) and reads -------------------------------------------------------


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    t = db.get(QTrip, source_id)
    if t is None or t.project_id != project.id:
        raise qc.field_err(
            "source_id", "The trip is not on this project.", "الرحلة ليست في المشروع."
        )
    x = db.scalar(
        select(QExcursion)
        .where(
            QExcursion.trip_id == t.id,
            QExcursion.transient.is_(False),
            QExcursion.status != QExcursionStatus.voided,
        )
        .order_by(QExcursion.severity.desc(), QExcursion.started_at)
        .limit(1)
    )
    finding = (
        f"Transit excursion from {b.local(x.started_at):%Y-%m-%d %H:%M}, {x.duration_min} min, "
        f"peak {x.peak_value} °C ({x.severity.value})."
        if x
        else "Transport finding (pre-load, delivery exception)."
    )
    return reg.SourceInfo(
        ref=t.trip_no,
        title=f"Transport — {t.trip_no}",
        site_id=t.site_id,
        engagement_id=b.operator_engagement(db, project),
        supplier_id=t.carrier_id,
        item_key=f"TRP:{t.carrier_id or 'own'}",
        detection_stage=QDetectionStage.at_customer
        if t.status in (ST.delivered, ST.closed)
        else QDetectionStage.in_process,
        requirement_en="Keep the load within the compartment range in transit (Q-TRN-05).",
        requirement_ar="الحفاظ على الحمولة ضمن نطاق الحجرة أثناء النقل.",
        finding_en=finding,
        finding_ar="انحراف أو استثناء في النقل.",
        proposed_class=QNcrClass(x.severity.value) if x else QNcrClass.minor,
        record_type=RT,
    )


def read(db: Session, p: Principal, t: QTrip) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    project = db.get(Project, t.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, project.id)
    pods = {x.shipment_id: x for x in db.scalars(select(QPod).where(QPod.trip_id == t.id))}
    resp = db.get(ChecklistResponse, t.preload_response_id) if t.preload_response_id else None
    excs = list(
        db.scalars(
            select(QExcursion)
            .where(QExcursion.trip_id == t.id, QExcursion.status != QExcursionStatus.voided)
            .order_by(QExcursion.started_at)
        )
    )
    ships = []
    for s in shipments_of(db, t):
        pod = pods.get(s.id)
        ships.append(
            {
                "id": s.id,
                "shipment_ref": s.shipment_ref,
                "consignee_name": s.consignee_name,
                "compartment": s.compartment,
                "classes": sorted(c.value for c in _classes_of(db, s)),
                "promised_at": s.promised_at,
                "delivered_at": s.delivered_at,
                "stopped": s.stopped,
                "notify_consignee": s.notify_consignee,
                "pod": None
                if pod is None
                else {
                    "id": pod.id,
                    "delivered_at": pod.delivered_at,
                    "receiver_name": None if hide else pod.receiver_name,
                    "receiver_role": pod.receiver_role,
                    "signature_attachment_id": None if hide else pod.signature_attachment_id,
                    "seal_intact": pod.seal_intact,
                    "product_temp_c": pod.product_temp_c,
                    "exceptions": pod.exceptions,
                },
            }
        )
    can_override = (
        t.status == ST.preload_checked
        and not t.preload_passed
        and b.resolves(db, p, project, RT, t.id, "dispatch_override", ctx(t, db))
    )
    return {
        "id": t.id,
        "project_id": t.project_id,
        "trip_no": t.trip_no,
        "site_id": t.site_id,
        "carrier": b.supplier_ref(db, t.carrier_id),
        "own_fleet": t.own_fleet,
        "vehicle_id": t.vehicle_id,
        "plate_text": t.plate_text,
        "reefer_serial": t.reefer_serial,
        "compartments": t.compartments,
        "driver_name": None if hide else t.driver_name,
        "driver_worker_id": None if hide else t.driver_worker_id,
        "loggers": [b.mte_ref(db, x) for x in t.logger_mte_ids],
        "seal_numbers": t.seal_numbers,
        "planned_departure": t.planned_departure,
        "preload": checklists.response_read(resp),
        "preload_passed": t.preload_passed,
        "preload_failures": t.preload_failures,
        "preload_box_temp_c": t.preload_box_temp_c,
        "loading_temps": t.loading_temps,
        "override_allowed": override_allowed(t),
        "override_reason": t.override_reason,
        "override_requested": t.override_requested_at is not None,
        "can_override": can_override,
        "readiness": t.readiness,
        "departed_at": t.departed_at,
        "delivered_at": t.delivered_at,
        "closed_at": t.closed_at,
        "transit_data": has_transit_data(db, t),
        "status": t.status,
        "cancel_reason": t.cancel_reason,
        "shipments": ships,
        "excursions": [
            {
                "id": x.id,
                "exc_no": x.exc_no,
                "compartment": x.compartment,
                "severity": x.severity,
                "status": x.status,
                "transient": x.transient,
                "started_at": x.started_at,
                "duration_min": x.duration_min,
                "ncr_id": x.ncr_id,
            }
            for x in excs
        ],
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, t.id)
        ],
    }


def list_trips(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page_no: int,
    size: int,
    status: QTripStatus | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    q = select(QTrip).where(QTrip.project_id == project.id)
    if status:
        q = q.where(QTrip.status == status)
    if search and search.strip():
        q = q.where(QTrip.trip_no.ilike(f"%{search.strip()}%"))
    items = []
    for t in db.scalars(q.order_by(QTrip.created_at.desc()).limit(2000)):
        if g.scope.value == "responsible":
            if not (
                t.override_requested_at
                and t.status == ST.preload_checked
                and b.resolves(db, p, project, RT, t.id, "dispatch_override", ctx(t, db))
            ) and not b.signed_by(db, RT, t.id, p.user.id):
                continue
        elif not g.covers_site(t.site_id):
            continue
        items.append(
            {
                "id": t.id,
                "trip_no": t.trip_no,
                "status": t.status,
                "carrier": b.supplier_ref(db, t.carrier_id),
                "plate_text": t.plate_text,
                "planned_departure": t.planned_departure,
                "departed_at": t.departed_at,
                "delivered_at": t.delivered_at,
                "shipments": len(shipments_of(db, t)),
                "preload_passed": t.preload_passed,
                "overridden": t.override_reason is not None,
                "transit_excursions": db.scalar(
                    select(QExcursion.id)
                    .where(
                        QExcursion.trip_id == t.id,
                        QExcursion.transient.is_(False),
                        QExcursion.status != QExcursionStatus.voided,
                    )
                    .limit(1)
                )
                is not None,
            }
        )
    return b.page(items, page_no, size)


def list_shipments(
    db: Session, p: Principal, project_id: uuid.UUID, unassigned: bool = False
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    q = select(QShipment).where(QShipment.project_id == project.id)
    if unassigned:
        q = q.where(QShipment.trip_id.is_(None), QShipment.delivered_at.is_(None))
    out = []
    for s in db.scalars(q.order_by(QShipment.created_at.desc()).limit(300)):
        out.append(
            {
                "id": s.id,
                "shipment_ref": s.shipment_ref,
                "consignee_name": s.consignee_name,
                "owner": b.customer_ref(db, s.owner_customer_id),
                "classes": sorted(c.value for c in _classes_of(db, s)),
                "promised_at": s.promised_at,
                "delivered_at": s.delivered_at,
                "trip_id": s.trip_id,
            }
        )
    return out


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    return [
        reg.OpenStep(
            reg.PendingStep(
                RT,
                t.id,
                project.id,
                t.trip_no,
                "Dispatch override requested",
                "dispatch_override",
                t.override_requested_at or t.created_at,
                f"/quality/transport/{t.id}",
                "Q3",
            ),
            None,
            t.site_id,
            None,
            ctx(t, db).requesters,
        )
        for t in db.scalars(
            select(QTrip).where(
                QTrip.project_id == project.id,
                QTrip.status == ST.preload_checked,
                QTrip.override_requested_at.is_not(None),
            )
        )
    ]


_ = QExcursionKind
