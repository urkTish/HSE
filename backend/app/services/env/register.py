"""Aspects and impacts (§3.1, §4.1, ASP-1…ASP-3), the org-wide provider register (§3.2, PRV) and
permits / licences (§3.3, §4.2, PRM-1…PRM-5) of spec 6e-environmental."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.env_enums import (
    AspectAction,
    AspectStatus,
    PermitAction,
    PermitStatus,
    PermitType,
    ProviderAction,
    ProviderKind,
    ProviderStatus,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import ControlLevel
from app.models import EnvAspect, EnvPermit, EnvProvider, Project
from app.schemas.env import (
    AspectControl,
    AspectCreate,
    AspectPage,
    AspectRead,
    AspectTransition,
    AspectUpdate,
    Facility,
    MonitoringLink,
    PermitCondition,
    PermitCreate,
    PermitPage,
    PermitRead,
    PermitScope,
    PermitTransition,
    PermitUpdate,
    ProviderCreate,
    ProviderPage,
    ProviderRead,
    ProviderTransition,
    ProviderUpdate,
)
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal, forbidden_error

C = Capability
ET = EntityType
NK = NotificationKind


def _conflict(en: str, ar: str = "لا يمكن تنفيذ هذا الإجراء في الحالة الحالية.") -> ApiError:
    return ApiError(409, ErrorCode.INVALID_TRANSITION, en, ar)


# ---- aspects -------------------------------------------------------------------------------------


def score(a: EnvAspect) -> int:
    return a.severity * a.likelihood


def significant(a: EnvAspect) -> bool:
    """ASP-1."""
    return score(a) >= 12 or a.legal_requirement or a.stakeholder_concern


def aspect_read(a: EnvAspect) -> AspectRead:
    return AspectRead(
        id=a.id, project_id=a.project_id, aspect_no=a.aspect_no, activity=a.activity,
        aspect=a.aspect, impact=a.impact, condition=a.condition, site_ids=list(a.site_ids or []),
        engagement_ids=list(a.engagement_ids or []), severity=a.severity,
        likelihood=a.likelihood, legal_requirement=a.legal_requirement,
        permit_ids=list(a.permit_ids or []), stakeholder_concern=a.stakeholder_concern,
        score=score(a), significant=significant(a),
        controls=[AspectControl.model_validate(x) for x in a.controls or []],
        monitoring_links=[MonitoringLink.model_validate(x) for x in a.monitoring_links or []],
        activated_on=a.activated_on, review_due_on=a.review_due_on, review_flag=a.review_flag,
        status=a.status, status_reason=a.status_reason,
    )  # fmt: skip


def _check_codes(aspect: str | None, impact: str | None) -> None:
    from app.core.env_enums import AspectCode, ImpactCode  # noqa: PLC0415

    if aspect is not None and aspect not in {x.value for x in AspectCode}:
        raise validation_error("aspect", "Use a list AS code.")
    if impact is not None and impact not in {x.value for x in ImpactCode}:
        raise validation_error("impact", "Use a list IM code.")


def _aspect(db: Session, p: Principal, aspect_id: uuid.UUID) -> EnvAspect:
    a = db.get(EnvAspect, aspect_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Aspect")
    ec.need(p, a.project_id, C.env_view, write=False)
    return a


def _links(data: dict[str, Any]) -> None:
    for k in ("controls", "monitoring_links"):
        if k in data and data[k] is not None:
            data[k] = [
                {kk: (str(vv) if isinstance(vv, uuid.UUID) else getattr(vv, "value", vv))
                 for kk, vv in x.items()}
                for x in data[k]
            ]  # fmt: skip


def list_aspects(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: list[AspectStatus] | None,
    sig: bool | None,
    site_id: uuid.UUID | None,
    page: int,
    size: int,
) -> AspectPage:
    ec.view_grant(db, p, project_id)
    rows = list(
        db.scalars(
            select(EnvAspect).where(EnvAspect.project_id == project_id).order_by(EnvAspect.seq)
        )
    )
    rows = [
        a for a in rows
        if (not status or a.status in status) and (sig is None or significant(a) == sig)
        and (site_id is None or site_id in (a.site_ids or []))
    ]  # fmt: skip
    return AspectPage(
        items=[aspect_read(a) for a in rows[(page - 1) * size : page * size]],
        total=len(rows), page=page, page_size=size,
    )  # fmt: skip


def create_aspect(
    db: Session, p: Principal, project_id: uuid.UUID, body: AspectCreate
) -> AspectRead:
    pr = ec.project(db, p, project_id)
    p.require(project_id, C.env_aspect_manage)
    _check_codes(body.aspect, body.impact)
    for s in body.site_ids:
        ec.site_of(db, project_id, s)
    seq = (
        int(
            db.scalar(select(func.max(EnvAspect.seq)).where(EnvAspect.project_id == project_id))
            or 0
        )
        + 1
    )
    data = body.model_dump()
    _links(data)
    a = EnvAspect(
        id=uuid.uuid4(), project_id=project_id, aspect_no=f"ASP-{pr.code}-{seq:03d}", seq=seq,
        status=AspectStatus.draft, created_by_user_id=p.user.id,
        **{**data, "activity": body.activity.value, "condition": body.condition},
    )  # fmt: skip
    db.add(a)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_aspect, a, project_id)
    return aspect_read(a)


def read_aspect(db: Session, p: Principal, aspect_id: uuid.UUID) -> AspectRead:
    return aspect_read(_aspect(db, p, aspect_id))


def update_aspect(
    db: Session, p: Principal, aspect_id: uuid.UUID, body: AspectUpdate
) -> AspectRead:
    a = _aspect(db, p, aspect_id)
    p.require(a.project_id, C.env_aspect_manage)
    if a.status == AspectStatus.archived:
        raise _conflict("An archived aspect cannot be edited.")
    data = body.model_dump(exclude_unset=True)
    _check_codes(data.get("aspect"), data.get("impact"))
    _links(data)
    if "activity" in data and data["activity"] is not None:
        data["activity"] = data["activity"].value
    for k, v in data.items():
        setattr(a, k, v)
    if a.status == AspectStatus.active:
        _asp2(a)
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_aspect, a, a.project_id)
    return aspect_read(a)


def _asp2(a: EnvAspect) -> None:
    """ASP-2: a significant entry needs ≥ 1 control and ≥ 1 monitoring link; PPE alone refused."""
    if not significant(a):
        return
    if a.controls and all(x.get("control_level") == ControlLevel.ppe.value for x in a.controls):
        raise ec.code_err(
            ErrorCode.CONTROL_LEVEL_TOO_LOW,
            "PPE alone cannot be the only control of a significant aspect.",
            "لا يمكن أن تكون معدات الوقاية الشخصية الضابط الوحيد لجانب جوهري.",
        )
    if not a.controls or not a.monitoring_links:
        raise ec.code_err(
            ErrorCode.ASPECT_CONTROL_REQUIRED,
            "A significant aspect needs at least one control and one monitoring link.",
            "يتطلب الجانب الجوهري ضابطاً واحداً ورابط رصد واحداً على الأقل.",
        )


def _review_due(db: Session, a: EnvAspect, d: date) -> date:
    from app.services.train.common import add_months  # noqa: PLC0415

    return add_months(d, int(ec.cfg(db, a.project_id)["aspect_review_months"])) - timedelta(days=1)


def transition_aspect(
    db: Session, p: Principal, aspect_id: uuid.UUID, body: AspectTransition
) -> AspectRead:
    a = _aspect(db, p, aspect_id)
    p.require(a.project_id, C.env_aspect_manage)
    today = ec.local_day()
    if body.action == AspectAction.activate:
        if a.status != AspectStatus.draft:
            raise _conflict("Only a draft aspect can be activated.")
        _asp2(a)
        a.status = AspectStatus.active
        a.activated_on = today
        a.review_due_on = _review_due(db, a, today)
    elif body.action == AspectAction.archive:
        if a.status == AspectStatus.archived:
            raise _conflict("The aspect is already archived.")
        a.status_reason = ec.reason(body.reason, 20)
        a.status = AspectStatus.archived
    else:
        if a.status != AspectStatus.active:
            raise _conflict("Only an active aspect can be reviewed.")
        _asp2(a)
        a.review_due_on = _review_due(db, a, today)
        a.review_flag = False
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.env_aspect, a, a.project_id, None,
              details={"action": body.action.value})  # fmt: skip
    return aspect_read(a)


def flag_aspects(db: Session, project_id: uuid.UUID, site_id: uuid.UUID, codes: set[str],
                 why: str) -> int:  # fmt: skip
    """ASP-3: set review_flag on Active entries of the site whose aspect matches; one alert per
    entry to the HSE Officers."""
    n = 0
    for a in db.scalars(
        select(EnvAspect).where(
            EnvAspect.project_id == project_id, EnvAspect.status == AspectStatus.active
        )
    ):
        if a.aspect not in codes or site_id not in (a.site_ids or []):
            continue
        a.review_flag = True
        n += 1
        if ec.once(db, f"env:aspect_flag:{a.id}:{why}"):
            ec.send(
                db, ec.officers(db, project_id), NK.aspect_review,
                f"{a.aspect_no} needs review: {why}", f"يحتاج {a.aspect_no} إلى مراجعة: {why}",
                project_id, ET.env_aspect, a.id,
            )  # fmt: skip
    db.flush()
    return n


# ---- providers -----------------------------------------------------------------------------------


def provider_read(db: Session, pv: EnvProvider, with_licences: bool = True) -> ProviderRead:
    return ProviderRead(
        id=pv.id, provider_code=pv.provider_code, name_en=pv.name_en, name_ar=pv.name_ar,
        cr_number=pv.cr_number, kinds=[ProviderKind(k) for k in pv.kinds or []],
        facilities=[Facility.model_validate(x) for x in pv.facilities or []],
        contact_email=pv.contact_email, phone=pv.phone, status=pv.status,
        status_reason=pv.status_reason,
        licences=[permit_read(db, x) for x in ec.licences(db, pv.id)] if with_licences else [],
    )  # fmt: skip


def _any_view(p: Principal) -> None:
    if not p.has_any(C.env_view):
        raise forbidden_error()


def _provider(db: Session, p: Principal, provider_id: uuid.UUID) -> EnvProvider:
    _any_view(p)
    pv = db.get(EnvProvider, provider_id)
    if pv is None:
        raise not_found("Provider")
    return pv


def list_providers(
    db: Session, p: Principal, kind: ProviderKind | None, page: int, size: int
) -> ProviderPage:
    _any_view(p)
    rows = list(db.scalars(select(EnvProvider).order_by(EnvProvider.provider_code)))
    if kind is not None:
        rows = [x for x in rows if kind.value in (x.kinds or [])]
    return ProviderPage(
        items=[provider_read(db, x) for x in rows[(page - 1) * size : page * size]],
        total=len(rows), page=page, page_size=size,
    )  # fmt: skip


def _writer(p: Principal, cap: Capability) -> None:
    p.ensure_writer()
    if not p.has_any(cap):
        raise forbidden_error()


def _facilities(kinds: list[ProviderKind], fac: list[Facility]) -> None:
    need = {ProviderKind.recycler, ProviderKind.treatment_facility, ProviderKind.landfill}
    if set(kinds) & need and not fac:
        raise validation_error("facilities", "Recyclers, treatment facilities and landfills "
                               "need at least one facility.")  # fmt: skip


def create_provider(db: Session, p: Principal, body: ProviderCreate) -> ProviderRead:
    _writer(p, C.env_permit_manage)
    if db.scalar(select(EnvProvider.id).where(EnvProvider.provider_code == body.provider_code)):
        raise ApiError(
            409, ErrorCode.DUPLICATE_VALUE, "This provider code exists.", "الرمز مستخدم."
        )
    _facilities(body.kinds, body.facilities)
    data = body.model_dump(mode="json")
    pv = EnvProvider(id=uuid.uuid4(), status=ProviderStatus.approved,
                     created_by_user_id=p.user.id, **data)  # fmt: skip
    db.add(pv)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_provider, pv, None)
    return provider_read(db, pv)


def read_provider(db: Session, p: Principal, provider_id: uuid.UUID) -> ProviderRead:
    return provider_read(db, _provider(db, p, provider_id))


def update_provider(
    db: Session, p: Principal, provider_id: uuid.UUID, body: ProviderUpdate
) -> ProviderRead:
    pv = _provider(db, p, provider_id)
    _writer(p, C.env_permit_manage)
    data = body.model_dump(exclude_unset=True, mode="json")
    for k, v in data.items():
        setattr(pv, k, v)
    _facilities([ProviderKind(k) for k in pv.kinds], [Facility.model_validate(x)
                                                       for x in pv.facilities or []])  # fmt: skip
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_provider, pv, None)
    return provider_read(db, pv)


def transition_provider(
    db: Session, p: Principal, provider_id: uuid.UUID, body: ProviderTransition
) -> ProviderRead:
    """PRV-1: approve / suspend / blacklist by 213 (HSE Manager)."""
    pv = _provider(db, p, provider_id)
    _writer(p, C.env_settings)
    to = {
        ProviderAction.approve: ProviderStatus.approved,
        ProviderAction.suspend: ProviderStatus.suspended,
        ProviderAction.blacklist: ProviderStatus.blacklisted,
    }[body.action]
    if pv.status == to:
        raise _conflict(f"The provider is already {to.value}.")
    pv.status_reason = ec.reason(body.reason, 20) if to != ProviderStatus.approved else None
    pv.status = to
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.env_provider, pv, None,
              details={"action": body.action.value})  # fmt: skip
    return provider_read(db, pv)


# ---- permits and licences ------------------------------------------------------------------------


def permit_read(db: Session, pm: EnvPermit) -> PermitRead:
    today = ec.local_day()
    return PermitRead(
        id=pm.id, record_no=pm.record_no, project_id=pm.project_id, provider_id=pm.provider_id,
        permit_type=pm.permit_type, issuer=pm.issuer, requirement_code=pm.requirement_code,
        required=pm.required, applies_from=pm.applies_from, applies_to=pm.applies_to,
        reference_no=pm.reference_no, scope=PermitScope.model_validate(pm.scope or {}),
        valid_from=pm.valid_from, valid_to=pm.valid_to,
        conditions=[PermitCondition.model_validate(x) for x in pm.conditions or []],
        document_id=pm.document_id, supersedes_id=pm.supersedes_id,
        status=ec.permit_status(db, pm, today),
        days_to_expiry=(pm.valid_to - today).days if pm.valid_to else None,
        status_reason=pm.status_reason,
    )  # fmt: skip


def _permit(db: Session, p: Principal, permit_id: uuid.UUID) -> EnvPermit:
    pm = db.get(EnvPermit, permit_id)
    if pm is None:
        raise not_found("Permit")
    if pm.project_id is not None:
        if not p.can_see_project(pm.project_id):
            raise not_found("Permit")
        ec.need(p, pm.project_id, C.env_view, write=False)
    else:
        _any_view(p)
    return pm


def list_permits(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: list[PermitStatus] | None,
    permit_type: PermitType | None,
    within: int | None,
    page: int,
    size: int,
) -> PermitPage:
    ec.view_grant(db, p, project_id)
    today = ec.local_day()
    rows = ec.project_permits(db, project_id)
    out = []
    for pm in rows:
        st = ec.permit_status(db, pm, today)
        if status and st not in status:
            continue
        if permit_type and pm.permit_type != permit_type:
            continue
        if within is not None and (pm.valid_to is None or not 0 <= (pm.valid_to - today).days
                                   <= within or st == PermitStatus.superseded):  # fmt: skip
            continue
        out.append(pm)
    return PermitPage(
        items=[permit_read(db, x) for x in out[(page - 1) * size : page * size]],
        total=len(out), page=page, page_size=size,
    )  # fmt: skip


def _validate_permit(pm: EnvPermit, pending: bool) -> None:
    info = rf.PT_INFO[pm.permit_type]
    holder = "project" if pm.project_id else "provider"
    if info[2] not in (holder, "either"):
        raise validation_error("permit_type", f"{pm.permit_type.value} is a {info[2]} record.")
    if not pending and not pm.reference_no:
        raise validation_error("reference_no", "Give the permit reference (or mark it pending).")
    if not pending and pm.valid_to is None and info[3] and pm.permit_type not in ec.NO_EXPIRY:
        raise validation_error("valid_to", "This permit type has an expiry date.")
    if pm.valid_from and pm.valid_to and pm.valid_to < pm.valid_from:
        raise validation_error("valid_to", "valid_to is before valid_from.")
    if holder == "project" and pm.required and not pm.requirement_code:
        raise validation_error("requirement_code", "A required permit needs a requirement code.")
    if holder == "provider" and pm.permit_type != PermitType.lab_accreditation:
        sc = pm.scope or {}
        if not sc.get("activities") or not sc.get("waste_classes"):
            raise validation_error("scope", "A provider licence needs activities and classes.")


def create_permit(
    db: Session,
    p: Principal,
    project_id: uuid.UUID | None,
    provider_id: uuid.UUID | None,
    body: PermitCreate,
) -> PermitRead:
    if project_id is not None:
        pr = ec.project(db, p, project_id)
        p.require(project_id, C.env_permit_manage)
        code = pr.code
        n = db.scalar(select(func.max(EnvPermit.seq)).where(EnvPermit.project_id == project_id))
    else:
        pv = _provider(db, p, provider_id)  # type: ignore[arg-type]
        _writer(p, C.env_permit_manage)
        code = pv.provider_code
        n = db.scalar(select(func.max(EnvPermit.seq)).where(EnvPermit.provider_id == provider_id))
    seq = int(n or 0) + 1
    data = body.model_dump(mode="json", exclude={"pending"})
    for k in ("applies_from", "applies_to", "valid_from", "valid_to"):
        data[k] = getattr(body, k)
    for k in ("document_id", "supersedes_id"):
        data[k] = getattr(body, k)
    pm = EnvPermit(
        id=uuid.uuid4(), record_no=f"EPL-{code}-{seq:03d}", project_id=project_id,
        provider_id=provider_id, seq=seq, created_by_user_id=p.user.id,
        manual_status=PermitStatus.pending if body.pending else None, **data,
    )  # fmt: skip
    _validate_permit(pm, body.pending)
    if pm.supersedes_id is not None:
        old = db.get(EnvPermit, pm.supersedes_id)
        if (
            old is None
            or old.project_id != project_id
            or old.provider_id != provider_id
            or (old.requirement_code != pm.requirement_code)
        ):
            raise validation_error("supersedes_id", "Supersede a record of the same holder and "
                                   "requirement.")  # fmt: skip
    db.add(pm)
    db.flush()
    ec.clear_cache(db)
    ec.record(db, p, AuditAction.create, ET.env_permit, pm, project_id)
    return permit_read(db, pm)


def read_permit(db: Session, p: Principal, permit_id: uuid.UUID) -> PermitRead:
    return permit_read(db, _permit(db, p, permit_id))


def _permit_writer(p: Principal, pm: EnvPermit) -> None:
    if pm.project_id is not None:
        p.require(pm.project_id, C.env_permit_manage)
    else:
        _writer(p, C.env_permit_manage)


def update_permit(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PermitUpdate
) -> PermitRead:
    pm = _permit(db, p, permit_id)
    _permit_writer(p, pm)
    data = body.model_dump(exclude_unset=True)
    js = body.model_dump(mode="json", exclude_unset=True)
    for k, v in data.items():
        setattr(pm, k, js[k] if k in ("conditions", "scope") else v)
    if pm.manual_status == PermitStatus.pending and pm.reference_no and pm.valid_from:
        pm.manual_status = None
    _validate_permit(pm, pm.manual_status == PermitStatus.pending)
    db.flush()
    ec.clear_cache(db)
    ec.record(db, p, AuditAction.update, ET.env_permit, pm, pm.project_id)
    return permit_read(db, pm)


def transition_permit(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PermitTransition
) -> PermitRead:
    pm = _permit(db, p, permit_id)
    _permit_writer(p, pm)
    if body.action == PermitAction.reinstate:
        if pm.manual_status != PermitStatus.suspended:
            raise _conflict("Only a suspended record can be reinstated.")
        pm.manual_status, pm.manual_from, pm.status_reason = None, None, None
    else:
        if pm.manual_status in (PermitStatus.cancelled,):
            raise _conflict("The record is cancelled.")
        pm.status_reason = ec.reason(body.reason, 20)
        pm.manual_status = (PermitStatus.suspended if body.action == PermitAction.suspend
                            else PermitStatus.cancelled)  # fmt: skip
        pm.manual_from = ec.local_day()
    db.flush()
    ec.clear_cache(db)
    ec.record(db, p, AuditAction.status_change, ET.env_permit, pm, pm.project_id,
              details={"action": body.action.value})  # fmt: skip
    return permit_read(db, pm)


def project_of(db: Session, project_id: uuid.UUID) -> Project:
    pr = db.get(Project, project_id)
    if pr is None:
        raise not_found("Project")
    return pr
