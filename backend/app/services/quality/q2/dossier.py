"""Q2 handover dossier sections (spec 8-quality §B.7, Q-DOS-01 / -03 e): `mar`, `mir`, `tests`,
`welding` and `calibration` for the Q1 dossier engine through registry `DOSSIER_SECTIONS`.

A record is in a dossier when its zone is in the scope zones or its system in the scope systems
(Q-DOS-01): tests and welds by `zone_id` / `system_id`, MIRs by `storage_zone_id` or an in-scope
test of the delivery, MARs through their in-scope MIRs, pours and tests, calibrations through the
instruments used by the in-scope tests, MIRs and welds. The dossier object is only read through its
`project_id`, `zone_ids` and `system_ids` (no import of Q1's model, §3.4).

Blockers (e): a failed test result without a closed NCR; a rejected MIR whose quarantined material
is not disposed of."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.hse_enums import AttachmentOwner as A
from app.core.quality.common import QNcrSourceType, QNcrStatus, QRecordType
from app.core.quality.q2 import (
    QCalRecordStatus,
    QMarStatus,
    QMirResult,
    QMirStatus,
    QQuarantineStatus,
    QTestStatus,
    QTestVerdict,
    QWeldStatus,
)
from app.models import Attachment
from app.models.quality import QMteItem, QMteUsage, QNcr
from app.models.quality.q2 import (
    QCalibration,
    QMar,
    QMir,
    QPour,
    QQuarantineItem,
    QTestRequest,
    QWeld,
)
from app.services.quality import registry as reg

TEST_LIVE = (QTestStatus.cancelled, QTestStatus.voided, QTestStatus.requested)
TITLES = {
    "mar": ("Material approvals", "اعتمادات المواد"),
    "mir": ("Material inspections", "فحوص المواد الموردة"),
    "tests": ("Test results", "نتائج الاختبارات"),
    "welding": ("Welding records", "سجلات اللحام"),
    "calibration": ("Calibration certificates", "شهادات المعايرة"),
}


def _ids(v: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(x)) for x in (v or [])]


def _scope(model: Any, d: Any, zone_attr: str = "zone_id") -> Any:
    """Q-DOS-01 on one table: zone in the scope zones or system in the scope systems."""
    zones, systems = _ids(getattr(d, "zone_ids", None)), _ids(getattr(d, "system_ids", None))
    conds = []
    if zones:
        conds.append(getattr(model, zone_attr).in_(zones))
    if systems and hasattr(model, "system_id"):
        conds.append(model.system_id.in_(systems))
    return or_(*conds) if conds else model.id.is_(None)


def _files(db: Session, owner: A, owner_id: uuid.UUID) -> list[str]:
    return [
        str(x)
        for x in db.scalars(
            select(Attachment.id)
            .where(
                Attachment.owner_type == owner,
                Attachment.owner_id == owner_id,
                Attachment.superseded_at.is_(None),
            )
            .order_by(Attachment.created_at)
        )
    ]


def _item(
    ref: str | None,
    title: str,
    status: Any,
    on: Any,
    rtype: str,
    rid: uuid.UUID,
    path: str,
    files: list[str],
    revision: Any = None,
) -> dict[str, Any]:
    return {
        "ref": ref or "—",
        "title": title,
        "revision": revision,
        "status": getattr(status, "value", status),
        "date": on.isoformat() if on is not None else None,
        "record_type": rtype,
        "record_id": str(rid),
        "link_path": path,
        "files": files,
    }


# ---- record sets ---------------------------------------------------------------------------------


def tests_in(db: Session, d: Any) -> list[QTestRequest]:
    return list(
        db.scalars(
            select(QTestRequest)
            .where(
                QTestRequest.project_id == d.project_id,
                _scope(QTestRequest, d),
                QTestRequest.status.notin_(TEST_LIVE),
            )
            .order_by(QTestRequest.test_no)
        )
    )


def mirs_in(db: Session, d: Any) -> list[QMir]:
    via_tests = [t.mir_id for t in tests_in(db, d) if t.mir_id]
    cond = _scope(QMir, d, "storage_zone_id")
    if via_tests:
        cond = or_(cond, QMir.id.in_(via_tests))
    return list(
        db.scalars(
            select(QMir)
            .where(
                QMir.project_id == d.project_id,
                cond,
                QMir.status.in_((QMirStatus.submitted, QMirStatus.decided)),
            )
            .order_by(QMir.mir_no)
        )
    )


def welds_in(db: Session, d: Any) -> list[QWeld]:
    return list(
        db.scalars(
            select(QWeld)
            .where(
                QWeld.project_id == d.project_id,
                _scope(QWeld, d),
                QWeld.status != QWeldStatus.voided,
            )
            .order_by(QWeld.joint_id)
        )
    )


def mars_in(db: Session, d: Any) -> list[QMar]:
    tests = tests_in(db, d)
    ids = {x.mar_id for x in mirs_in(db, d) if x.mar_id}
    pours = [t.pour_id for t in tests if t.pour_id]
    pour_cond = _scope(QPour, d)
    if pours:
        pour_cond = or_(pour_cond, QPour.id.in_(pours))
    ids |= {
        m
        for m in db.scalars(select(QPour.mar_id).where(QPour.project_id == d.project_id, pour_cond))
        if m
    }
    if not ids:
        return []
    return list(
        db.scalars(
            select(QMar)
            .where(
                QMar.id.in_(ids),
                QMar.status.notin_((QMarStatus.draft, QMarStatus.withdrawn)),
            )
            .order_by(QMar.mar_no, QMar.revision)
        )
    )


def instruments_in(db: Session, d: Any) -> set[uuid.UUID]:
    tests, mirs, welds = tests_in(db, d), mirs_in(db, d), welds_in(db, d)
    out: set[uuid.UUID] = {m for t in tests for m in (t.mte_ids or [])}
    records = [
        (QRecordType.test_request.value, [t.id for t in tests]),
        (QRecordType.mir.value, [x.id for x in mirs]),
        (QRecordType.weld.value, [w.id for w in welds]),
    ]
    for rtype, ids in records:
        if ids:
            out |= set(
                db.scalars(
                    select(QMteUsage.mte_id).where(
                        QMteUsage.project_id == d.project_id,
                        QMteUsage.record_type == rtype,
                        QMteUsage.record_id.in_(ids),
                    )
                )
            )
    return out


# ---- sections ------------------------------------------------------------------------------------


def mar_items(db: Session, d: Any) -> list[dict[str, Any]]:
    return [
        _item(
            m.mar_no,
            m.title_en,
            m.status,
            m.decided_at or m.submitted_at,
            "mar",
            m.id,
            f"/quality/materials/{m.id}",
            _files(db, A.q_mar, m.id),
            m.revision,
        )
        for m in mars_in(db, d)
    ]


def mir_items(db: Session, d: Any) -> list[dict[str, Any]]:
    return [
        _item(
            x.mir_no,
            x.material_description,
            x.result or x.status,
            x.decided_at or x.submitted_at,
            "mir",
            x.id,
            f"/quality/material-inspections/{x.id}",
            _files(db, A.q_mir, x.id),
        )
        for x in mirs_in(db, d)
    ]


def mir_blockers(db: Session, d: Any) -> list[reg.Blocker]:
    """(e) a rejected MIR whose quarantined material is not disposed of."""
    out = []
    for x in mirs_in(db, d):
        if x.result != QMirResult.rejected and not (x.rejected_qty or 0) > 0:
            continue
        for q in db.scalars(
            select(QQuarantineItem).where(
                QQuarantineItem.mir_id == x.id,
                QQuarantineItem.status == QQuarantineStatus.quarantined,
            )
        ):
            out.append(
                reg.Blocker(
                    "MIR_QUARANTINE_OPEN",
                    f"{x.mir_no}: rejected material {q.tag_no} is not disposed of.",
                    f"{x.mir_no}: المادة المرفوضة {q.tag_no} لم يُتصرف فيها بعد.",
                )
            )
    return out


def test_items(db: Session, d: Any) -> list[dict[str, Any]]:
    return [
        _item(
            t.test_no,
            f"{t.test_type_code} · {t.location_ref}",
            t.verdict if t.verdict != QTestVerdict.pending else t.status,
            t.verified_at or t.results_entered_at or t.sampled_at,
            "test_request",
            t.id,
            f"/quality/tests/{t.id}",
            _files(db, A.q_test_report, t.id),
            t.result_version or None,
        )
        for t in tests_in(db, d)
    ]


def _closed_ncr(db: Session, test_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(QNcr.id)
            .where(
                QNcr.source_type == QNcrSourceType.test_result,
                QNcr.source_id == test_id,
                QNcr.status == QNcrStatus.closed,
            )
            .limit(1)
        )
        is not None
    )


def test_blockers(db: Session, d: Any) -> list[reg.Blocker]:
    """(e) a failed test result without a closed NCR."""
    return [
        reg.Blocker(
            "TEST_FAILED_NCR_OPEN",
            f"{t.test_no} failed and has no closed NCR.",
            f"{t.test_no} راسب ولا يوجد له تقرير عدم مطابقة مغلق.",
        )
        for t in tests_in(db, d)
        if t.verdict == QTestVerdict.fail and not _closed_ncr(db, t.id)
    ]


def weld_items(db: Session, d: Any) -> list[dict[str, Any]]:
    return [
        _item(
            w.joint_id,
            f"{w.drawing_ref or ''} {w.process.value} {w.position}".strip(),
            w.status,
            w.welded_on,
            "weld",
            w.id,
            f"/quality/welding/welds/{w.id}",
            _files(db, A.q_weld, w.id),
            w.repair_count or None,
        )
        for w in welds_in(db, d)
    ]


def calibration_items(db: Session, d: Any) -> list[dict[str, Any]]:
    ids = instruments_in(db, d)
    if not ids:
        return []
    rows = db.execute(
        select(QCalibration, QMteItem)
        .join(QMteItem, QMteItem.id == QCalibration.mte_id)
        .where(QCalibration.mte_id.in_(ids), QCalibration.status == QCalRecordStatus.accepted)
        .order_by(QMteItem.mte_no, QCalibration.cal_date)
    ).all()
    return [
        _item(
            f"{m.mte_no} {c.certificate_no or c.cal_no or ''}".strip(),
            m.description,
            c.kind,
            c.cal_date,
            "calibration",
            c.id,
            f"/quality/calibration/{c.id}",
            _files(db, A.q_calibration_cert, c.id),
        )
        for c, m in rows
    ]


def register() -> None:
    providers = {
        "mar": (mar_items, None),
        "mir": (mir_items, mir_blockers),
        "tests": (test_items, test_blockers),
        "welding": (weld_items, None),
        "calibration": (calibration_items, None),
    }
    for code, (items, blocks) in providers.items():
        en, ar = TITLES[code]
        if blocks is None:
            reg.DOSSIER_SECTIONS[code] = reg.DossierSection(items, title_en=en, title_ar=ar)
        else:
            reg.DOSSIER_SECTIONS[code] = reg.DossierSection(items, blocks, en, ar)
