"""Concrete pours (spec 8-quality Q-TST-11…13): the pour log with the sets required versus taken,
the pre-pour hold point check through Q1's `HOLD_CHECKS` registry and the mix strength status
across pours (3-test windows)."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, EntityType
from app.core.errors import ErrorCode
from app.core.quality.common import QLinkKind, QRecordType
from app.core.quality.q2 import (
    MAR_APPROVED,
    QMaterialCategory,
    QPourStatus,
    QTestStatus,
    QTestVerdict,
)
from app.models import Site, Zone
from app.models.quality import QCriterion, QSupplier
from app.models.quality.q2 import QMar, QPour, QTestRequest
from app.schemas.hse_common import ApiWarning
from app.services.common import paginate
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import links, numbering, suppliers
from app.services.quality import registry as reg
from app.services.quality.q2 import base
from app.services.quality.q2.evaluators import STRENGTH_RULES, d

C = Capability
RT = QRecordType
ST = QPourStatus
DEAD = (QTestStatus.cancelled, QTestStatus.voided)


def mix_key(mar_id: uuid.UUID | None, grade: str) -> str:
    return f"{mar_id or '-'}|{grade.strip().upper()}"[:80]


def can_view(db: Session, p: Principal, x: QPour) -> bool:
    return base.can_view(
        db,
        p,
        x.project_id,
        (C.test_record, C.test_verify),
        x.site_id,
        x.engagement_id,
        own=(x.created_by_user_id,),
    )


def get_pour(db: Session, p: Principal, pour_id: uuid.UUID) -> QPour:
    x = db.get(QPour, pour_id)
    base.require_view(
        db,
        p,
        x is not None and can_view(db, p, x),
        EntityType.q_pour,
        pour_id,
        x.project_id if x else None,
        "Pour",
    )
    assert x is not None  # noqa: S101
    return x


def strength_sets(db: Session, x: QPour) -> list[QTestRequest]:
    out = []
    for t in db.scalars(
        select(QTestRequest).where(QTestRequest.pour_id == x.id, QTestRequest.status.not_in(DEAD))
    ):
        crit = db.get(QCriterion, t.criterion_id) if t.criterion_id else None
        if crit is not None and crit.rule_code in STRENGTH_RULES and t.retest_of_id is None:
            out.append(t)
    return out


def required_sets(db: Session, x: QPour) -> int:
    """Q-TST-11: max(1, ⌈volume_m3 ÷ `pour_sampling_m3`⌉) per pour and mix."""
    per = Decimal(str(base.setting(db, x.project_id, "pour_sampling_m3") or 50))
    return max(1, math.ceil(x.volume_m3 / per)) if per > 0 else 1


def mix_status(db: Session, x: QPour) -> dict[str, Any]:
    """Q-TST-13: strength tests of the mix in cast-date order; a failing 3-test window (clause a)
    marks every pour of that window."""
    if not x.mix_key:
        return {"tests": [], "flagged_pour_ids": [], "flagged": False}
    rows = list(
        db.scalars(
            select(QTestRequest).where(
                QTestRequest.project_id == x.project_id,
                QTestRequest.mix_key == x.mix_key,
                QTestRequest.status.in_(
                    [QTestStatus.results_entered, QTestStatus.verified, QTestStatus.amended]
                ),
                QTestRequest.retest_of_id.is_(None),
            )
        )
    )
    rows.sort(key=lambda t: (t.cast_date or datetime.min.date(), t.created_at))
    flagged: set[uuid.UUID] = set()
    out = []
    for i, t in enumerate(rows):
        det = t.verdict_detail or {}
        if t.verdict == QTestVerdict.fail:
            if det.get("clause") == "a" or det.get("a") == "fail":
                for w in rows[max(0, i - 2) : i + 1]:
                    if w.pour_id:
                        flagged.add(w.pour_id)
            if t.pour_id:
                flagged.add(t.pour_id)
        pour = db.get(QPour, t.pour_id) if t.pour_id else None
        out.append(
            {
                "test_id": t.id,
                "test_no": t.test_no,
                "pour_no": pour.pour_no if pour else None,
                "cast_date": t.cast_date,
                "test": det.get("test"),
                "mean3": det.get("mean3"),
                "verdict": t.verdict,
                "clause": det.get("clause"),
            }
        )
    return {"tests": out, "flagged_pour_ids": sorted(flagged, key=str), "flagged": x.id in flagged}


def read(db: Session, p: Principal, x: QPour, full: bool = True) -> dict[str, Any]:
    site = db.get(Site, x.site_id)
    zone = db.get(Zone, x.zone_id) if x.zone_id else None
    mar = db.get(QMar, x.mar_id) if x.mar_id else None
    sup = db.get(QSupplier, x.supplier_id) if x.supplier_id else None
    sets = strength_sets(db, x)
    acts: list[str] = []
    if qc.covers(p.grant(x.project_id, C.test_record), x.site_id, x.engagement_id) or p.is_manager:
        acts = {ST.planned: ["start", "cancel"], ST.started: ["close"]}.get(x.status, [])
    return {
        "id": x.id,
        "project_id": x.project_id,
        "pour_no": x.pour_no,
        "engagement_id": x.engagement_id,
        "element": x.element,
        "site_id": x.site_id,
        "site_code": site.code if site else "",
        "zone_id": x.zone_id,
        "zone_code": zone.code if zone else None,
        "location_ref": x.location_ref,
        "mar_id": x.mar_id,
        "mar_no": mar.mar_no if mar else None,
        "grade": x.grade,
        "fc_mpa": str(x.fc_mpa) if x.fc_mpa is not None else None,
        "volume_m3": str(x.volume_m3),
        "supplier_id": x.supplier_id,
        "supplier_code": sup.supplier_code if sup else None,
        "planned_on": x.planned_on,
        "started_at": x.started_at,
        "finished_at": x.finished_at,
        "ambient_temp_c": str(x.ambient_temp_c) if x.ambient_temp_c is not None else None,
        "pre_pour_ir_id": x.pre_pour_ir_id,
        "itp_point_id": x.itp_point_id,
        "quality_engineer_id": x.quality_engineer_id,
        "sets_required": required_sets(db, x),
        "sets_taken": len(sets),
        "set_test_ids": [t.id for t in sets],
        "flags": list(x.warnings or []),
        "status": x.status,
        "mix_status": mix_status(db, x) if full else None,
        "actions": acts if full else [],
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: QPourStatus | None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.test_record, C.test_verify)
    stmt = select(QPour).where(
        QPour.project_id == project.id,
        base.scope_cond(
            p, project.id, (C.test_record, C.test_verify), QPour.site_id, QPour.engagement_id
        ),
    )
    if status:
        stmt = stmt.where(QPour.status == status)
    items, total = paginate(db, stmt.order_by(QPour.created_at.desc()), page, page_size)
    return {
        "items": [read(db, p, x, full=False) for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QPour, list[ApiWarning]]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.ensure_profile_for(db, project, RT.pour, "A concrete pour")
    warnings: list[ApiWarning] = []
    eng = body.get("engagement_id")
    ir_id = body.get("pre_pour_ir_id")
    itp_point = body.get("itp_point_id")
    if ir_id:
        ad = reg.RECORD_TYPES.get(RT.ir)
        row = ad.get(db, ir_id) if ad else None
        if ad is not None:
            if row is None or ad.project_id(row) != project.id:
                raise qc.field_err("pre_pour_ir_id", "The IR is not on this project.")
            eng = ad.engagement(db, row) or eng  # Q-RPM-07: the ITP engagement of the IR
            itp_point = itp_point or getattr(row, "itp_point_id", None)
    site = db.get(Site, body["site_id"])
    if site is None or site.project_id != project.id:
        raise qc.field_err("site_id", "The site does not belong to this project.")
    qc.require_cover(p, project.id, C.test_record, site.id, eng)
    mar = db.get(QMar, body["mar_id"]) if body.get("mar_id") else None
    if body.get("mar_id"):
        if (
            mar is None
            or mar.project_id != project.id
            or mar.category != QMaterialCategory.concrete_mix
        ):
            raise qc.field_err("mar_id", "Pick a concrete-mix MAR of this project.")
        if mar.status not in MAR_APPROVED:
            raise qc.err(
                422,
                ErrorCode.MAR_NOT_APPROVED,
                f"{mar.mar_no or 'The MAR'} is not approved; the mix cannot be poured.",
                "طلب اعتماد الخلطة غير معتمد.",
            )
    if body.get("supplier_id"):
        warnings += suppliers.check_use(db, body["supplier_id"])
    grade = str(body["grade"]).strip()
    fc = d(body.get("fc_mpa"))
    if fc is None:
        digits = "".join(ch for ch in grade if ch.isdigit())
        fc = Decimal(digits) if digits else None
    x = QPour(
        id=uuid.uuid4(),
        project_id=project.id,
        pour_no=numbering.assign(db, project, RT.pour),
        engagement_id=eng,
        element=body["element"],
        site_id=site.id,
        zone_id=body.get("zone_id"),
        location_ref=body.get("location_ref"),
        mar_id=mar.id if mar else None,
        grade=grade,
        fc_mpa=fc,
        volume_m3=Decimal(str(body["volume_m3"])),
        supplier_id=body.get("supplier_id") or (mar.supplier_id if mar else None),
        planned_on=body.get("planned_on"),
        ambient_temp_c=d(body.get("ambient_temp_c")),
        pre_pour_ir_id=ir_id,
        itp_point_id=itp_point,
        quality_engineer_id=body.get("quality_engineer_id"),
        mix_key=mix_key(mar.id if mar else None, grade),
        status=ST.planned,
        warnings=[],
        created_by_user_id=p.user.id,
    )
    if x.volume_m3 <= 0:
        raise qc.field_err("volume_m3", "Volume must be above 0.")
    db.add(x)
    db.flush()
    x.sets_required = required_sets(db, x)
    if ir_id and RT.ir in reg.RECORD_TYPES:
        links.add(db, project.id, RT.pour, x.id, RT.ir, ir_id, QLinkKind.requires, p.user.id)
    if mar is not None:
        links.add(db, project.id, RT.pour, x.id, RT.mar, mar.id, QLinkKind.relates, p.user.id)
    base.audit_create(db, p, RT.pour, x, pour_no=x.pour_no)
    return x, warnings


def _writer(db: Session, p: Principal, x: QPour) -> None:
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.test_record, x.site_id, x.engagement_id)


def start(
    db: Session, p: Principal, pour_id: uuid.UUID, at: datetime | None
) -> tuple[QPour, list[ApiWarning]]:
    """Q-TST-12: the pre-pour hold IR must be released: True → allowed; False → 422
    HOLD_POINT_NOT_RELEASED; None (Q1 not installed, or no link) → warning HOLD_STATUS_UNKNOWN."""
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    x = get_pour(db, p, pour_id)
    _writer(db, p, x)
    if x.status != ST.planned:
        raise base.invalid("The pour", x.status, "started")
    fn = reg.HOLD_CHECKS.get("itp_point")
    released = fn(db, x.itp_point_id, x.location_ref) if fn is not None and x.itp_point_id else None
    warnings: list[ApiWarning] = []
    if released is False:
        raise qc.err(
            422,
            ErrorCode.HOLD_POINT_NOT_RELEASED,
            "The pre-pour hold point is not released; the pour cannot start (Q-TST-12).",
            "نقطة التوقف قبل الصب لم يُفرج عنها؛ لا يمكن بدء الصب.",
        )
    if released is None:
        warnings.append(
            qc.warning(
                ErrorCode.HOLD_STATUS_UNKNOWN,
                "The release of the pre-pour hold point could not be checked; confirm it before "
                "pouring.",
                "تعذّر التحقق من الإفراج عن نقطة التوقف قبل الصب؛ تأكد منه قبل الصب.",
            )
        )
        x.warnings = sorted({*(x.warnings or []), str(ErrorCode.HOLD_STATUS_UNKNOWN)})
    x.started_at = at or now()
    base.set_status(db, p, RT.pour, x, ST.started)
    return x, warnings


def close(
    db: Session, p: Principal, pour_id: uuid.UUID, at: datetime | None, temp: Any
) -> tuple[QPour, list[ApiWarning]]:
    """Closing with fewer strength sets than required gives `POUR_SAMPLING_SHORT` (counted)."""
    x = get_pour(db, p, pour_id)
    _writer(db, p, x)
    if x.status != ST.started:
        raise base.invalid("The pour", x.status, "closed")
    x.finished_at = at or now()
    if temp is not None:
        x.ambient_temp_c = d(temp)
    need, have = required_sets(db, x), len(strength_sets(db, x))
    x.sets_required = need
    warnings: list[ApiWarning] = []
    if have < need:
        warnings.append(
            qc.warning(
                ErrorCode.POUR_SAMPLING_SHORT,
                f"{have} strength set(s) taken; {need} required for {x.volume_m3} m³.",
                f"عدد مجموعات العينات {have}؛ المطلوب {need}.",
            )
        )
        x.warnings = sorted({*(x.warnings or []), str(ErrorCode.POUR_SAMPLING_SHORT)})
    base.set_status(db, p, RT.pour, x, ST.closed, sets=f"{have}/{need}")
    return x, warnings


def cancel(db: Session, p: Principal, pour_id: uuid.UUID, why: str | None) -> QPour:
    x = get_pour(db, p, pour_id)
    _writer(db, p, x)
    if x.status != ST.planned:
        raise base.invalid("The pour", x.status, "cancelled")
    x.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.pour, x, ST.cancelled, reason=x.status_reason)
    return x
