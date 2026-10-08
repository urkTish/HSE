"""Training matrix lines (spec 5-training §3.4, §4.3, MX-1…MX-8), hook-derived lines kept in
step with the Phase 2/3 attach points (MX-2), worker training profiles (§3.5, MX-9) and
requirement exemptions (§3.11, MX-10)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.clock import now
from app.core.enums import AuditAction, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import Trade
from app.core.ptw_enums import PermitType, PtwCrewRole
from app.core.train_enums import (
    ExemptionStatus,
    MatrixAppliesTo,
    MatrixLevel,
    MatrixLineSource,
    MatrixRole,
    ProfileField,
)
from app.models import (
    AccessSettings,
    Deployment,
    PassCategory,
    Project,
    TrainingExemption,
    TrainingMatrixLine,
    TrainingProfile,
    Zone,
    ZoneAccessProfile,
)
from app.schemas.training_matrix import (
    ExemptionCreate,
    ExemptionPage,
    ExemptionRead,
    ExemptionWithdraw,
    MatrixLineCreate,
    MatrixLineRead,
    MatrixLineRemove,
    MatrixLineUpdate,
    MatrixLineVersions,
    MatrixRead,
    MatrixRequirementRead,
    ProfileHistoryRow,
    TrainingProfileRead,
    TrainingProfileUpdate,
)
from app.services.cert import common as cc
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.train import common
from app.services.train import reference as ref
from app.services.train import requirements as reqs

A = MatrixAppliesTo
C = common.C
TC = HookKind.training_course
APPOINTMENT_RECEIVER = "receiver"
# order in which hook-derived enforcement lines are numbered on first sync (A.4 E01…E12)
E_ORDER = (
    "FIRE-WATCH",
    "WAH",
    "CSE-ENTRANT",
    "CSE-RESCUE",
    "CSE-ATTENDANT",
    "GAS-TEST",
    "LOTO",
    "ELEC-QUALIFIED",
    "PTW-ISSUER",
    "PTW-RECEIVER",
    "LOTO-AUTHORITY",
    "FIRST-AID",
)


# ---- reads ---------------------------------------------------------------------------------------


def requirement_read(db: Session, course_code: str | None, any_of: list[str] | None) -> Any:
    codes = [course_code] if course_code else list(any_of or [])
    return MatrixRequirementRead(
        course_code=course_code,
        any_of=list(any_of) if any_of else None,
        courses=[common.course_ref_code(db, c) for c in codes],
    )


def _labels(db: Session, r: TrainingMatrixLine) -> list[str]:
    vals = list(r.applies_to_values or [])
    if r.applies_to_kind == A.zone:
        out = []
        for v in vals:
            try:
                z = db.get(Zone, uuid.UUID(v))
            except ValueError:
                z = None
            out.append(z.code if z else v)
        return out
    if r.applies_to_kind == A.matrix_role:
        return [ref.MATRIX_ROLE_LABELS[MatrixRole(v)][0] for v in vals if v in MatrixRole]
    if r.applies_to_kind == A.all_workers:
        return ["All workers"]
    return [v.replace("_", " ") for v in vals]


def line_read(
    db: Session, r: TrainingMatrixLine, refs: Refs | None = None, count: int | None = None
) -> MatrixLineRead:
    refs = refs or Refs(db)
    return MatrixLineRead(
        id=r.line_id,
        version_id=r.id,
        line_no=r.line_no,
        project_id=r.project_id,
        applies_to_kind=r.applies_to_kind,
        applies_to_values=list(r.applies_to_values or []),
        applies_to_labels=_labels(db, r),
        requirement=requirement_read(db, r.course_code, r.any_of),
        level=r.level,
        due_within_days=r.due_within_days,
        source=r.source,
        kpi_counted=r.kpi_counted,
        hook_attach_point=r.hook_attach_point,
        effective_from=r.effective_from,
        effective_to=r.effective_to,
        reason=r.reason,
        applicable_deployments=count,
        created_by=refs.user(r.created_by_user_id),
        created_at=r.created_at,
    )


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if p.grant(project_id, C.training_catalogue_view) is None:
        raise forbidden_error()


def read_matrix(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    as_of: date | None = None,
    kinds: list[MatrixAppliesTo] | None = None,
    level: MatrixLevel | None = None,
    source: MatrixLineSource | None = None,
    course_code: str | None = None,
    include_counts: bool = False,
) -> MatrixRead:
    common.visible_project(db, p, project_id)
    _view(p, project_id)
    sync_hook_lines(db, project_id)
    d = as_of or common.today_local()
    lines = reqs.lines_at(db, project_id, d)
    counts: dict[uuid.UUID, int] = {}
    if include_counts:
        f = reqs.load(db, project_id, d)
        for ln in lines:
            if not ln.row.kpi_counted:
                continue
            counts[ln.row.line_id] = sum(
                1
                for dep in f.deps
                if common.mobilised_on(dep, d) and reqs._applies(f, ln, dep) is not None
            )
    refs = Refs(db)
    out = []
    for ln in lines:
        r = ln.row
        if kinds and r.applies_to_kind not in kinds:
            continue
        if level and r.level != level:
            continue
        if source and r.source != source:
            continue
        if course_code and course_code not in ln.codes:
            continue
        out.append(line_read(db, r, refs, counts.get(r.line_id) if include_counts else None))
    return MatrixRead(project_id=project_id, as_of=d, lines=out)


def _current(db: Session, line_id: uuid.UUID) -> TrainingMatrixLine:
    rows = list(
        db.scalars(
            select(TrainingMatrixLine)
            .where(TrainingMatrixLine.line_id == line_id)
            .order_by(
                TrainingMatrixLine.effective_from.desc(), TrainingMatrixLine.created_at.desc()
            )
        )
    )
    if not rows:
        raise not_found("Matrix line")
    return rows[0]


def versions(db: Session, p: Principal, line_id: uuid.UUID) -> MatrixLineVersions:
    cur = _current(db, line_id)
    common.visible_project(db, p, cur.project_id)
    _view(p, cur.project_id)
    rows = list(
        db.scalars(
            select(TrainingMatrixLine)
            .where(TrainingMatrixLine.line_id == line_id)
            .order_by(
                TrainingMatrixLine.effective_from.desc(), TrainingMatrixLine.created_at.desc()
            )
        )
    )
    refs = Refs(db)
    return MatrixLineVersions(
        line_id=line_id, line_no=cur.line_no, versions=[line_read(db, r, refs) for r in rows]
    )


# ---- validation ----------------------------------------------------------------------------------


def _err(code: ErrorCode, en: str, ar: str, status: int = 422, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def _validate(
    db: Session,
    project_id: uuid.UUID,
    kind: MatrixAppliesTo,
    values: list[str],
    course_code: str | None,
    any_of: list[str] | None,
    due: int,
) -> None:
    if kind in (A.crew_role, A.appointment_function):
        raise _err(
            ErrorCode.LINE_DERIVED_FROM_HOOK,
            "Crew-role and appointment lines are derived from the Phase 3 hooks.",
            "بنود أدوار الطاقم والتعيينات مشتقة من متطلبات المرحلة 3.",
        )
    if kind == A.all_workers:
        if values:
            raise validation_error("applies_to_values", "Leave values empty for all workers.")
    elif not values:
        raise validation_error("applies_to_values", "Give at least one value.")
    if kind == A.trade:
        bad = [v for v in values if v not in Trade.__members__]
        if bad:
            raise validation_error("applies_to_values", f"Unknown trade: {bad[0]}")
    elif kind == A.matrix_role:
        if any(v not in MatrixRole.__members__ for v in values):
            raise validation_error("applies_to_values", "Unknown matrix role.")
    elif kind == A.zone:
        zids = {str(z) for z in db.scalars(select(Zone.id).where(Zone.project_id == project_id))}
        if any(v not in zids for v in values):
            raise validation_error("applies_to_values", "Zones must be zones of the project.")
    elif kind == A.pass_category:
        cats = set(
            db.scalars(select(PassCategory.code).where(PassCategory.project_id == project_id))
        )
        if any(v not in cats for v in values):
            raise validation_error("applies_to_values", "Unknown pass category.")
    elif kind == A.adp_category:
        if any(v not in ref.ADP_CATEGORIES for v in values):
            raise validation_error("applies_to_values", "Unknown ADP category.")
    if (course_code is None) == (not any_of):
        raise validation_error("requirement", "Give exactly one of course_code or any_of.")
    codes = [course_code] if course_code else list(any_of or [])
    for c in codes:
        crs = common.course(db, c or "")
        if crs is None or not crs.active:
            raise validation_error("requirement", f"Unknown or inactive course: {c}")
        if any_of and crs.category not in ref.ANY_OF_CATEGORIES:
            raise _err(
                ErrorCode.ANY_OF_NOT_ALLOWED,
                "any_of is allowed only for professional qualifications and awareness courses.",
                "خيار «أيٌّ من» مسموح فقط للمؤهلات المهنية ودورات التوعية.",
            )
    if any_of and not 2 <= len(any_of) <= 6:
        raise validation_error("requirement", "any_of needs 2 to 6 codes.")
    s = common.settings(db, project_id)
    if due > s.matrix_line_max_due_days:
        raise validation_error(
            "due_within_days", f"At most {s.matrix_line_max_due_days} days on this project."
        )
    if due > 0:
        hook = reqs.project_hook_codes(db, project_id)
        sat: set[str] = set()
        for c in codes:
            crs = common.course(db, c or "")
            sat |= {c or ""} | set(crs.satisfies if crs else [])
        if sat & hook:
            raise _err(
                ErrorCode.DUE_DAYS_NOT_ALLOWED,
                "A requirement on a hook code must be due on mobilisation (0 days).",
                "يجب أن تكون مهلة المتطلب صفراً لأنه مستخدم كمتطلب في البوابات أو التصاريح.",
            )


def _next_manual_no(db: Session, project: Project) -> str:
    prefix = f"MXL-{project.code}-"
    nos = db.scalars(
        select(TrainingMatrixLine.line_no).where(
            TrainingMatrixLine.project_id == project.id,
            TrainingMatrixLine.source == MatrixLineSource.manual,
        )
    )
    n = 0
    for x in nos:
        tail = x.removeprefix(prefix)
        if tail.isdigit():
            n = max(n, int(tail))
    return f"{prefix}{n + 1:03d}"


def _snap(r: TrainingMatrixLine) -> dict[str, Any]:
    return cc.snap(r)


def create_line(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    body: MatrixLineCreate,
    effective_from: date | None = None,
    seed: bool = False,
) -> MatrixLineRead:
    """MX-7: effective_from = today (the seed passes its own date)."""
    project = common.project(db, project_id)
    if p is not None:
        common.visible_project(db, p, project_id)
        p.require(project_id, C.training_matrix_edit)
    rq = body.requirement
    _validate(
        db,
        project_id,
        body.applies_to_kind,
        list(body.applies_to_values),
        rq.course_code,
        rq.any_of,
        body.due_within_days,
    )
    r = TrainingMatrixLine(
        id=uuid.uuid4(),
        line_id=uuid.uuid4(),
        project_id=project_id,
        line_no=_next_manual_no(db, project),
        applies_to_kind=body.applies_to_kind,
        applies_to_values=list(body.applies_to_values),
        course_code=rq.course_code,
        any_of=list(rq.any_of or []),
        level=body.level,
        due_within_days=body.due_within_days,
        source=MatrixLineSource.manual,
        kpi_counted=True,
        effective_from=effective_from or common.today_local(),
        seed_fake=seed,
    )
    cc.stamp(r, p, create=True)
    db.add(r)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_matrix_line, r, project_id)
    return line_read(db, r)


def _loosening(msg: str) -> ApiError:
    return _err(
        ErrorCode.MATRIX_LOOSENING,
        f"Only the HSE Manager can loosen the matrix ({msg}).",
        "تخفيف متطلبات المصفوفة من صلاحية مدير السلامة فقط.",
    )


def update_line(
    db: Session, p: Principal, line_id: uuid.UUID, body: MatrixLineUpdate
) -> MatrixLineRead:
    cur = _current(db, line_id)
    common.visible_project(db, p, cur.project_id)
    p.require(cur.project_id, C.training_matrix_edit)
    if cur.source == MatrixLineSource.hook:
        raise _err(
            ErrorCode.LINE_DERIVED_FROM_HOOK,
            "This line follows a Phase 2/3 hook and cannot be edited.",
            "هذا البند مشتق من متطلبات المراحل 2/3 ولا يمكن تعديله.",
        )
    d = common.today_local()
    if cur.effective_to is not None and cur.effective_to < d:
        raise _err(ErrorCode.INVALID_TRANSITION, "The line was removed.", "تمت إزالة البند.", 409)
    ch = body.changes()
    values = ch.get("applies_to_values", list(cur.applies_to_values or []))
    rq = body.requirement
    course_code = rq.course_code if rq is not None else cur.course_code
    any_of = (rq.any_of or []) if rq is not None else list(cur.any_of or [])
    level = ch.get("level", cur.level)
    due = ch.get("due_within_days", cur.due_within_days)
    loosen = cur.level == MatrixLevel.mandatory and (
        level == MatrixLevel.recommended or due > cur.due_within_days
    )
    if loosen:
        if not p.is_manager:
            raise _loosening("downgrade or later due date")
        common.reason(body.reason, 20)
    _validate(db, cur.project_id, cur.applies_to_kind, values, course_code, any_of, due)
    before = _snap(cur)
    if cur.effective_from >= d:
        new = cur
    else:
        cur.effective_to = d - timedelta(days=1)
        cc.stamp(cur, p)
        new = TrainingMatrixLine(
            id=uuid.uuid4(),
            line_id=cur.line_id,
            project_id=cur.project_id,
            line_no=cur.line_no,
            applies_to_kind=cur.applies_to_kind,
            source=cur.source,
            kpi_counted=cur.kpi_counted,
            effective_from=d,
        )
        cc.stamp(new, p, create=True)
        db.add(new)
    new.applies_to_values = list(values)
    new.course_code = course_code
    new.any_of = list(any_of or [])
    new.level = level
    new.due_within_days = due
    new.reason = (body.reason or "").strip() or None
    new.effective_to = None
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.training_matrix_line, new, new.project_id,
              before)  # fmt: skip
    return line_read(db, new)


def remove_line(
    db: Session, p: Principal, line_id: uuid.UUID, body: MatrixLineRemove
) -> MatrixLineRead:
    cur = _current(db, line_id)
    common.visible_project(db, p, cur.project_id)
    p.require(cur.project_id, C.training_matrix_edit)
    if cur.source == MatrixLineSource.hook:
        raise _err(
            ErrorCode.LINE_DERIVED_FROM_HOOK,
            "This line follows a Phase 2/3 hook and cannot be removed.",
            "هذا البند مشتق من متطلبات المراحل 2/3 ولا يمكن إزالته.",
        )
    d = common.today_local()
    if cur.effective_to is not None and cur.effective_to < d:
        raise _err(ErrorCode.INVALID_TRANSITION, "The line was removed.", "البند مُزال.", 409)
    if cur.level == MatrixLevel.mandatory:
        if not p.is_manager:
            raise _loosening("remove a mandatory line")
        common.reason(body.reason, 20)
    before = _snap(cur)
    cur.effective_to = d - timedelta(days=1)
    cur.reason = (body.reason or "").strip() or cur.reason
    cc.stamp(cur, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.training_matrix_line, cur, cur.project_id,
              before, {"removed": True})  # fmt: skip
    return line_read(db, cur)


# ---- hook-derived lines (MX-2) -------------------------------------------------------------------


@dataclass(frozen=True)
class HookLine:
    key: str  # hook_key
    group: str  # H / E
    kind: MatrixAppliesTo
    values: tuple[str, ...]
    code: str
    attach: str
    order: tuple[int, str]


def _tc(items: Any) -> list[str]:
    out = []
    for h in items or []:
        k = h.get("kind") if isinstance(h, dict) else None
        if str(getattr(k, "value", k)) == TC.value:
            out.append(str(h["code"]))
    return out


def desired_hook_lines(db: Session, project_id: uuid.UUID) -> list[HookLine]:
    from app.services.ptw import config as pcfg  # noqa: PLC0415
    from app.services.ptw import reference as pref  # noqa: PLC0415

    out: list[HookLine] = []
    # H: zone profiles, pass categories, ADP categories (kpi_counted)
    zones: dict[str, list[str]] = {}
    for zp, _zcode in db.execute(
        select(ZoneAccessProfile, Zone.code)
        .join(Zone, Zone.id == ZoneAccessProfile.zone_id)
        .where(ZoneAccessProfile.project_id == project_id)
    ):
        for code in _tc(zp.hook_requirements):
            zones.setdefault(code, []).append(str(zp.zone_id))
    for code, vals in sorted(zones.items()):
        out.append(HookLine(f"zone:{code}", "H", A.zone, tuple(sorted(vals)), code,
                            "zone profile", (0, code)))  # fmt: skip
    cats: dict[str, list[str]] = {}
    for pc in db.scalars(select(PassCategory).where(PassCategory.project_id == project_id)):
        if not pc.active:
            continue
        for code in _tc(pc.hook_requirements):
            cats.setdefault(code, []).append(pc.code)
    for code, vals in sorted(cats.items()):
        out.append(HookLine(f"pass:{code}", "H", A.pass_category, tuple(sorted(vals)), code,
                            "pass category", (1, code)))  # fmt: skip
    acc = db.get(AccessSettings, project_id)
    adps: dict[str, list[str]] = {}
    for cat, items in ((acc.hook_requirements_by_adp_category if acc else None) or {}).items():
        for code in _tc(items):
            adps.setdefault(code, []).append(str(cat))
    for code, vals in sorted(adps.items()):
        out.append(HookLine(f"adp:{code}", "H", A.adp_category, tuple(sorted(vals)), code,
                            "ADP category", (2, code)))  # fmt: skip
    # E: crew roles per permit type and appointment functions (enforcement only)
    pairs: dict[str, dict[str, set[str]]] = {}  # code → role → types
    all_roles = {r.value for r in PtwCrewRole}
    for t in PermitType:
        crew = pcfg.type_lists(db, project_id, t)["crew"]
        for role, items in crew.items():
            for kind, code in items:
                if kind == TC:
                    pairs.setdefault(code, {}).setdefault(role.value, set()).add(t.value)
    for code, by_role in pairs.items():
        groups: dict[tuple[str, ...], list[str]] = {}
        for role, tset in by_role.items():
            groups.setdefault(tuple(sorted(tset)), []).append(role)
        for tkey, roles in groups.items():
            if set(roles) == all_roles:
                key = "|".join(f"crew:{t}:*" for t in tkey)
                rv: tuple[str, ...] = ()
                attach = f"all crew on {', '.join(tkey)} permits"
            else:
                key = "|".join(f"crew:{t}:{r}" for t in tkey for r in sorted(roles))
                rv = tuple(sorted(roles))
                attach = f"crew role {', '.join(rv)} ({', '.join(tkey)})"
            out.append(HookLine(key, "E", A.crew_role, rv, code, attach, _eorder(code)))
    for fn, items in pref.APPOINTMENT_HOOKS.items():
        for kind, code in items:
            if kind == TC:
                out.append(HookLine(f"appointment:{fn.value}", "E", A.appointment_function,
                                    (fn.value,), code, f"appointment {fn.value}",
                                    _eorder(code)))  # fmt: skip
    if pref.RECEIVER_HOOK[0] == TC:
        code = pref.RECEIVER_HOOK[1]
        out.append(HookLine(f"appointment:{APPOINTMENT_RECEIVER}", "E", A.appointment_function,
                            (APPOINTMENT_RECEIVER,), code, "permit receiver",
                            _eorder(code)))  # fmt: skip
    out.sort(key=lambda h: (h.group, h.order, h.key))
    return out


def _eorder(code: str) -> tuple[int, str]:
    return (E_ORDER.index(code) if code in E_ORDER else len(E_ORDER), code)


def sync_hook_lines(
    db: Session, project_id: uuid.UUID, on: date | None = None, seed: bool = False
) -> int:
    """MX-2: create / version / close the hook-derived lines to match the attach points.
    Returns the number of lines changed."""
    project = db.get(Project, project_id)
    if project is None:
        return 0
    d = on or common.today_local()
    want = {h.key: h for h in desired_hook_lines(db, project_id)}
    rows = list(
        db.scalars(
            select(TrainingMatrixLine).where(
                TrainingMatrixLine.project_id == project_id,
                TrainingMatrixLine.source == MatrixLineSource.hook,
            )
        )
    )
    open_rows = {r.hook_key: r for r in rows if r.effective_to is None}
    used: dict[str, int] = {"H": 0, "E": 0}
    prefix = f"MXL-{project.code}-"
    for r in rows:
        tail = r.line_no.removeprefix(prefix)
        if tail[:1] in used and tail[1:].isdigit():
            used[tail[:1]] = max(used[tail[:1]], int(tail[1:]))
    known_no = {r.hook_key: (r.line_no, r.line_id) for r in rows}
    changed = 0
    for key, r in open_rows.items():
        h = want.get(key or "")
        same = h is not None and tuple(r.applies_to_values or []) == h.values
        if same and h is not None and r.course_code == h.code:
            continue
        if r.effective_from >= d:
            if h is None:
                db.delete(r)
            else:
                r.applies_to_values = list(h.values)
                r.course_code = h.code
            changed += 1
            continue
        r.effective_to = d - timedelta(days=1)
        changed += 1
        if h is not None:
            db.add(_hook_row(project_id, h, r.line_no, r.line_id, d, seed))
    for key, h in want.items():
        if key in open_rows:
            continue
        if key in known_no:
            no, lid = known_no[key]
        else:
            used[h.group] += 1
            no, lid = f"{prefix}{h.group}{used[h.group]:02d}", uuid.uuid4()
        db.add(_hook_row(project_id, h, no, lid, d, seed))
        changed += 1
    if changed:
        db.flush()
    return changed


def _hook_row(
    project_id: uuid.UUID, h: HookLine, no: str, line_id: uuid.UUID, d: date, seed: bool
) -> TrainingMatrixLine:
    return TrainingMatrixLine(
        id=uuid.uuid4(),
        line_id=line_id,
        project_id=project_id,
        line_no=no,
        applies_to_kind=h.kind,
        applies_to_values=list(h.values),
        course_code=h.code,
        any_of=[],
        level=MatrixLevel.mandatory,
        due_within_days=0,
        source=MatrixLineSource.hook,
        kpi_counted=h.group == "H",
        hook_key=h.key,
        hook_attach_point=h.attach,
        effective_from=d,
        seed_fake=seed,
    )


# ---- training profiles (§3.5, MX-9) --------------------------------------------------------------


def _dep(db: Session, deployment_id: uuid.UUID) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise not_found("Deployment")
    return dep


def profile_row(db: Session, dep: Deployment) -> TrainingProfile | None:
    return db.scalar(select(TrainingProfile).where(TrainingProfile.deployment_id == dep.id))


def profile_read(db: Session, p: Principal, dep: Deployment) -> TrainingProfileRead:
    from app.models import Worker  # noqa: PLC0415

    pr = profile_row(db, dep)
    refs = Refs(db)
    w = db.get(Worker, dep.worker_id)
    assert w is not None  # noqa: S101
    zones = [z for z in (refs.zone(zid) for zid in (pr.work_zone_ids if pr else [])) if z]
    hist = []
    for h in (pr.history if pr else []) or []:
        hist.append(
            ProfileHistoryRow(
                field=ProfileField(h["field"]),
                value=[str(x) for x in h.get("value") or []],
                from_date=date.fromisoformat(h["from_date"]),
                to_date=date.fromisoformat(h["to_date"]) if h.get("to_date") else None,
                by=refs.user(uuid.UUID(h["by"])) if h.get("by") else None,
            )
        )
    return TrainingProfileRead(
        deployment_id=dep.id,
        project_id=dep.project_id,
        worker=common.worker_ref(w, common.names(p, dep.project_id)),
        engagement=refs.eng_required(dep.engagement_id) if dep.engagement_id else _no_eng(),
        trade=dep.trade,
        matrix_roles=[MatrixRole(r) for r in (pr.matrix_roles if pr else [])],
        work_zones=zones,
        history=hist,
        updated_at=pr.updated_at if pr else None,
    )


def _no_eng() -> Any:
    from app.schemas.hse_common import EngagementRef  # noqa: PLC0415

    return EngagementRef(
        id=uuid.UUID(int=0), contractor_id=uuid.UUID(int=0), short_code="—", name_en="—",
        name_ar="—", tier=1,
    )  # fmt: skip


def get_profile(db: Session, p: Principal, deployment_id: uuid.UUID) -> TrainingProfileRead:
    dep = _dep(db, deployment_id)
    common.visible_project(db, p, dep.project_id)
    if not common.covers_dep(p.grant(dep.project_id, C.training_record_view), dep):
        raise forbidden_error()
    return profile_read(db, p, dep)


def set_profile(
    db: Session,
    p: Principal | None,
    dep: Deployment,
    matrix_roles: list[str] | None = None,
    work_zone_ids: list[uuid.UUID] | None = None,
    on: date | None = None,
    seed: bool = False,
) -> TrainingProfile:
    """MX-9: each change opens a history row from `on` (today) and closes the previous one."""
    d = on or common.today_local()
    pr = profile_row(db, dep)
    if pr is None:
        pr = TrainingProfile(
            id=uuid.uuid4(),
            deployment_id=dep.id,
            project_id=dep.project_id,
            matrix_roles=[],
            work_zone_ids=[],
            history=[],
            seed_fake=seed,
        )
        cc.stamp(pr, p, create=True)
        db.add(pr)
    hist = [dict(h) for h in pr.history or []]
    by = str(p.user.id) if p is not None else None
    for fld, new in (
        (ProfileField.matrix_roles, matrix_roles),
        (ProfileField.work_zone_ids, [str(z) for z in work_zone_ids] if work_zone_ids is not None
         else None),
    ):  # fmt: skip
        if new is None:
            continue
        cur = [str(x) for x in getattr(pr, fld.value) or []]
        if sorted(cur) == sorted(new):
            continue
        for h in hist:
            if h["field"] == fld.value and h.get("to_date") is None:
                if date.fromisoformat(h["from_date"]) >= d:
                    h["to_date"] = "drop"
                else:
                    h["to_date"] = (d - timedelta(days=1)).isoformat()
        hist = [h for h in hist if h.get("to_date") != "drop"]
        if new:
            hist.append(
                {"field": fld.value, "value": sorted(new), "from_date": d.isoformat(),
                 "to_date": None, "by": by}
            )  # fmt: skip
        if fld == ProfileField.matrix_roles:
            pr.matrix_roles = sorted(new)
        else:
            pr.work_zone_ids = [uuid.UUID(z) for z in sorted(new)]
    pr.history = hist
    cc.stamp(pr, p)
    db.flush()
    return pr


def update_profile(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: TrainingProfileUpdate
) -> TrainingProfileRead:
    dep = _dep(db, deployment_id)
    common.visible_project(db, p, dep.project_id)
    g = p.require(dep.project_id, C.training_profile_edit)
    if not common.covers_dep(g, dep):
        raise forbidden_error()
    ch = body.changes()
    zones = ch.get("work_zone_ids")
    if zones is not None:
        sites = set(dep.site_ids or [])
        for zid in zones:
            z = db.get(Zone, zid)
            if z is None or z.project_id != dep.project_id or z.site_id not in sites:
                raise _err(
                    ErrorCode.ZONE_NOT_IN_DEPLOYMENT_SITES,
                    "The zone is not on the deployment's sites.",
                    "المنطقة ليست ضمن مواقع تعيين العامل.",
                )
    roles = ch.get("matrix_roles")
    pr0 = profile_row(db, dep)
    before = cc.snap(pr0) if pr0 is not None else None
    pr = set_profile(
        db,
        p,
        dep,
        [getattr(r, "value", r) for r in roles] if roles is not None else None,
        list(zones) if zones is not None else None,
    )
    cc.record(db, p, AuditAction.update if before else AuditAction.create,
              EntityType.training_profile, pr, dep.project_id, before)  # fmt: skip
    return profile_read(db, p, dep)


# ---- exemptions (§3.11, MX-10) -------------------------------------------------------------------


def exemption_read(db: Session, p: Principal, ex: TrainingExemption, refs: Refs) -> ExemptionRead:
    from app.models import Worker  # noqa: PLC0415

    dep = db.get(Deployment, ex.deployment_id)
    assert dep is not None  # noqa: S101
    w = db.get(Worker, dep.worker_id)
    assert w is not None  # noqa: S101
    ln = _current(db, ex.line_id)
    granted = refs.user(ex.granted_by_user_id)
    assert granted is not None  # noqa: S101
    status = ex.status
    if status == ExemptionStatus.active and ex.valid_until < common.today_local():
        status = ExemptionStatus.expired
    return ExemptionRead(
        id=ex.id,
        project_id=ex.project_id,
        deployment_id=ex.deployment_id,
        worker=common.worker_ref(w, common.names(p, ex.project_id)),
        line_no=ln.line_no,
        requirement=requirement_read(db, ln.course_code, ln.any_of),
        reason=ex.reason,
        valid_until=ex.valid_until,
        status=status,
        granted_by=granted,
        granted_at=ex.granted_at,
        withdrawn_by=refs.user(ex.withdrawn_by_user_id),
        withdrawn_at=ex.withdrawn_at,
    )


def list_exemptions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[ExemptionStatus] | None = None,
    deployment_id: uuid.UUID | None = None,
) -> ExemptionPage:
    common.visible_project(db, p, project_id)
    g = common.need(p, project_id, C.training_record_view, write=False)
    stmt = select(TrainingExemption).where(TrainingExemption.project_id == project_id)
    if deployment_id:
        stmt = stmt.where(TrainingExemption.deployment_id == deployment_id)
    if g.engagement_ids is not None:
        stmt = stmt.join(Deployment, Deployment.id == TrainingExemption.deployment_id).where(
            Deployment.engagement_id.in_(list(g.engagement_ids))
        )
    if statuses:
        d = common.today_local()
        conds = []
        from sqlalchemy import and_, or_  # noqa: PLC0415

        for s in statuses:
            if s == ExemptionStatus.active:
                conds.append(
                    and_(TrainingExemption.status == s, TrainingExemption.valid_until >= d)
                )
            elif s == ExemptionStatus.expired:
                conds.append(
                    or_(
                        TrainingExemption.status == s,
                        and_(TrainingExemption.status == ExemptionStatus.active,
                             TrainingExemption.valid_until < d),
                    )
                )  # fmt: skip
            else:
                conds.append(TrainingExemption.status == s)
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(TrainingExemption.granted_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    return ExemptionPage(
        items=[exemption_read(db, p, x, refs) for x in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def create_exemption(
    db: Session, p: Principal, project_id: uuid.UUID, body: ExemptionCreate
) -> ExemptionRead:
    common.visible_project(db, p, project_id)
    p.require(project_id, C.training_matrix_edit)
    dep = _dep(db, body.deployment_id)
    if dep.project_id != project_id:
        raise not_found("Deployment")
    ln = _current(db, body.line_id)
    if ln.project_id != project_id:
        raise not_found("Matrix line")
    codes = [ln.course_code] if ln.course_code else list(ln.any_of or [])
    hook = reqs.project_hook_codes(db, project_id)
    if ln.source == MatrixLineSource.hook or "IND-GENERAL" in codes or set(codes) & hook:
        raise _err(
            ErrorCode.EXEMPTION_NOT_ALLOWED,
            "Exemptions are not allowed for IND-GENERAL or hook codes.",
            "لا يُسمح بالاستثناء من التعريف العام أو من متطلبات البوابات والتصاريح.",
        )
    d = common.today_local()
    if body.valid_until < d or body.valid_until > common.add_months(d, ref.EXEMPTION_MAX_MONTHS):
        raise validation_error("valid_until", "An exemption lasts at most 6 months from today.")
    cc_reason = common.reason(body.reason, 30)
    ex = TrainingExemption(
        id=uuid.uuid4(),
        project_id=project_id,
        deployment_id=dep.id,
        line_id=ln.line_id,
        reason=cc_reason,
        valid_from=d,
        valid_until=body.valid_until,
        status=ExemptionStatus.active,
        granted_by_user_id=p.user.id,
        granted_at=now(),
    )
    cc.stamp(ex, p, create=True)
    db.add(ex)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_exemption, ex, project_id)
    return exemption_read(db, p, ex, Refs(db))


def withdraw_exemption(
    db: Session, p: Principal, exemption_id: uuid.UUID, body: ExemptionWithdraw
) -> ExemptionRead:
    ex = db.get(TrainingExemption, exemption_id)
    if ex is None:
        raise not_found("Exemption")
    common.visible_project(db, p, ex.project_id)
    p.require(ex.project_id, C.training_matrix_edit)
    if ex.status != ExemptionStatus.active:
        raise _err(ErrorCode.INVALID_TRANSITION, "The exemption is not active.",
                   "الاستثناء غير ساري.", 409)  # fmt: skip
    before = cc.snap(ex)
    ex.status = ExemptionStatus.withdrawn
    ex.withdrawn_by_user_id = p.user.id
    ex.withdrawn_at = now()
    ex.withdraw_reason = common.reason(body.reason, 10)
    cc.stamp(ex, p)
    db.flush()
    cc.record(db, p, AuditAction.status_change, EntityType.training_exemption, ex, ex.project_id,
              before)  # fmt: skip
    return exemption_read(db, p, ex, Refs(db))


def is_hse_or_manager(p: Principal, project_id: uuid.UUID) -> bool:
    return p.is_manager or Role.hse_officer in common.roles_on(p, project_id)
