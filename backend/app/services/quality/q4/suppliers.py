"""Supplier evaluation and quality scorecards (spec 8-quality §E.3, Q-SUP-01…05).

Evaluations: draft → submitted → approved (279 + RPM `supplier_evaluation.approve`, the submitter
never approves) or back to draft, or cancelled. The approved evaluation sets the supplier's
`next_evaluation_due` (Q-SUP-02) and feeds the Q0 approval gate (`SUPPLIER_GATES`, Q-SUP-01).

Scorecards are org-wide per supplier and period (`supplier_score_period`), computed from Q2 MIRs
and test results, Q3 receipts and Q0 NCRs / SCARs of every project (Q-SUP-03): points by 6g
`calc.points`, weights re-normalised over the metrics with data, band by the A / B / C limits.
Provisional until 10 days after the period end, then final (§4 `quality_daily`)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction
from app.core.errors import ErrorCode, not_found
from app.core.quality.common import QRecordType, QSupplierStatus
from app.core.quality.q2 import QMirResult, QMirStatus, QTestVerdict
from app.core.quality.q3 import QLineDecision, QReceiptStatus
from app.core.quality.q4 import (
    SCORE_METRICS,
    QScorePeriod,
    QScoreStatus,
    QSevKind,
    QSevMethod,
    QSevRecommendation,
    QSevStatus,
)
from app.models import Project
from app.models.quality import QNcr, QSupplier
from app.models.quality.q2 import QMir, QTestRequest
from app.models.quality.q3 import QReceipt, QReceiptLine
from app.models.quality.q4 import QSupplierEvaluation, QSupplierScore
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q4 import base as b
from app.services.scorecard import calc

C = b.C
RT = QRecordType
D = Decimal
ST = QSevStatus
OTIF_MIN = 60  # org-wide scorecards use the default `otif_window_minutes` (D-364)


# ---- evaluations -----------------------------------------------------------------------------


def total_of(criteria: list[dict[str, Any]]) -> Decimal | None:
    w = sum(D(str(c.get("weight") or 0)) for c in criteria)
    if w <= 0:
        return None
    s = sum(D(str(c.get("weight") or 0)) * D(str(c.get("score") or 0)) for c in criteria)
    return (D(s) / w).quantize(D("0.01"), ROUND_HALF_UP)


def sev_read(db: Session, e: QSupplierEvaluation, p: Principal | None = None) -> dict[str, Any]:
    hide = b.hide_names(p, e.project_id) if p else False
    project = db.get(Project, e.project_id)
    can_approve = bool(
        p is not None
        and project is not None
        and e.status == ST.submitted
        and rpm.resolves(db, p, project, RT.supplier_evaluation, "approve", _ctx(e), record_id=e.id)
    )
    return {
        "id": e.id,
        "project_id": e.project_id,
        "sev_no": e.sev_no,
        "supplier": b.supplier_ref(db, e.supplier_id),
        "kind": e.kind,
        "method": e.method,
        "audit_id": e.audit_id,
        "criteria": list(e.criteria or []),
        "total": e.total,
        "recommendation": e.recommendation,
        "conditions": e.conditions,
        "evaluated_at": e.evaluated_at,
        "submitted_at": e.submitted_at,
        "submitted_by": b.user_ref(db, e.submitted_by_user_id, hide),
        "approved_at": e.approved_at,
        "next_evaluation_due": e.next_evaluation_due,
        "status": e.status,
        "status_reason": e.status_reason,
        "can_approve": can_approve,
    }


def _ctx(e: QSupplierEvaluation) -> rpm.Ctx:
    return rpm.Ctx(requesters=frozenset(qc.ids(e.created_by_user_id, e.submitted_by_user_id)))


def _get(db: Session, p: Principal, eid: uuid.UUID) -> QSupplierEvaluation:
    e = db.get(QSupplierEvaluation, eid)
    if e is None or not p.can_see_project(e.project_id):
        raise not_found("Supplier evaluation")
    if p.grant(e.project_id, C.supplier_manage) is None:
        project = db.get(Project, e.project_id)
        if project is None or not rpm.resolves(
            db,
            p,
            project,
            RT.supplier_evaluation,
            "approve",
            _ctx(e),
            record_id=e.id,
            can_act=False,
        ):
            raise not_found("Supplier evaluation")
    return e


def list_evaluations(
    db: Session, p: Principal, project_id: uuid.UUID, supplier_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    b.project(db, p, project_id)
    if (
        p.grant(project_id, C.supplier_manage) is None
        and p.grant(project_id, C.supplier_approve) is None
    ):
        raise forbidden_error()
    stmt = select(QSupplierEvaluation).where(QSupplierEvaluation.project_id == project_id)
    if supplier_id:
        stmt = stmt.where(QSupplierEvaluation.supplier_id == supplier_id)
    rows = list(db.scalars(stmt.order_by(QSupplierEvaluation.created_at.desc())))
    if p.grant(project_id, C.supplier_manage) is None:
        rows = [e for e in rows if _can_n(db, p, e)]
    return [sev_read(db, e, p) for e in rows]


def _can_n(db: Session, p: Principal, e: QSupplierEvaluation) -> bool:
    try:
        _get(db, p, e.id)
    except Exception:
        return False
    return True


def read(db: Session, p: Principal, eid: uuid.UUID) -> dict[str, Any]:
    return sev_read(db, _get(db, p, eid), p)


def _criteria(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(raw):
        w, s = D(str(c.get("weight") or 0)), D(str(c.get("score") or 0))
        if not (0 <= w <= 100) or not (0 <= s <= 100):
            raise qc.field_err(
                f"criteria[{i}]", "Weight and score are 0–100.", "الوزن والدرجة من 0 إلى 100."
            )
        if not str(c.get("criterion") or "").strip():
            raise qc.field_err(f"criteria[{i}].criterion", "Name the criterion.", "اذكر المعيار.")
        out.append(
            {"criterion": str(c["criterion"]).strip()[:150], "weight": str(w), "score": str(s)}
        )
    return out


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.supplier_manage)
    s = db.get(QSupplier, body["supplier_id"])
    if s is None:
        raise qc.field_err("supplier_id", "Unknown supplier.", "مورد غير معروف.")
    crit = _criteria(body.get("criteria") or [])
    e = QSupplierEvaluation(
        id=uuid.uuid4(),
        project_id=project.id,
        supplier_id=s.id,
        kind=QSevKind(body["kind"]),
        method=QSevMethod(body["method"]),
        audit_id=body.get("audit_id"),
        criteria=crit,
        total=total_of(crit),
        recommendation=body.get("recommendation"),
        conditions=body.get("conditions"),
        evaluated_at=body.get("evaluated_at") or b.today(project),
        status=ST.draft,
        created_by_user_id=p.user.id,
    )
    db.add(e)
    db.flush()
    b.record(db, p, AuditAction.create, RT.supplier_evaluation, e, project.id)
    return sev_read(db, e, p)


def update(db: Session, p: Principal, eid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    e = _get(db, p, eid)
    b.writer(db, p, e.project_id, C.supplier_manage)
    if e.status != ST.draft:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a Draft evaluation is edited.",
            "تُعدل المسودة فقط.",
        )
    if "criteria" in body:
        e.criteria = _criteria(body["criteria"] or [])
        e.total = total_of(e.criteria)
    for k in ("recommendation", "conditions", "evaluated_at", "method", "audit_id"):
        if k in body:
            setattr(e, k, body[k])
    e.updated_by_user_id = p.user.id
    db.flush()
    return sev_read(db, e, p)


def transition(
    db: Session, p: Principal, eid: uuid.UUID, action: str, body: dict[str, Any]
) -> dict[str, Any]:
    e = _get(db, p, eid)
    bad = qc.err(
        409,
        ErrorCode.INVALID_TRANSITION,
        f"{action} is not allowed now.",
        "الإجراء غير مسموح الآن.",
    )
    if action == "submit":
        b.writer(db, p, e.project_id, C.supplier_manage)
        if e.status != ST.draft:
            raise bad
        if not any(D(str(c.get("weight") or 0)) > 0 for c in e.criteria or []):
            raise qc.field_err(
                "criteria",
                "At least one criterion with a weight above 0.",
                "معيار واحد على الأقل بوزن أكبر من صفر.",
            )
        if e.recommendation is None:
            raise qc.field_err("recommendation", "Give the recommendation.", "حدد التوصية.")
        e.status = ST.submitted
        e.submitted_at = now()
        e.submitted_by_user_id = p.user.id
    elif action in ("approve", "return"):
        project, _g = b.writer(db, p, e.project_id, C.supplier_approve, allow_n=True)
        if e.status != ST.submitted:
            raise bad
        if action == "return":
            comment = qc.reason(body.get("comment"), 20, "comment")
            b.sign(
                db,
                p,
                project,
                RT.supplier_evaluation,
                e.id,
                "approve",
                _ctx(e),
                decision="returned",
                comment=comment,
            )
            e.status = ST.draft
            e.status_reason = comment
        else:
            if p.user.id in _ctx(e).requesters:
                raise qc.err(
                    422,
                    ErrorCode.SOD_CONFLICT,
                    "The evaluator cannot approve their own evaluation (Q-RPM-06).",
                    "لا يجوز للمقيِّم اعتماد تقييمه.",
                )
            b.sign(
                db,
                p,
                project,
                RT.supplier_evaluation,
                e.id,
                "approve",
                _ctx(e),
                decision="approved",
                comment=body.get("comment"),
            )
            approve_effects(db, project, e)
    elif action == "cancel":
        b.writer(db, p, e.project_id, C.supplier_manage)
        if e.status not in (ST.draft, ST.submitted):
            raise bad
        e.status_reason = qc.reason(body.get("reason"), 20)
        e.status = ST.cancelled
    else:
        raise bad
    db.flush()
    b.record(
        db,
        p,
        AuditAction.status_change,
        RT.supplier_evaluation,
        e,
        e.project_id,
        details={"action": action},
    )
    return sev_read(db, e, p)


def approve_effects(db: Session, project: Project, e: QSupplierEvaluation) -> None:
    t = now()
    e.status = ST.approved
    e.approved_at = t
    e.approved_date = qc.project_day(project, t)
    if e.sev_no is None:
        e.sev_no = b.number(db, project, RT.supplier_evaluation)
    months = int(b.setting(db, project.id, "supplier_reeval_months"))
    e.next_evaluation_due = b.due_after(e.approved_date, months)
    s = db.get(QSupplier, e.supplier_id)
    if s is not None:
        s.next_evaluation_due = e.next_evaluation_due
    db.flush()


def gate(db: Session, s: QSupplier, to: str) -> list[reg.Blocker]:
    """Q-SUP-01: pending_approval → approved needs an approved evaluation recommending `approve`
    within the last 12 months (`conditional` also accepts `conditional`)."""
    ok = {QSevRecommendation.approve}
    if to == QSupplierStatus.conditional.value:
        ok.add(QSevRecommendation.conditional)
    since = now() - timedelta(days=366)
    hit = db.scalar(
        select(QSupplierEvaluation.id)
        .where(
            QSupplierEvaluation.supplier_id == s.id,
            QSupplierEvaluation.status == ST.approved,
            QSupplierEvaluation.recommendation.in_(list(ok)),
            QSupplierEvaluation.approved_at >= since,
        )
        .limit(1)
    )
    if hit is not None:
        return []
    return [
        reg.Blocker(
            "SUPPLIER_EVALUATION_REQUIRED",
            "Approve a supplier evaluation recommending approval (last 12 months) "
            "first (Q-SUP-01).",
            "اعتمد تقييماً للمورد يوصي بالاعتماد خلال آخر 12 شهراً أولاً.",
        )
    ]


# ---- scorecards (Q-SUP-03, -04) -----------------------------------------------------------------


def period_of(day: date, kind: QScorePeriod) -> tuple[date, date]:
    if kind == QScorePeriod.month:
        start = day.replace(day=1)
    else:
        start = date(day.year, (day.month - 1) // 3 * 3 + 1, 1)
    end = b.add_months(start, 1 if kind == QScorePeriod.month else 3) - timedelta(days=1)
    return start, end


def score_of(
    values: dict[str, Decimal | None],
    weights: dict[str, Any],
    anchors: dict[str, Any],
    bands: dict[str, Any],
) -> dict[str, Any]:
    """Pure Q-SUP-03 maths (QX19): points per metric, weights re-normalised over metrics with
    data, score 1 dp, band by A / B / C limits."""
    pts: dict[str, Decimal] = {}
    num = den = D(0)
    for code, _en, _ar in SCORE_METRICS:
        v = values.get(code)
        if v is None:
            continue
        good, bad = (D(str(x)) for x in anchors[code])
        pt = calc.points(D(str(v)), good, bad)
        pts[code] = pt.quantize(D("0.01"), ROUND_HALF_UP)
        w = D(str(weights.get(code, 0)))
        num += w * pt
        den += w
    score = (num / den).quantize(D("0.1"), ROUND_HALF_UP) if den else None
    band = None
    if score is not None:
        band = "D"
        for g in ("A", "B", "C"):
            if score >= D(str(bands[g])):
                band = g
                break
    rec = {"A": "keep", "B": "keep", "C": "improvement_plan", "D": "suspend"}.get(band or "")
    return {
        "points": {k: str(v) for k, v in pts.items()},
        "score": score,
        "band": band,
        "recommendation": rec,
        "weight_total": str(den),
    }


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return b.day_start(start), b.day_start(end + timedelta(days=1))


def metric_values(db: Session, supplier_id: uuid.UUID, start: date, end: date) -> dict[str, Any]:
    """Q-SUP-03 metric inputs over every project (SQL counts; a metric without data is None)."""
    a, e = _bounds(start, end)
    rl = db.execute(
        select(
            func.count(QReceiptLine.id),
            func.count(QReceiptLine.id).filter(QReceiptLine.decision == QLineDecision.accept),
        )
        .join(QReceipt, QReceipt.id == QReceiptLine.receipt_id)
        .where(
            QReceipt.supplier_id == supplier_id,
            QReceipt.status == QReceiptStatus.decided,
            QReceipt.decided_at >= a,
            QReceipt.decided_at < e,
            QReceiptLine.decision.is_not(None),
        )
    ).one()
    mirs = db.execute(
        select(
            func.count(QMir.id),
            func.count(QMir.id).filter(QMir.result == QMirResult.accepted),
            func.count(QMir.id).filter(func.jsonb_array_length(QMir.heat_mismatch) == 0),
        ).where(
            QMir.supplier_id == supplier_id,
            QMir.status == QMirStatus.decided,
            QMir.decided_at >= a,
            QMir.decided_at < e,
        )
    ).one()
    receipts = db.execute(
        select(
            func.count(QReceipt.id),
            func.count(QReceipt.id).filter(QReceipt.expected_at.is_not(None)),
            func.count(QReceipt.id).filter(
                QReceipt.expected_at.is_not(None),
                QReceipt.arrived_at
                <= QReceipt.expected_at + func.make_interval(0, 0, 0, 0, 0, OTIF_MIN),
            ),
        ).where(
            QReceipt.supplier_id == supplier_id,
            QReceipt.status == QReceiptStatus.decided,
            QReceipt.arrived_at >= a,
            QReceipt.arrived_at < e,
        )
    ).one()
    ncrs = (
        db.scalar(
            select(func.count(QNcr.id)).where(
                QNcr.supplier_id == supplier_id,
                QNcr.opened_at >= a,
                QNcr.opened_at < e,
                QNcr.status.not_in(["draft", "voided"]),
            )
        )
        or 0
    )
    tests = db.execute(
        select(
            func.count(QTestRequest.id).filter(QTestRequest.verdict == QTestVerdict.pass_),
            func.count(QTestRequest.id).filter(QTestRequest.verdict == QTestVerdict.fail),
        )
        .join(QMir, QMir.id == QTestRequest.mir_id)
        .where(
            QMir.supplier_id == supplier_id,
            QTestRequest.results_entered_at >= a,
            QTestRequest.results_entered_at < e,
        )
    ).one()
    scar_req = scar_ok = 0
    for sr in db.scalars(
        select(QNcr.supplier_response).where(
            QNcr.supplier_id == supplier_id, QNcr.supplier_response.is_not(None)
        )
    ):
        due = (sr or {}).get("due_on")
        if not due or not (start.isoformat() <= str(due) <= end.isoformat()):
            continue
        scar_req += 1
        scar_ok += bool((sr or {}).get("received_on_time"))
    decided = int(rl[0]) + int(mirs[0])
    deliveries = int(receipts[0]) + int(mirs[0])
    return {
        "M1": b.pct(int(rl[1]) + int(mirs[1]), decided, "0.01"),
        "M2": b.pct(ncrs, deliveries, "0.01"),
        "M3": b.pct(int(receipts[2]), int(receipts[1]), "0.01"),
        "M4": b.pct(int(tests[0]), int(tests[0]) + int(tests[1]), "0.01"),
        "M5": b.pct(scar_ok, scar_req, "0.01"),
        "M6": b.pct(int(mirs[2]), int(mirs[0]), "0.01"),
        "counts": {
            "decided": decided,
            "deliveries": deliveries,
            "ncrs": int(ncrs),
            "receipts_with_eta": int(receipts[1]),
            "tests": int(tests[0]) + int(tests[1]),
            "scar_requested": scar_req,
        },
    }


def _cfg(db: Session, project_id: uuid.UUID | None) -> tuple[Any, Any, Any, QScorePeriod]:
    pid = project_id or db.scalar(select(Project.id).order_by(Project.code).limit(1))
    assert pid is not None  # noqa: S101
    return (
        b.setting(db, pid, "supplier_score_weights"),
        b.setting(db, pid, "supplier_score_anchors"),
        b.setting(db, pid, "supplier_score_bands"),
        QScorePeriod(str(b.setting(db, pid, "supplier_score_period"))),
    )


def compute(
    db: Session, s: QSupplier, start: date, end: date, kind: QScorePeriod
) -> QSupplierScore:
    row = db.scalar(
        select(QSupplierScore).where(
            QSupplierScore.supplier_id == s.id, QSupplierScore.period_start == start
        )
    )
    if row is not None and row.status == QScoreStatus.final:
        return row
    w, anc, bands, _k = _cfg(db, None)
    vals = metric_values(db, s.id, start, end)
    res = score_of({k: vals[k] for k, _e, _a in SCORE_METRICS}, w, anc, bands)
    if row is None:
        row = QSupplierScore(
            id=uuid.uuid4(), supplier_id=s.id, period_kind=kind, period_start=start, period_end=end
        )
        db.add(row)
    row.metrics = {
        "values": {
            k: (str(v) if v is not None else None) for k, v in vals.items() if k != "counts"
        },
        "counts": vals["counts"],
        **res,
    }
    row.score, row.band, row.recommendation = res["score"], res["band"], res["recommendation"]
    row.computed_at = now()
    db.flush()
    return row


def score_read(db: Session, x: QSupplierScore) -> dict[str, Any]:
    return {
        "id": x.id,
        "supplier": b.supplier_ref(db, x.supplier_id),
        "period_kind": x.period_kind,
        "period_start": x.period_start,
        "period_end": x.period_end,
        "metrics": x.metrics,
        "score": x.score,
        "band": x.band,
        "recommendation": x.recommendation,
        "status": x.status,
        "finalised_at": x.finalised_at,
    }


def list_scores(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    period_start: date | None,
    supplier_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    b.project(db, p, project_id)
    if (
        p.grant(project_id, C.supplier_manage) is None
        and p.grant(project_id, C.quality_view) is None
    ):
        raise forbidden_error()
    stmt = select(QSupplierScore)
    if period_start:
        stmt = stmt.where(QSupplierScore.period_start == period_start)
    if supplier_id:
        stmt = stmt.where(QSupplierScore.supplier_id == supplier_id)
    rows = list(
        db.scalars(stmt.order_by(QSupplierScore.period_start.desc(), QSupplierScore.score.desc()))
    )
    return [score_read(db, x) for x in rows]


def recompute(
    db: Session, p: Principal, project_id: uuid.UUID, day: date | None
) -> list[dict[str, Any]]:
    project, _g = b.writer(db, p, project_id, C.supplier_manage)
    _w, _a, _b, kind = _cfg(db, project.id)
    start, end = period_of(day or b.today(project), kind)
    for s in db.scalars(
        select(QSupplier).where(
            QSupplier.status.in_(
                [QSupplierStatus.approved, QSupplierStatus.conditional, QSupplierStatus.suspended]
            )
        )
    ):
        compute(db, s, start, end, kind)
    return list_scores(db, p, project_id, start, None)


def latest_final(db: Session, supplier_id: uuid.UUID) -> QSupplierScore | None:
    return db.scalar(
        select(QSupplierScore)
        .where(
            QSupplierScore.supplier_id == supplier_id, QSupplierScore.status == QScoreStatus.final
        )
        .order_by(QSupplierScore.period_start.desc())
        .limit(1)
    )


def contractor_score(db: Session, p: Principal, contractor_id: uuid.UUID) -> list[dict[str, Any]]:
    """Q-SUP-05: the latest quality score of suppliers linked to a contractor (information only;
    never part of the 6g HSE scorecard)."""
    if (
        not any(p.grant(a.project_id, C.quality_view) for a in p.active_assignments if a.project_id)
        and not p.is_manager
    ):
        raise forbidden_error()
    out = []
    for s in db.scalars(select(QSupplier).where(QSupplier.contractor_id == contractor_id)):
        x = latest_final(db, s.id)
        out.append(
            {
                "supplier": b.supplier_ref(db, s.id),
                "score": x.score if x else None,
                "band": x.band if x else None,
                "period_start": x.period_start if x else None,
                "period_end": x.period_end if x else None,
            }
        )
    return out


def k157(db: Session, project_id: uuid.UUID, start: date, end: date) -> dict[str, Any]:
    """Mean of the latest final scores of suppliers used in the period (MIRs, receipts, NCRs)."""
    a, e = _bounds(start, end)
    used = set(
        db.scalars(
            select(QMir.supplier_id).where(
                QMir.project_id == project_id, QMir.decided_at >= a, QMir.decided_at < e
            )
        )
    )
    used |= set(
        db.scalars(
            select(QReceipt.supplier_id).where(
                QReceipt.project_id == project_id, QReceipt.arrived_at >= a, QReceipt.arrived_at < e
            )
        )
    )
    used |= set(
        db.scalars(
            select(QNcr.supplier_id).where(
                QNcr.project_id == project_id, QNcr.opened_at >= a, QNcr.opened_at < e
            )
        )
    )
    used.discard(None)
    scores = []
    by_band: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for sid in used:
        x = db.scalar(
            select(QSupplierScore)
            .where(
                QSupplierScore.supplier_id == sid,
                QSupplierScore.status == QScoreStatus.final,
                QSupplierScore.period_end <= max(end, start),
            )
            .order_by(QSupplierScore.period_start.desc())
            .limit(1)
        )
        if x is None:
            x = latest_final(db, sid)  # type: ignore[arg-type]
        if x is not None and x.score is not None:
            scores.append(D(x.score))
            by_band[x.band or "D"] += 1
    mean = (D(sum(scores)) / len(scores)).quantize(D("0.1"), ROUND_HALF_UP) if scores else None
    return {"suppliers": len(scores), "mean": mean, "by_band": by_band}


# ---- jobs ----------------------------------------------------------------------------------------


def daily(db: Session, at: datetime) -> dict[str, int]:
    """Provisional scores of the running period, finalisation 10 days after a period end
    (with the band C / D alerts, Q-SUP-04) and re-evaluation due alerts (Q-SUP-02)."""
    project = db.scalar(select(Project).order_by(Project.code).limit(1))
    if project is None:
        return {}
    _w, _a, _b, kind = _cfg(db, project.id)
    day = b.local_day(at)
    n = 0
    for s in db.scalars(
        select(QSupplier).where(
            QSupplier.status.in_([QSupplierStatus.approved, QSupplierStatus.conditional])
        )
    ):
        start, end = period_of(day, kind)
        compute(db, s, start, end, kind)
        pstart, pend = period_of(start - timedelta(days=1), kind)
        if day >= pend + timedelta(days=10):
            row = compute(db, s, pstart, pend, kind)
            if row.status != QScoreStatus.final:
                row.status = QScoreStatus.final
                row.finalised_at = now()
                n += band_alert(db, s, row)
        if s.next_evaluation_due is not None and day > s.next_evaluation_due:
            for pr in _projects_using(db, s.id):
                n += b.send(
                    db,
                    pr,
                    b.holders(db, pr, C.supplier_manage),
                    f"sev-due:{s.id}:{s.next_evaluation_due}",
                    f"Re-evaluation of {s.supplier_code} is overdue",
                    f"إعادة تقييم المورد {s.supplier_code} متأخرة",
                    path="/quality/supplier-scores",
                    email=False,
                )
    db.flush()
    return {"q4_supplier_scores": n}


def _projects_using(db: Session, sid: uuid.UUID) -> list[Project]:
    pids = set(db.scalars(select(QNcr.project_id).where(QNcr.supplier_id == sid)))
    pids |= set(db.scalars(select(QMir.project_id).where(QMir.supplier_id == sid)))
    pids |= set(db.scalars(select(QReceipt.project_id).where(QReceipt.supplier_id == sid)))
    pids |= set(
        db.scalars(
            select(QSupplierEvaluation.project_id).where(QSupplierEvaluation.supplier_id == sid)
        )
    )
    return [x for x in (db.get(Project, pid) for pid in pids) if x is not None]


def band_alert(db: Session, s: QSupplier, row: QSupplierScore) -> int:
    """Q-SUP-04: band C → improvement-plan task to 278 holders; band D → suspension recommendation
    to the `supplier.suspend` resolvers. The supplier status never changes by itself."""
    n = 0
    if row.band not in ("C", "D"):
        return 0
    for pr in _projects_using(db, s.id):
        if row.band == "C":
            n += b.send(
                db,
                pr,
                b.holders(db, pr, C.supplier_manage),
                f"sup-band-c:{s.id}:{row.period_start}",
                f"{s.supplier_code}: band C — ask for an improvement plan",
                f"{s.supplier_code}: الفئة C — اطلب خطة تحسين",
                path="/quality/supplier-scores",
            )
        else:
            users = b.resolvers(db, pr, RT.supplier, "suspend", rpm.Ctx())
            n += b.send(
                db,
                pr,
                users,
                f"sup-band-d:{s.id}:{row.period_start}",
                f"{s.supplier_code}: band D — suspension recommended",
                f"{s.supplier_code}: الفئة D — يوصى بالإيقاف",
                path="/quality/supplier-scores",
            )
    return n
