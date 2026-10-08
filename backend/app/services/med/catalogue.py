"""Fitness code catalogue and reference lists (spec 6a-occupational-health §3.1, §3.10,
MC-1…MC-5)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.med_enums import (
    AssessmentType,
    ExaminerClass,
    ExposureGroup,
    FitnessCategory,
    FitnessOutcome,
    HoldReason,
    MedicalProviderKind,
    ReferralReason,
    RestrictionCode,
    TypicalTest,
)
from app.models import (
    AccessSettings,
    FitnessCode,
    FitnessLine,
    MedicalPlanLine,
    TrainingCourse,
    ZoneAccessProfile,
)
from app.schemas.hse_common import LabelledCode
from app.schemas.medical import (
    FitnessCodeCreate,
    FitnessCodeList,
    FitnessCodeRead,
    FitnessCodeUpdate,
    FitnessReference,
    RestrictionInfo,
)
from app.services.cert import common as cc
from app.services.med import common, engine
from app.services.med import reference as ref
from app.services.permissions import Principal, forbidden_error

C = Capability
MF = HookKind.medical_fitness.value


def _lc(code: str, en: str, ar: str) -> LabelledCode:
    return LabelledCode(code=code, label_en=en, label_ar=ar)


def reference(db: Session, p: Principal) -> FitnessReference:
    return FitnessReference(
        restrictions=[
            RestrictionInfo(
                code=r,
                label_en=v[0],
                label_ar=v[1],
                value_kind=v[2],
                negates=list(v[3]),
                review_required=v[4],
            )
            for r, v in ref.RESTRICTIONS.items()
        ],
        exposure_groups=[_lc(g.value, *ref.EXPOSURE_LABELS[g]) for g in ExposureGroup],
        outcomes=[_lc(o.value, *ref.OUTCOME_LABELS[o]) for o in FitnessOutcome],
        assessment_types=[_lc(t.value, *ref.TYPE_LABELS[t]) for t in AssessmentType],
        examiner_classes=[_lc(x.value, *ref.EXAMINER_LABELS[x]) for x in ExaminerClass],
        categories=[_lc(x.value, *ref.CATEGORY_LABELS[x]) for x in FitnessCategory],
        hold_reasons=[_lc(x.value, *ref.HOLD_LABELS[x]) for x in HoldReason],
        referral_reasons=[_lc(x.value, *ref.REFERRAL_LABELS[x]) for x in ReferralReason],
        typical_tests=[_lc(x.value, *ref.TEST_LABELS[x]) for x in TypicalTest],
        hints=[_lc(*h) for h in ref.HINTS],
    )


# ---- hook use (HK6-2) ----------------------------------------------------------------------------


def attach_codes(db: Session, project_id: uuid.UUID | None = None) -> set[str]:
    """Codes used by a Phase 2/3 medical attach point (on one project or any)."""
    out: set[str] = set()
    q = select(AccessSettings)
    if project_id is not None:
        q = q.where(AccessSettings.project_id == project_id)
    for s in db.scalars(q):
        for h in s.project_hook_requirements or []:
            if h.get("kind") == MF:
                out.add(str(h["code"]))
        for m in (s.hook_requirements_by_adp_category, s.hook_requirements_by_crew_role):
            for items in (m or {}).values():
                out |= {str(h["code"]) for h in items or [] if h.get("kind") == MF}
    zq = select(ZoneAccessProfile)
    if project_id is not None:
        zq = zq.where(ZoneAccessProfile.project_id == project_id)
    for zp in db.scalars(zq):
        out |= {str(h["code"]) for h in zp.hook_requirements or [] if h.get("kind") == MF}
    from app.services.ptw import reference as pref  # noqa: PLC0415

    out |= {c for codes in pref.MEDICAL_CREW_HOOKS.values() for c in codes}
    out.add(pref.MEDICAL_WAH_CODE)
    out |= set(pref.MEDICAL_OPERATOR_CODES.values())
    return out


def _in_use(db: Session, code: str) -> bool:
    n = db.scalar(select(func.count()).select_from(FitnessLine).where(FitnessLine.code == code))
    if n:
        return True
    m = db.scalar(
        select(func.count()).select_from(MedicalPlanLine).where(MedicalPlanLine.code == code)
    )
    return bool(m)


def code_read(
    db: Session, fc: FitnessCode, project_id: uuid.UUID | None = None, hooks: set[str] | None = None
) -> FitnessCodeRead:
    eff = None
    crit = None
    if project_id is not None:
        s = common.settings(db, project_id)
        ov = common.override_months(s, fc.code)
        eff = min(ov, fc.validity_months) if ov is not None else fc.validity_months
        crit = fc.code in common.critical_codes(s)
    return FitnessCodeRead(
        id=fc.id,
        code=fc.code,
        name_en=fc.name_en,
        name_ar=fc.name_ar,
        category=fc.category,
        validity_months=fc.validity_months,
        examiner_classes=[ExaminerClass(x) for x in fc.examiner_classes or []],
        provider_kinds=[MedicalProviderKind(x) for x in fc.provider_kinds or []],
        typical_tests=[TypicalTest(x) for x in fc.typical_tests or []],
        negated_by=[RestrictionCode(x) for x in common.negated_by(fc)],
        hook_code=fc.code in (hooks if hooks is not None else attach_codes(db)),
        in_use=_in_use(db, fc.code),
        active=fc.active,
        effective_validity_months=eff,
        critical_on_project=crit,
    )


def _view(p: Principal) -> None:
    if not p.has_any(C.fitness_catalogue_view):
        raise forbidden_error()


def list_codes(
    db: Session, p: Principal, project_id: uuid.UUID | None, include_inactive: bool = True
) -> FitnessCodeList:
    _view(p)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    hooks = attach_codes(db)
    order = {c: i for i, c in enumerate(ref.CODES)}
    rows = sorted(common.codes(db).values(), key=lambda c: (order.get(c.code, 99), c.code))
    return FitnessCodeList(
        items=[code_read(db, c, project_id, hooks) for c in rows if include_inactive or c.active]
    )


def _get(db: Session, code: str) -> FitnessCode:
    fc = common.code(db, code)
    if fc is None:
        raise not_found("Fitness code")
    return fc


def get_code(
    db: Session, p: Principal, code: str, project_id: uuid.UUID | None = None
) -> FitnessCodeRead:
    _view(p)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    return code_read(db, _get(db, code), project_id)


def _manager(p: Principal) -> None:
    p.ensure_writer()
    if not p.is_manager:  # capability 147 is the HSE Manager's
        raise forbidden_error()


def other_catalogue(db: Session, code: str) -> bool:
    """MC-2: Phase 4 list PCT / custom certificate types, Phase 5 courses and Phase 2 induction
    / training hook codes."""
    from app.services.cert import settings as cset  # noqa: PLC0415

    if cset.is_type(db, code) or code in cset.training_codes(db):
        return True
    return db.scalar(select(TrainingCourse.id).where(TrainingCourse.code == code)) is not None


def _kinds_ok(category: FitnessCategory, kinds: list[str]) -> None:
    if MedicalProviderKind.contractor_clinic.value in kinds and category != FitnessCategory.general:
        raise common.err(
            422,
            ErrorCode.PROVIDER_KIND_NOT_ALLOWED,
            "Contractor clinics may be allowed only for general fitness codes (MC-4).",
            "لا يسمح بعيادات المقاولين إلا لرموز اللياقة العامة.",
        )


def create_code(db: Session, p: Principal, body: FitnessCodeCreate) -> FitnessCodeRead:
    _manager(p)
    code = body.code
    if common.code(db, code) is not None:
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("code", f"Fitness code {code} already exists.")
    if other_catalogue(db, code):
        raise common.err(
            422,
            ErrorCode.CODE_IN_OTHER_CATALOGUE,
            f"{code} exists in the Phase 4 or Phase 5 catalogue; use another code (MC-2).",
            f"الرمز {code} مستخدم في فهرس آخر.",
        )
    exc = [x.value for x in body.examiner_classes]
    if ExaminerClass.nurse.value in exc:
        raise validation_error("examiner_classes", "A nurse never signs a fitness line (EX-3).")
    kinds = list(dict.fromkeys(x.value for x in body.provider_kinds))
    _kinds_ok(body.category, kinds)
    fc = FitnessCode(
        id=uuid.uuid4(),
        code=code,
        name_en=body.name_en,
        name_ar=body.name_ar,
        category=body.category,
        validity_months=body.validity_months,
        examiner_classes=list(dict.fromkeys(exc)),
        provider_kinds=kinds,
        typical_tests=[x.value for x in body.typical_tests],
        extra_negated_by=[],
        active=body.active,
        seeded=False,
    )
    cc.stamp(fc, p, create=True)
    db.add(fc)
    db.flush()
    common.clear_cache(db)
    common.record(db, p, AuditAction.create, EntityType.fitness_code, fc, None)
    return code_read(db, fc)


def _loosening(what: str) -> Exception:
    return common.err(
        422,
        ErrorCode.CATALOGUE_LOOSENING,
        f"Catalogue edits may only tighten ({what}).",
        "تعديلات الفهرس يجب أن تكون أكثر تشدداً فقط.",
    )


def update_code(db: Session, p: Principal, code: str, body: FitnessCodeUpdate) -> FitnessCodeRead:
    _manager(p)
    fc = _get(db, code)
    before = common.snap(fc)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is None:
            raise validation_error(k, "Cannot be null.")
    if "provider_kinds" in data:
        kinds = list(dict.fromkeys(getattr(x, "value", x) for x in data["provider_kinds"]))
        _kinds_ok(fc.category, kinds)
        if not set(kinds) <= set(fc.provider_kinds or []):
            raise _loosening("provider kinds may only be removed")
        if not kinds:
            raise validation_error("provider_kinds", "At least one provider kind.")
        fc.provider_kinds = kinds
    if "examiner_classes" in data:
        exc = list(dict.fromkeys(getattr(x, "value", x) for x in data["examiner_classes"]))
        if not set(exc) <= set(fc.examiner_classes or []):
            raise _loosening("examiner classes may only be removed")
        if not exc:
            raise validation_error("examiner_classes", "At least one examiner class.")
        fc.examiner_classes = exc
    shortened = False
    if "validity_months" in data:
        months = int(data["validity_months"])
        if months > fc.validity_months:
            raise _loosening("validity may only be shortened")
        shortened = months < fc.validity_months
        fc.validity_months = months
    if "negated_by" in data:
        new = [getattr(x, "value", x) for x in data["negated_by"]]
        if not set(common.negated_by(fc)) <= set(new):
            raise _loosening("negating restrictions may only be added")
        base = {r.value for r, v in ref.RESTRICTIONS.items() if fc.code in v[3]}
        fc.extra_negated_by = sorted(set(new) - base)
    for k in ("name_en", "name_ar", "active"):
        if k in data:
            setattr(fc, k, data[k])
    if "typical_tests" in data:
        fc.typical_tests = [getattr(x, "value", x) for x in data["typical_tests"]]
    cc.stamp(fc, p)
    db.flush()
    common.clear_cache(db)
    if shortened:
        _recompute(db, fc)
    common.record(db, p, AuditAction.update, EntityType.fitness_code, fc, None, before)
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "medical.fitness_changed")
    return code_read(db, fc)


def _recompute(db: Session, fc: FitnessCode) -> None:
    """MC-3: a shorter validity recomputes every line's stored valid_until; workers whose line
    now expires within 30 days are alerted (as Phase 5 CC-2)."""
    from app.models import FitnessAssessment  # noqa: PLC0415
    from app.services.med import alerts  # noqa: PLC0415

    d = common.today_local()
    affected: list[tuple[uuid.UUID, uuid.UUID]] = []
    for ln, a in db.execute(
        select(FitnessLine, FitnessAssessment)
        .join(FitnessAssessment, FitnessAssessment.id == FitnessLine.assessment_id)
        .where(FitnessLine.code == fc.code)
    ):
        vu, factor = engine.stored_validity(
            fc, a.examined_on, ln.outcome, ln.restrictions or [], ln.restriction_review_date,
            ln.printed_next_due,
        )  # fmt: skip
        if vu != ln.valid_until:
            ln.valid_until, ln.limiting_factor = vu, factor
            if (
                vu is not None
                and vu <= d + timedelta(days=30)
                and ln.line_state.value == "governing"
            ):
                affected.append((a.worker_id, a.project_id))
    db.flush()
    for wid, pid in affected:
        alerts.catalogue_shortened(db, pid, wid, fc.code)


def delete_code(db: Session, p: Principal, code: str) -> None:
    _manager(p)
    fc = _get(db, code)
    if _in_use(db, code) or code in attach_codes(db):
        raise common.err(
            409,
            ErrorCode.FITNESS_CODE_IN_USE,
            "The code is in use: make it inactive instead (MC-1).",
            "الرمز مستخدم: اجعله غير فعال بدلاً من حذفه.",
        )
    before = common.snap(fc)
    db.delete(fc)
    db.flush()
    common.clear_cache(db)
    from app.services import audit  # noqa: PLC0415

    audit.record(
        db, AuditAction.archive, p.actor(None), entity_type=EntityType.fitness_code,
        entity_id=fc.id, before=before,
    )  # fmt: skip
