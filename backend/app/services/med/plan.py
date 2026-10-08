"""Medical requirement plan and worker health profiles (spec 6a-occupational-health §3.4, §3.5,
MR-1…MR-6, WP-1, WP-2): manual lines (capability 150), lines derived from the `medical_fitness`
attach points (H counted, E enforcement-only; read-only, MR-2), no exemptions (MR-6), the
requirements view and the gap register (§6.3)."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import Trade
from app.core.med_enums import (
    ExposureGroup,
    FitnessRequirementState,
    MedicalAppliesTo,
    MedicalLineSource,
)
from app.models import (
    AccessSettings,
    Deployment,
    HealthProfile,
    MedicalPlanLine,
    Project,
    Worker,
    Zone,
    ZoneAccessProfile,
)
from app.schemas.medical import (
    FitnessGapPage,
    FitnessGapRow,
    FitnessRequirementList,
    FitnessRequirementRead,
    HealthProfileHistory,
    HealthProfileRead,
    HealthProfileUpdate,
    MedicalPlanLineCreate,
    MedicalPlanLineRead,
    MedicalPlanLineRemove,
    MedicalPlanLineUpdate,
    MedicalPlanLineVersions,
    MedicalPlanRead,
)
from app.services.med import alerts, common
from app.services.med import reference as ref
from app.services.med import requirements as rq
from app.services.permissions import Principal, deny, forbidden_error

C = common.C
A = MedicalAppliesTo
SRC = MedicalLineSource
RS = FitnessRequirementState
MANUAL_KINDS = (A.all_workers, A.trade, A.exposure_group, A.adp_category)
MF = HookKind.medical_fitness.value

# ---- reads ---------------------------------------------------------------------------------------


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if p.grant(project_id, C.fitness_catalogue_view) is None:
        raise forbidden_error()


def line_read(
    ln: MedicalPlanLine, counts: tuple[int, int, int] | None = None
) -> MedicalPlanLineRead:
    out = MedicalPlanLineRead(
        id=ln.id,
        line_id=ln.line_id,
        line_no=ln.line_no,
        applies_to_kind=ln.applies_to_kind,
        applies_to_values=list(ln.applies_to_values or []),
        trades=[Trade(t) for t in ln.trades or []],
        code=ln.code,
        due_within_days=ln.due_within_days,
        source=ln.source,
        kpi_counted=ln.kpi_counted,
        read_only=ln.source != SRC.manual,
        hook_key=ln.hook_key,
        effective_from=ln.effective_from,
        effective_to=ln.effective_to,
        reason=ln.reason,
    )
    if counts is not None:
        out.counted, out.met, out.gaps = counts
    return out


def read_plan(
    db: Session, p: Principal, project_id: uuid.UUID, as_of: date | None, with_counts: bool
) -> MedicalPlanRead:
    common.visible_project(db, p, project_id)
    _view(p, project_id)
    d = as_of or common.today_local()
    lines = rq.lines_at(db, project_id, d)
    counts: dict[uuid.UUID, list[int]] = {}
    if with_counts:
        ev = rq.evaluate_project(db, project_id, d)
        for r in ev.counted:
            for ln in r.lines:
                c = counts.setdefault(ln.row.line_id, [0, 0, 0])
                c[0] += 1
                if r.state in (RS.met, RS.expiring):
                    c[1] += 1
                else:
                    c[2] += 1
    return MedicalPlanRead(
        project_id=project_id,
        as_of=d,
        lines=[
            line_read(ln.row, tuple(counts.get(ln.row.line_id, [0, 0, 0])) if with_counts else None)  # type: ignore[arg-type]
            for ln in lines
        ],
        hook_codes=sorted(rq.hook_codes(db, project_id)),
    )


def _get_versions(db: Session, line_id: uuid.UUID) -> list[MedicalPlanLine]:
    return list(
        db.scalars(
            select(MedicalPlanLine)
            .where(MedicalPlanLine.line_id == line_id)
            .order_by(MedicalPlanLine.effective_from, MedicalPlanLine.created_at)
        )
    )


def _current(db: Session, p: Principal, line_id: uuid.UUID) -> MedicalPlanLine:
    vs = _get_versions(db, line_id) or [
        x for x in [db.get(MedicalPlanLine, line_id)] if x is not None
    ]
    if not vs:
        raise deny(db, p, EntityType.medical_plan_line, line_id, None, "Plan line")
    vs = _get_versions(db, vs[0].line_id)
    cur = next((x for x in reversed(vs) if x.effective_to is None), vs[-1])
    common.visible_project(db, p, cur.project_id)
    return cur


def versions(db: Session, p: Principal, line_id: uuid.UUID) -> MedicalPlanLineVersions:
    cur = _current(db, p, line_id)
    _view(p, cur.project_id)
    return MedicalPlanLineVersions(items=[line_read(x) for x in _get_versions(db, cur.line_id)])


# ---- manual lines (MR-1, MR-5) -------------------------------------------------------------------


def _pcode(db: Session, project_id: uuid.UUID) -> str:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return pr.code


def _next_no(db: Session, project_id: uuid.UUID) -> str:
    nos = set(
        db.scalars(
            select(MedicalPlanLine.line_no).where(
                MedicalPlanLine.project_id == project_id,
                MedicalPlanLine.source == SRC.manual,
            )
        )
    )
    n = 1
    code = _pcode(db, project_id)
    while f"MRL-{code}-{n:03d}" in nos:
        n += 1
    return f"MRL-{code}-{n:03d}"


def _validate_values(kind: MedicalAppliesTo, values: list[str]) -> list[str]:
    if kind == A.all_workers:
        return []
    if not values:
        raise validation_error("applies_to_values", "Give at least one value.")
    if kind == A.trade:
        ok = {t.value for t in Trade}
    elif kind == A.exposure_group:
        ok = {g.value for g in ExposureGroup}
    else:
        from app.core.access_enums import AreaCategory  # noqa: PLC0415

        ok = {c.value for c in AreaCategory}
    bad = [v for v in values if v not in ok]
    if bad:
        raise validation_error("applies_to_values", f"Unknown values: {', '.join(bad)}.")
    return sorted(set(values))


def _due_ok(db: Session, project_id: uuid.UUID, code: str, days: int) -> None:
    s = common.settings(db, project_id)
    if days > s.medical_line_max_due_days:
        raise validation_error("due_within_days", f"At most {s.medical_line_max_due_days} days.")
    if days > 0 and code in rq.hook_codes(db, project_id):
        raise ApiError(
            422,
            ErrorCode.DUE_DAYS_NOT_ALLOWED,
            "A hook code on this project must be met from day one (due 0).",
            "رمز المتطلب المستخدم في المشروع يجب أن يستوفى من اليوم الأول.",
        )


def create_line(
    db: Session, p: Principal, project_id: uuid.UUID, body: MedicalPlanLineCreate
) -> MedicalPlanLineRead:
    common.visible_project(db, p, project_id)
    p.require(project_id, C.medical_plan_edit)
    if body.applies_to_kind not in MANUAL_KINDS:
        raise ApiError(
            422,
            ErrorCode.LINE_DERIVED_FROM_HOOK,
            "This kind of line is derived from the attach points.",
            "هذا النوع من البنود مشتق من نقاط الربط.",
        )
    fc = common.code(db, body.code)
    if fc is None or not fc.active:
        raise validation_error("code", "Unknown or inactive fitness code.")
    _due_ok(db, project_id, body.code, body.due_within_days)
    d = common.today_local()
    ln = MedicalPlanLine(
        id=uuid.uuid4(),
        line_id=uuid.uuid4(),
        project_id=project_id,
        line_no=_next_no(db, project_id),
        applies_to_kind=body.applies_to_kind,
        applies_to_values=_validate_values(body.applies_to_kind, body.applies_to_values),
        trades=[],
        code=body.code,
        due_within_days=body.due_within_days,
        source=SRC.manual,
        kpi_counted=True,
        effective_from=d,
    )
    from app.services.cert import common as cc  # noqa: PLC0415

    cc.stamp(ln, p, create=True)
    db.add(ln)
    db.flush()
    common.record(db, p, AuditAction.create, EntityType.medical_plan_line, ln, project_id)
    return line_read(ln)


def _derived(ln: MedicalPlanLine) -> ApiError:
    return ApiError(
        422,
        ErrorCode.LINE_DERIVED_FROM_HOOK,
        f"{ln.line_no} is derived from an attach point and is read-only (MR-2).",
        f"البند {ln.line_no} مشتق من نقطة ربط وللقراءة فقط.",
    )


def _loosening() -> ApiError:
    return ApiError(
        422,
        ErrorCode.PLAN_LOOSENING,
        "Only the HSE Manager may loosen the plan, with a reason of at least 20 characters.",
        "يحق لمدير السلامة فقط تخفيف الخطة مع ذكر سبب لا يقل عن 20 حرفاً.",
    )


def _new_version(
    db: Session, p: Principal, cur: MedicalPlanLine, **changes: Any
) -> MedicalPlanLine:
    from app.services.cert import common as cc  # noqa: PLC0415

    d = common.today_local()
    if cur.effective_from >= d:
        before = common.snap(cur)
        for k, v in changes.items():
            setattr(cur, k, v)
        cc.stamp(cur, p)
        db.flush()
        common.record(
            db, p, AuditAction.update, EntityType.medical_plan_line, cur, cur.project_id, before
        )
        return cur
    before = common.snap(cur)
    cur.effective_to = d - timedelta(days=1)
    data = {c.key: getattr(cur, c.key) for c in MedicalPlanLine.__table__.columns}
    data.update(id=uuid.uuid4(), effective_from=d, effective_to=None, **changes)
    nv = MedicalPlanLine(**data)
    cc.stamp(nv, p, create=True)
    db.add(nv)
    db.flush()
    common.record(
        db, p, AuditAction.update, EntityType.medical_plan_line, nv, cur.project_id, before
    )
    return nv


def update_line(
    db: Session, p: Principal, line_id: uuid.UUID, body: MedicalPlanLineUpdate
) -> MedicalPlanLineRead:
    cur = _current(db, p, line_id)
    p.require(cur.project_id, C.medical_plan_edit)
    if cur.source != SRC.manual:
        raise _derived(cur)
    if cur.effective_to is not None:
        raise validation_error("line_id", "The line is no longer in force.")
    changes: dict[str, Any] = {}
    loosen = False
    if body.applies_to_values is not None:
        vals = _validate_values(cur.applies_to_kind, body.applies_to_values)
        loosen |= bool(set(cur.applies_to_values or []) - set(vals))
        changes["applies_to_values"] = vals
    if body.due_within_days is not None:
        _due_ok(db, cur.project_id, cur.code, body.due_within_days)
        loosen |= body.due_within_days > cur.due_within_days
        changes["due_within_days"] = body.due_within_days
    if loosen:
        if not p.is_manager or not body.reason or len(body.reason.strip()) < 20:
            raise _loosening()
        changes["reason"] = body.reason.strip()
    return line_read(_new_version(db, p, cur, **changes))


def remove_line(
    db: Session, p: Principal, line_id: uuid.UUID, body: MedicalPlanLineRemove
) -> MedicalPlanLineRead:
    cur = _current(db, p, line_id)
    p.require(cur.project_id, C.medical_plan_edit)
    if cur.source != SRC.manual:
        raise _derived(cur)
    if not p.is_manager or len(body.reason.strip()) < 20:
        raise _loosening()
    before = common.snap(cur)
    cur.effective_to = common.today_local() - timedelta(days=1)
    cur.reason = body.reason.strip()
    db.flush()
    common.record(
        db,
        p,
        AuditAction.update,
        EntityType.medical_plan_line,
        cur,
        cur.project_id,
        before,
        {"removed": True},
    )
    return line_read(cur)


def exemption(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    common.visible_project(db, p, project_id)
    raise ApiError(
        422,
        ErrorCode.EXEMPTION_NOT_ALLOWED,
        "There are no medical exemptions: change the exposure group or trade instead (MR-6).",
        "لا توجد استثناءات طبية: غيّر مجموعة التعرض أو المهنة بدلاً من ذلك.",
    )


# ---- hook-derived lines (MR-2) -------------------------------------------------------------------


@dataclass(frozen=True)
class HookLine:
    key: str
    group: str  # "H" or "E"
    kind: MedicalAppliesTo
    values: tuple[str, ...]
    trades: tuple[str, ...]
    code: str
    base: int


def _mf(items: Any) -> list[dict[str, Any]]:
    return [x for x in items or [] if isinstance(x, dict) and x.get("kind") == MF]


def desired_hook_lines(db: Session, project_id: uuid.UUID) -> list[HookLine]:
    from app.services.ptw import reference as pref  # noqa: PLC0415

    out: list[HookLine] = []
    acc = db.get(AccessSettings, project_id)
    for x in _mf(acc.project_hook_requirements if acc else []):
        out.append(HookLine(f"project:{x['code']}", "H", A.project_hook, (), (), x["code"], 1))
    adps: dict[str, list[str]] = {}
    for cat, items in ((acc.hook_requirements_by_adp_category if acc else None) or {}).items():
        for x in _mf(items):
            adps.setdefault(x["code"], []).append(str(cat))
    for code, vals in sorted(adps.items()):
        out.append(HookLine(f"adp:{code}", "H", A.adp_category, tuple(sorted(vals)), (), code, 2))
    zones: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for zp in db.scalars(
        select(ZoneAccessProfile).where(ZoneAccessProfile.project_id == project_id)
    ):
        for x in _mf(zp.hook_requirements):
            k = (x["code"], tuple(sorted(x.get("trades") or [])))
            zones.setdefault(k, []).append(str(zp.zone_id))
    for (code, trades), vals in sorted(zones.items()):
        key = f"zone:{code}:{','.join(trades)}"
        out.append(HookLine(key, "H", A.zone, tuple(sorted(vals)), trades, code, 3))
    if common.registered(db, project_id):
        by_code: dict[str, list[str]] = {}
        for role, codes in pref.MEDICAL_CREW_HOOKS.items():
            for c in codes:
                by_code.setdefault(c, []).append(role.value)
        order = [
            "CSE-ENTRY-FIT",
            "RESPIRATOR-FIT",
            pref.MEDICAL_WAH_CODE,
            "CRANE-OPERATOR-FIT",
            "DRIVER-FIT",
            "RAD-WORKER-FIT",
        ]
        e = 1
        for code in order:
            if code == pref.MEDICAL_WAH_CODE:
                out.append(HookLine("crew:work_at_height:*", "E", A.crew_role, ("*",), (), code, e))
            elif code in by_code:
                roles = tuple(sorted(by_code[code]))
                out.append(HookLine(f"crew:{code}", "E", A.crew_role, roles, (), code, e))
            e += 1
        ops: dict[str, list[str]] = {}
        for cat, code in pref.MEDICAL_OPERATOR_CODES.items():
            ops.setdefault(code, []).append(cat)
        for code, cats in sorted(ops.items()):
            out.append(
                HookLine(
                    f"operator:{code}", "E", A.operator_binding, tuple(sorted(cats)), (), code, e
                )
            )
            e += 1
    return out


def sync_hook_lines(db: Session, project_id: uuid.UUID, on: date | None = None) -> int:
    """MR-2: create / version / close the derived lines to match the attach points."""
    d = on or common.today_local()
    want = {h.key: h for h in desired_hook_lines(db, project_id)}
    rows = list(
        db.scalars(
            select(MedicalPlanLine).where(
                MedicalPlanLine.project_id == project_id,
                MedicalPlanLine.source != SRC.manual,
                MedicalPlanLine.effective_to.is_(None),
            )
        )
    )
    have = {r.hook_key: r for r in rows if r.hook_key}
    used = set(
        db.scalars(
            select(MedicalPlanLine.line_no).where(
                MedicalPlanLine.project_id == project_id, MedicalPlanLine.source != SRC.manual
            )
        )
    )
    code = _pcode(db, project_id)
    n = 0
    for key, r in have.items():
        if key not in want:
            r.effective_to = d - timedelta(days=1) if r.effective_from < d else r.effective_from
            n += 1
    for key, h in want.items():
        cur = have.get(key)
        if (
            cur is not None
            and tuple(cur.applies_to_values or []) == h.values
            and cur.code == h.code
        ):
            continue
        if cur is not None:
            cur.effective_to = (
                d - timedelta(days=1) if cur.effective_from < d else cur.effective_from
            )
            line_id, line_no = cur.line_id, cur.line_no
        else:
            line_id = uuid.uuid4()
            i = h.base
            while f"MRL-{code}-{h.group}{i:02d}" in used:
                i += 1
            line_no = f"MRL-{code}-{h.group}{i:02d}"
            used.add(line_no)
        db.add(
            MedicalPlanLine(
                id=uuid.uuid4(),
                line_id=line_id,
                project_id=project_id,
                line_no=line_no,
                applies_to_kind=h.kind,
                applies_to_values=list(h.values),
                trades=list(h.trades),
                code=h.code,
                due_within_days=0,
                source=SRC.hook if h.group == "H" else SRC.enforcement,
                kpi_counted=h.group == "H",
                hook_key=key,
                effective_from=d,
            )
        )
        n += 1
    db.flush()
    return n


# ---- health profiles (WP-1, WP-2) ----------------------------------------------------------------


def _dep(db: Session, p: Principal, deployment_id: uuid.UUID) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if dep is None or not p.can_see_project(dep.project_id):
        raise deny(db, p, EntityType.worker, deployment_id, None, "Deployment")
    return dep


def ensure_profile(db: Session, dep: Deployment) -> HealthProfile:
    pr = db.scalar(select(HealthProfile).where(HealthProfile.deployment_id == dep.id))
    if pr is None:
        s = common.settings(db, dep.project_id)
        groups = rq.default_groups(s, dep.trade.value)
        pr = HealthProfile(
            id=uuid.uuid4(),
            deployment_id=dep.id,
            project_id=dep.project_id,
            exposure_groups=groups,
            history=[
                {
                    "value": groups,
                    "from_date": dep.mobilised_on.isoformat(),
                    "to_date": None,
                    "by": None,
                }
            ],
        )
        db.add(pr)
        db.flush()
    return pr


def profile_read(
    db: Session, p: Principal, dep: Deployment, pr: HealthProfile
) -> HealthProfileRead:
    w = db.get(Worker, dep.worker_id)
    assert w is not None  # noqa: S101
    hist = []
    for h in pr.history or []:
        hist.append(
            HealthProfileHistory(
                value=[ExposureGroup(x) for x in h.get("value") or []],
                from_date=date.fromisoformat(h["from_date"]),
                to_date=date.fromisoformat(h["to_date"]) if h.get("to_date") else None,
                by=common.user_ref(db, uuid.UUID(h["by"])) if h.get("by") else None,
            )
        )
    return HealthProfileRead(
        deployment_id=dep.id,
        project_id=dep.project_id,
        worker=common.worker_ref(w, common.names(p, dep.project_id)),
        trade=dep.trade,
        deployment_status=dep.status,
        exposure_groups=[ExposureGroup(x) for x in pr.exposure_groups or []],
        history=hist,
    )


def get_profile(db: Session, p: Principal, deployment_id: uuid.UUID) -> HealthProfileRead:
    dep = _dep(db, p, deployment_id)
    ok = any(
        common.covers_dep(p.grant(dep.project_id, c), dep)
        for c in (C.fitness_status_view, C.health_profile_edit)
    )
    if not ok:
        raise deny(db, p, EntityType.worker, deployment_id, dep.project_id, "Deployment")
    return profile_read(db, p, dep, ensure_profile(db, dep))


def update_profile(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: HealthProfileUpdate
) -> HealthProfileRead:
    dep = _dep(db, p, deployment_id)
    g = p.require(dep.project_id, C.health_profile_edit)
    if not common.covers_dep(g, dep):
        raise forbidden_error()
    pr = ensure_profile(db, dep)
    new = sorted({x.value for x in body.exposure_groups})
    old = list(pr.exposure_groups or [])
    removed = set(old) - set(new)
    d = common.today_local()
    gap_codes = []
    if removed:
        f = rq.load(db, dep.project_id, d, deployment_ids=[dep.id], mobilised_only=False)
        for r in rq.evaluate_dep(f, dep):
            for g_ in removed:
                if ref.SURVEILLANCE_OF.get(g_) == r.code and r.state == RS.gap:
                    gap_codes.append(r.code)
    if gap_codes:
        common.reason(body.reason, 20)
    before = common.snap(pr)
    hist = [dict(h) for h in pr.history or []]
    for h in hist:
        if h.get("to_date") is None:
            h["to_date"] = (d - timedelta(days=1)).isoformat()
    hist = [
        h
        for h in hist
        if date.fromisoformat(h["to_date"] or d.isoformat()) >= date.fromisoformat(h["from_date"])
    ]
    hist.append(
        {
            "value": new,
            "from_date": d.isoformat(),
            "to_date": None,
            "by": str(p.user.id),
            "reason": (body.reason or "").strip() or None,
        }
    )
    pr.history = hist
    pr.exposure_groups = new
    db.flush()
    common.record(db, p, AuditAction.update, EntityType.worker, pr, dep.project_id, before)
    if gap_codes:
        n = alerts.wno(db, dep.worker_id)
        alerts.send(
            db,
            alerts.oh(db, dep.project_id),
            NotificationKind.exposure_group_removed,
            f"Exposure group removed while surveillance was overdue: {n} ({', '.join(gap_codes)})",
            f"أزيلت مجموعة تعرض أثناء تأخر المراقبة الصحية: {n}",
            dep.project_id,
        )
    return profile_read(db, p, dep, pr)


# ---- requirements and gaps (§6.3) ----------------------------------------------------------------


def _req_read(r: rq.Req, tier: int) -> FitnessRequirementRead:
    c = r.check
    out = FitnessRequirementRead(
        code=r.code,
        line_nos=r.line_nos,
        kpi_counted=r.kpi_counted,
        hook_code=r.hook_code,
        critical=r.critical,
        applies_from=r.applies_from,
        due_date=r.due_date,
        state=r.state,
        counted=r.counted,
        valid_until=c.valid_until if c is not None else None,
    )
    if tier >= 2 and c is not None and c.row is not None:
        out.outcome = c.row.line.outcome
    if tier >= 3 and c is not None and not c.ok:
        out.reason_code = c.reason
    return out


def requirements(
    db: Session, p: Principal, deployment_id: uuid.UUID, as_of: date | None
) -> FitnessRequirementList:
    dep = _dep(db, p, deployment_id)
    t = common.tier(p, dep.project_id, dep)
    if t < 1:
        raise deny(db, p, EntityType.worker, deployment_id, dep.project_id, "Deployment")
    d = as_of or common.today_local()
    f = rq.load(db, dep.project_id, d, deployment_ids=[dep.id], mobilised_only=False)
    w = db.get(Worker, dep.worker_id)
    assert w is not None  # noqa: S101
    if t >= 2:
        common.sensitive_read(
            db,
            p,
            EntityType.worker,
            dep.worker_id,
            dep.project_id,
            ["fitness_outcome"] + (["fitness_reason"] if t >= 3 else []),
        )
    return FitnessRequirementList(
        deployment_id=dep.id,
        worker=common.worker_ref(w, common.names(p, dep.project_id)),
        as_of=d,
        tier=common.tier_enum(t),
        items=[_req_read(r, t) for r in rq.evaluate_dep(f, dep)],
    )


CATEGORY = {
    "MEDICAL_MISSING": "missing",
    "MEDICAL_EXPIRED": "expired",
    "MEDICAL_REVIEW_DUE": "review_due",
    "MEDICAL_UNFIT": "unfit",
    "RESTRICTION_CONFLICT": "restriction",
    "MEDICAL_HOLD": "hold",
    "MEDICAL_PENDING_REVIEW": "pending_review",
    "MEDICAL_UNVERIFIED": "unverified",
    "MEDICAL_REVOKED": "revoked",
    "MEDICAL_VERIFICATION_FAILED": "verification_failed",
}


def gaps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    as_of: date | None,
    code: list[str] | None,
    engagement_id: uuid.UUID | None,
    hook_codes_only: bool,
) -> FitnessGapPage:
    from app.models import ProjectEngagement  # noqa: PLC0415

    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.fitness_status_view)
    if g is None:
        raise forbidden_error()
    d = as_of or common.today_local()
    ev = rq.evaluate_project(db, project_id, d)
    rows = []
    for r in ev.counted:
        if r.state != RS.gap or not common.covers_dep(g, r.dep):
            continue
        if code and r.code not in code:
            continue
        if engagement_id is not None and r.dep.engagement_id != engagement_id:
            continue
        if hook_codes_only and not r.hook_code:
            continue
        rows.append(r)
    rows.sort(key=lambda r: (ev.f.workers[r.dep.worker_id].worker_no, r.code))
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    show = common.names(p, project_id)
    engs = {
        e.id: e.contractor.short_code
        for e in db.scalars(
            select(ProjectEngagement).where(ProjectEngagement.project_id == project_id)
        )
    }
    items = []
    for r in chunk:
        t = common.tier(p, project_id, r.dep)
        row = FitnessGapRow(
            deployment_id=r.dep.id,
            worker=common.worker_ref(ev.f.workers[r.dep.worker_id], show),
            engagement_short_code=engs.get(r.dep.engagement_id) if r.dep.engagement_id else None,
            trade=r.dep.trade,
            code=r.code,
            due_date=r.due_date,
            hook_code=r.hook_code,
            critical=r.critical,
        )
        if t >= 2 and r.reason is not None:
            row.outcome_category = CATEGORY.get(r.reason.value, "other")
        if t >= 3:
            row.reason_code = r.reason
        items.append(row)
    return FitnessGapPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        as_of=d,
        tier=common.tier_enum(common.project_tier(p, project_id)),
    )


def gap_counts(ev: rq.ProjectEval) -> Counter[str]:
    return Counter(r.reason.value if r.reason else "other" for r in ev.counted if r.state == RS.gap)


def zone_codes(db: Session, project_id: uuid.UUID) -> dict[str, str]:
    return {
        str(z.id): z.code for z in db.scalars(select(Zone).where(Zone.project_id == project_id))
    }


def plan_count(db: Session, project_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(MedicalPlanLine)
            .where(MedicalPlanLine.project_id == project_id)
        )
        or 0
    )
