"""Course catalogue (spec 5-training §3.1, CC-1…CC-7, BD5-2): org-wide, HSE Manager edits only,
tighten-only edits, project-effective validity and pass mark on read."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import InductionType
from app.core.clock import today
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.text import normalize
from app.core.train_enums import (
    AccreditationBodyCode,
    CourseCategory,
    DeliveryMode,
)
from app.models import (
    Project,
    TrainerAuthorisation,
    TrainingCourse,
    TrainingMatrixLine,
    TrainingRecord,
    TrainingSession,
)
from app.schemas.training_courses import (
    CourseCreate,
    CourseList,
    CourseRead,
    CourseUpdate,
    InductionLinkRead,
    ProviderRuleRead,
)
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.cert import reference as cref
from app.services.permissions import Principal, forbidden_error
from app.services.train import common
from app.services.train import requirements as reqs
from app.services.train import validity as tval

C = common.C
CAT = CourseCategory


def _err(code: ErrorCode, en: str, ar: str, status: int = 422, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def hook_codes_all(db: Session) -> set[str]:
    out: set[str] = set()
    for pid in db.scalars(select(Project.id)):
        out |= reqs.project_hook_codes(db, pid)
    return out


def in_use_codes(db: Session) -> set[str]:
    used: set[str] = set(db.scalars(select(TrainingRecord.course_code).distinct()))
    used |= set(db.scalars(select(TrainingSession.course_code).distinct()))
    used |= {c for c in db.scalars(select(TrainingMatrixLine.course_code).distinct()) if c}
    for xs in db.scalars(select(TrainingMatrixLine.any_of)):
        used |= set(xs or [])
    for xs in db.scalars(select(TrainerAuthorisation.course_codes)):
        used |= set(xs or [])
    return used


def course_read(
    db: Session,
    c: TrainingCourse,
    project_id: uuid.UUID | None = None,
    used: set[str] | None = None,
    hooks: set[str] | None = None,
    recomputed: int | None = None,
) -> CourseRead:
    allc = common.courses(db)
    link = None
    if c.category == CAT.induction_link and c.induction_type:
        link = InductionLinkRead(
            induction_type=InductionType(c.induction_type),
            project_course_codes={
                uuid.UUID(k): v for k, v in (c.induction_project_codes or {}).items()
            },
        )
    rule = None
    if c.category != CAT.induction_link:
        rule = ProviderRuleRead(
            internal_allowed=c.internal_allowed,
            contractor_delivery_allowed=c.contractor_delivery_allowed,
            accreditation_bodies_required=[
                AccreditationBodyCode(b) for b in c.accreditation_bodies_required or []
            ],
        )
    eff_v: int | None = None
    eff_pm: int | None = None
    crit: bool | None = None
    if project_id is not None:
        s = common.settings(db, project_id)
        eff_v = common.effective_validity_months(c, s)[0]
        eff_pm = common.effective_pass_mark(c, s) if c.theory_required else None
        crit = c.code in common.critical_codes(s)
    used = used if used is not None else in_use_codes(db)
    hooks = hooks if hooks is not None else hook_codes_all(db)
    return CourseRead(
        id=c.id,
        code=c.code,
        name_en=c.name_en,
        name_ar=c.name_ar,
        category=c.category,
        induction_link=link,
        validity_months=c.validity_months,
        effective_validity_months=eff_v,
        min_duration_hours=c.min_duration_hours,
        max_class_size=c.max_class_size,
        delivery_modes=[DeliveryMode(m) for m in c.delivery_modes or []],
        theory_required=c.theory_required,
        pass_mark_pct=c.pass_mark_pct,
        effective_pass_mark_pct=eff_pm,
        practical_required=c.practical_required,
        prerequisite_codes=list(c.prerequisite_codes or []),
        satisfies=list(c.satisfies or []),
        satisfied_by=[x.code for x in allc.values() if c.code in (x.satisfies or [])],
        renewal_course_code=c.renewal_course_code,
        renews_only=c.renews_only,
        provider_rule=rule,
        languages_offered=list(c.languages_offered or []),
        hook_code=c.code in hooks,
        critical_on_project=crit,
        in_use=c.code in used or c.code in hooks,
        active=c.active,
        records_recomputed=recomputed,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _can_view(p: Principal) -> None:
    if not p.has_any(C.training_catalogue_view):
        raise forbidden_error()


def list_courses(
    db: Session,
    p: Principal,
    category: list[CourseCategory] | None,
    active: bool | None,
    hook_code: bool | None,
    q: str | None,
    project_id: uuid.UUID | None,
) -> CourseList:
    _can_view(p)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    used = in_use_codes(db)
    hooks = hook_codes_all(db)
    out = []
    needle = normalize(q) if q else None
    for c in sorted(common.courses(db).values(), key=lambda x: x.code):
        if category and c.category not in category:
            continue
        if active is not None and c.active != active:
            continue
        if hook_code is not None and (c.code in hooks) != hook_code:
            continue
        if needle and needle not in normalize(f"{c.code} {c.name_en} {c.name_ar}"):
            continue
        out.append(course_read(db, c, project_id, used, hooks))
    return CourseList(items=out)


def get_course(
    db: Session, p: Principal, code: str, project_id: uuid.UUID | None = None
) -> CourseRead:
    _can_view(p)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    return course_read(db, common.course_or_404(db, code), project_id)


# ---- validation ---------------------------------------------------------------------------------


def _check_codes(db: Session, codes: list[str], field: str, self_code: str) -> None:
    allc = common.courses(db)
    for x in codes:
        if x == self_code:
            raise validation_error(field, "A course cannot refer to itself.")
        c = allc.get(x)
        if c is None or not c.active:
            raise validation_error(field, f"Unknown or inactive course code {x}.")


def _cycle(db: Session, code: str, prereq: list[str]) -> bool:
    graph = {c.code: list(c.prerequisite_codes or []) for c in common.courses(db).values()}
    graph[code] = list(prereq)
    seen: set[str] = set()
    stack = list(prereq)
    while stack:
        x = stack.pop()
        if x == code:
            return True
        if x in seen:
            continue
        seen.add(x)
        stack.extend(graph.get(x, []))
    return False


def _validate(db: Session, c: TrainingCourse) -> None:
    """§3.1 field rules on the resulting row."""
    if c.category == CAT.induction_link:
        if not c.induction_type:
            raise validation_error("induction_link", "Required for category induction_link.")
        return
    if c.induction_type:
        raise validation_error("induction_link", "Only for category induction_link.")
    if c.validity_months is None and c.category != CAT.professional_qualification:
        raise validation_error(
            "validity_months", "Only professional qualifications may have no expiry."
        )
    if c.min_duration_hours is None:
        raise validation_error("min_duration_hours", "Required.")
    if c.max_class_size is None:
        raise validation_error("max_class_size", "Required.")
    modes = set(c.delivery_modes or [])
    if not modes:
        raise validation_error("delivery_modes", "Choose at least one delivery mode.")
    if c.practical_required and modes == {DeliveryMode.e_learning.value}:
        raise _err(
            ErrorCode.PRACTICAL_REQUIRED,
            "A course with a practical assessment cannot be e-learning only.",
            "لا يمكن أن تكون الدورة ذات التقييم العملي تعلماً إلكترونياً فقط.",
        )
    if c.theory_required and c.pass_mark_pct is None:
        raise validation_error("pass_mark_pct", "Required when a theory test is required.")
    if not c.languages_offered:
        raise validation_error("languages_offered", "Choose at least one language.")
    if c.accreditation_bodies_required and (c.internal_allowed or c.contractor_delivery_allowed):
        raise _err(
            ErrorCode.ACCREDITED_PROVIDER_REQUIRED,
            "A course that requires an accredited provider cannot allow internal or contractor "
            "delivery.",
            "الدورة التي تتطلب جهة معتمدة لا تسمح بالتقديم الداخلي أو من المقاول.",
        )
    _check_codes(db, list(c.prerequisite_codes or []), "prerequisite_codes", c.code)
    _check_codes(db, list(c.satisfies or []), "satisfies", c.code)
    if _cycle(db, c.code, list(c.prerequisite_codes or [])):
        raise _err(
            ErrorCode.PREREQUISITE_CYCLE,
            "The prerequisites form a cycle.",
            "المتطلبات المسبقة تشكل حلقة.",
        )
    if c.renewal_course_code:
        r = common.course(db, c.renewal_course_code)
        if r is None or not r.renews_only or c.code not in (r.satisfies or []):
            raise validation_error(
                "renewal_course_code",
                "The renewal course must be renews_only and satisfy this course.",
            )


def _apply(c: TrainingCourse, data: dict[str, Any]) -> None:
    for k, v in data.items():
        if k == "induction_link":
            if v is None:
                c.induction_type = None
                c.induction_project_codes = {}
            else:
                c.induction_type = str(v["induction_type"])
                c.induction_project_codes = {
                    str(pk): code for pk, code in (v.get("project_course_codes") or {}).items()
                }
        elif k == "provider_rule":
            if v is not None:
                c.internal_allowed = bool(v["internal_allowed"])
                c.contractor_delivery_allowed = bool(v["contractor_delivery_allowed"])
                c.accreditation_bodies_required = [
                    str(b) for b in v.get("accreditation_bodies_required") or []
                ]
        elif k in ("delivery_modes", "languages_offered"):
            c.__setattr__(k, [str(x) for x in v or []])
        elif k == "reason":
            continue
        else:
            setattr(c, k, v)


def _manager(p: Principal) -> None:
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()


def create_course(db: Session, p: Principal, body: CourseCreate) -> CourseRead:
    _manager(p)
    code = body.code
    if code in cref.PCT:
        raise _err(
            ErrorCode.CODE_IN_OTHER_CATALOGUE,
            f"{code} is a Phase 4 personnel certificate type; use another code.",
            f"الرمز {code} مستخدم في قائمة شهادات الأفراد (المرحلة 4).",
        )
    if common.course(db, code) is not None:
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("code", f"Course {code} already exists.")
    c = TrainingCourse(id=uuid.uuid4(), code=code, induction_project_codes={}, seeded=False)
    _apply(c, body.model_dump())
    c.code = code
    _validate(db, c)
    cc.stamp(c, p, create=True)
    db.add(c)
    db.flush()
    common.clear_cache(db)
    cc.record(db, p, AuditAction.create, EntityType.training_course, c, None)
    return course_read(db, c)


def _loosening(field: str) -> ApiError:
    return _err(
        ErrorCode.CATALOGUE_LOOSENING,
        f"Catalogue edits may only tighten requirements ({field}).",
        "تعديلات الكتالوج يجب أن تشدد المتطلبات فقط.",
        field=field,
    )


def _tighten_only(c: TrainingCourse, data: dict[str, Any]) -> None:
    """CC-2."""
    if "validity_months" in data:
        new = data["validity_months"]
        old = c.validity_months
        if old is not None and (new is None or new > old):
            raise _loosening("validity_months")
    if "pass_mark_pct" in data and c.pass_mark_pct is not None:
        new = data["pass_mark_pct"]
        if new is None or new < c.pass_mark_pct:
            raise _loosening("pass_mark_pct")
    if "min_duration_hours" in data and c.min_duration_hours is not None:
        new = data["min_duration_hours"]
        if new is None or Decimal(new) < c.min_duration_hours:
            raise _loosening("min_duration_hours")
    if "practical_required" in data and c.practical_required and not data["practical_required"]:
        raise _loosening("practical_required")
    if "theory_required" in data and c.theory_required and not data["theory_required"]:
        raise _loosening("theory_required")
    if "category" in data and data["category"] != c.category:
        raise _loosening("category")
    if "renews_only" in data and data["renews_only"] != c.renews_only:
        raise _loosening("renews_only")
    if "satisfies" in data and not set(data["satisfies"] or []) <= set(c.satisfies or []):
        raise _loosening("satisfies")
    if "provider_rule" in data and data["provider_rule"] is not None:
        r = data["provider_rule"]
        if r["internal_allowed"] and not c.internal_allowed:
            if c.accreditation_bodies_required:
                raise _err(
                    ErrorCode.ACCREDITED_PROVIDER_REQUIRED,
                    "A course that requires an accredited provider cannot allow internal delivery.",
                    "الدورة التي تتطلب جهة معتمدة لا تسمح بالتقديم الداخلي.",
                )
            raise _loosening("provider_rule.internal_allowed")
        if r["contractor_delivery_allowed"] and not c.contractor_delivery_allowed:
            if c.accreditation_bodies_required:
                raise _err(
                    ErrorCode.ACCREDITED_PROVIDER_REQUIRED,
                    "A course that requires an accredited provider cannot allow contractor "
                    "delivery.",
                    "الدورة التي تتطلب جهة معتمدة لا تسمح بالتقديم من المقاول.",
                )
            raise _loosening("provider_rule.contractor_delivery_allowed")
        old_b = set(c.accreditation_bodies_required or [])
        new_b = {str(b) for b in r.get("accreditation_bodies_required") or []}
        if old_b and not new_b:
            raise _loosening("provider_rule.accreditation_bodies_required")


def update_course(db: Session, p: Principal, code: str, body: CourseUpdate) -> CourseRead:
    _manager(p)
    c = common.course_or_404(db, code)
    data = body.model_dump(exclude_unset=True)
    _tighten_only(c, data)
    before = cc.snap(c)
    old_validity = c.validity_months
    _apply(c, data)
    _validate(db, c)
    cc.stamp(c, p)
    db.flush()
    common.clear_cache(db)
    recomputed: int | None = None
    if "validity_months" in data and c.validity_months != old_validity:
        recomputed = _recompute_validity(db, c)
    cc.record(
        db,
        p,
        AuditAction.update,
        EntityType.training_course,
        c,
        None,
        before,
        details={"reason": data.get("reason"), "records_recomputed": recomputed},
    )
    return course_read(db, c, recomputed=recomputed)


def _recompute_validity(db: Session, c: TrainingCourse) -> int:
    """CC-2: a validity shortening recomputes every record's stored valid_until (strictest)
    and alerts holders whose record now expires within 30 days."""
    from app.services.cert import events  # noqa: PLC0415

    n = 0
    soon = today() + timedelta(days=30)
    changed: list[uuid.UUID] = []
    for r in db.scalars(select(TrainingRecord).where(TrainingRecord.course_code == c.code)):
        vu, lf = tval.stored_validity(c, r.completed_on, r.printed_expiry)
        if vu != r.valid_until:
            r.valid_until = vu
            r.limiting_factor = lf
            n += 1
            changed.append(r.worker_id)
            if vu is not None and vu <= soon and r.status.value == "accepted":
                _alert_shortened(db, r)
    db.flush()
    if changed:
        events.publish(db, "training.record_changed", worker_ids=changed)
    return n


def _alert_shortened(db: Session, r: TrainingRecord) -> None:
    from app.models import Deployment  # noqa: PLC0415

    for dep in db.scalars(select(Deployment).where(Deployment.worker_id == r.worker_id)):
        if dep.status.value == "demobilised":
            continue
        users = alerts.reps(db, dep.project_id, dep.engagement_id) | alerts.officers(
            db, dep.project_id
        )
        alerts.send(
            db,
            users,
            NotificationKind.training_record_expiry,
            f"Training record {r.record_no} ({r.course_code}) now expires on {r.valid_until}",
            f"السجل التدريبي {r.record_no} ({r.course_code}) ينتهي الآن في {r.valid_until}",
            EntityType.training_record,
            r.id,
            dep.project_id,
        )


def delete_course(db: Session, p: Principal, code: str) -> None:
    _manager(p)
    c = common.course_or_404(db, code)
    if c.seeded or c.code in in_use_codes(db) or c.code in hook_codes_all(db):
        raise _err(
            ErrorCode.COURSE_IN_USE,
            "The course is in use; make it inactive instead.",
            "الدورة مستخدمة؛ اجعلها غير فعالة بدلاً من ذلك.",
            status=409,
        )
    others = db.scalar(
        select(func.count())
        .select_from(TrainingCourse)
        .where(TrainingCourse.prerequisite_codes.any(c.code))  # type: ignore[arg-type]
    )
    if others:
        raise _err(
            ErrorCode.COURSE_IN_USE,
            "Another course lists it as a prerequisite.",
            "دورة أخرى تعتبرها متطلباً مسبقاً.",
            status=409,
        )
    cc.record(db, p, AuditAction.archive, EntityType.training_course, c, None)
    db.delete(c)
    db.flush()
    common.clear_cache(db)
