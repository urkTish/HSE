"""Helpers shared by the Phase 4 services (spec 4-third-party-cert): roles and scope, refs,
normalisation, errors and warnings."""

import re
import uuid
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    EquipmentDeploymentStatus,
    LimitationCode,
    PersonnelLimitationCode,
    TpiStatus,
)
from app.core.clock import today
from app.core.enums import Capability, Role
from app.core.errors import ApiError, ErrorCode, not_found
from app.models import (
    Contractor,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    Project,
    ProjectEngagement,
    Scaffold,
    Tpi,
)
from app.schemas.cert_common import (
    CertLineRef,
    DefectRef,
    DeploymentRef,
    EquipmentLimitationRead,
    EquipmentRef,
    PersonnelLimitationRead,
    ScaffoldRef,
    TpiRef,
)
from app.schemas.hse_common import ApiWarning, UserRef
from app.services.access import common as acommon
from app.services.cert import reference as ref
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
LIVE_DEPLOYMENT = (
    EquipmentDeploymentStatus.planned,
    EquipmentDeploymentStatus.approved,
    EquipmentDeploymentStatus.on_site,
)
CONTRACTOR_ROLES = frozenset({Role.contractor_hse_rep, Role.permit_receiver})

# ---- normalisation ------------------------------------------------------------------------------


def serial_norm(serial: str) -> str:
    """EQ-1 / EC-5: upper-case, spaces / '-' / '/' removed."""
    return re.sub(r"[\s\-/]", "", serial).upper()


def manufacturer_norm(m: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", m.upper())


def tag_norm(tag: str) -> str:
    return tag.strip().upper()


# ---- roles ---------------------------------------------------------------------------------------


def roles_on(p: Principal, project_id: uuid.UUID | None) -> set[Role]:
    if p.is_manager:
        return {Role.hse_manager}
    scope = p.projects.get(project_id) if project_id else None
    return scope.roles if scope else set()


def is_hse(p: Principal, project_id: uuid.UUID | None = None) -> bool:
    """P4-4: HSE Manager / HSE Officer (on the project; anywhere when project_id is None)."""
    if p.is_manager:
        return True
    if project_id is None:
        return any(Role.hse_officer in s.roles for s in p.projects.values())
    return Role.hse_officer in roles_on(p, project_id)


def contractor_only(p: Principal, project_id: uuid.UUID | None) -> bool:
    roles = roles_on(p, project_id)
    return bool(roles) and roles <= CONTRACTOR_ROLES


def site_engineer_only(p: Principal, project_id: uuid.UUID) -> bool:
    """Row 106/109 restrictions: site engineers edit only scaffolds and configuration events
    (106) and record only arrival / arrival inspection (109)."""
    roles = roles_on(p, project_id)
    return Role.site_engineer in roles and not roles & {
        Role.hse_manager,
        Role.hse_officer,
        Role.contractor_hse_rep,
    }


def require(
    p: Principal,
    project_id: uuid.UUID,
    cap: Capability,
    engagement_id: uuid.UUID | None = None,
    site_ids: Iterable[uuid.UUID] | None = None,
    write: bool = True,
) -> Grant:
    """Capability on the project; with an engagement / sites, the grant must also cover them.
    Without either it only asks for the grant in any scope (C-scoped callers then check each
    record — the lines' deployments, the holder's deployment — themselves)."""
    if engagement_id is None and not site_ids:
        if write:
            p.ensure_writer()
        g = p.grant(project_id, cap)
        if g is None:
            if write:
                p.require(project_id, cap)
            raise forbidden_error()
        return g
    return acommon.require_cap(p, project_id, cap, site_ids, engagement_id, write)


def grant_contractors(db: Session, g: Grant | None) -> set[uuid.UUID] | None:
    """Contractor ids covered by an engagement-scoped grant (None = unrestricted)."""
    if g is None:
        return set()
    if g.engagement_ids is None:
        return None
    rows = db.scalars(
        select(ProjectEngagement.contractor_id).where(
            ProjectEngagement.id.in_(list(g.engagement_ids))
        )
    )
    return set(rows)


def visible_projects(p: Principal, cap: Capability) -> dict[uuid.UUID, Grant] | None:
    return p.project_grants(cap)


# ---- lookups -------------------------------------------------------------------------------------


def project(db: Session, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None:
        raise not_found("Project")
    return x


def project_code(db: Session, project_id: uuid.UUID) -> str:
    return project(db, project_id).code


def live_deployment(db: Session, equipment_id: uuid.UUID) -> EquipmentDeployment | None:
    return db.scalar(
        select(EquipmentDeployment)
        .where(
            EquipmentDeployment.equipment_id == equipment_id,
            EquipmentDeployment.status.in_(LIVE_DEPLOYMENT),
        )
        .order_by(EquipmentDeployment.created_at.desc())
        .limit(1)
    )


def deployment_on(
    db: Session, equipment_id: uuid.UUID, project_id: uuid.UUID
) -> EquipmentDeployment | None:
    return db.scalar(
        select(EquipmentDeployment)
        .where(
            EquipmentDeployment.equipment_id == equipment_id,
            EquipmentDeployment.project_id == project_id,
            EquipmentDeployment.status.in_(LIVE_DEPLOYMENT),
        )
        .order_by(EquipmentDeployment.created_at.desc())
        .limit(1)
    )


def latest_deployment_on(
    db: Session, equipment_id: uuid.UUID, project_id: uuid.UUID
) -> EquipmentDeployment | None:
    """Live deployment on the project, else the latest one (any status)."""
    return deployment_on(db, equipment_id, project_id) or db.scalar(
        select(EquipmentDeployment)
        .where(
            EquipmentDeployment.equipment_id == equipment_id,
            EquipmentDeployment.project_id == project_id,
        )
        .order_by(EquipmentDeployment.created_at.desc())
        .limit(1)
    )


def owner_code(db: Session, contractor_id: uuid.UUID | None) -> str | None:
    if contractor_id is None:
        return None
    c = db.get(Contractor, contractor_id)
    return c.short_code if c else None


# ---- refs ----------------------------------------------------------------------------------------


def tpi_accepted(t: Tpi) -> bool:
    return t.status == TpiStatus.approved


def tpi_ref(t: Tpi, p: Principal | None = None, project_id: uuid.UUID | None = None) -> TpiRef:
    hse = p is None or is_hse(p, project_id) or not contractor_only(p, project_id)
    return TpiRef(
        id=t.id,
        tpi_code=t.tpi_code,
        legal_name_en=t.legal_name_en,
        legal_name_ar=t.legal_name_ar,
        status=t.status if hse else None,
        accepted_for_use=tpi_accepted(t),
    )


def equipment_ref(db: Session, e: EquipmentItem) -> EquipmentRef:
    return EquipmentRef(
        id=e.id,
        equipment_no=e.equipment_no,
        category=e.category,
        subtype=e.subtype,
        manufacturer=e.manufacturer,
        model=e.model,
        serial_no=e.serial_no,
        owner_short_code=owner_code(db, e.owner_contractor_id),
        service_status=e.service_status,
    )


def deployment_ref(d: EquipmentDeployment) -> DeploymentRef:
    return DeploymentRef(id=d.id, deployment_no=d.deployment_no, project_id=d.project_id, tag=d.tag)


def scaffold_ref(s: Scaffold) -> ScaffoldRef:
    return ScaffoldRef(
        id=s.id,
        scaffold_no=s.scaffold_no,
        tag=s.tag,
        status=s.status,
        tag_status=s.tag_status,
        tag_valid_until=s.tag_valid_until,
    )


def defect_ref(d: EquipmentDefect) -> DefectRef:
    return DefectRef(
        id=d.id,
        defect_no=d.defect_no,
        category=d.category,
        status=d.status.value,
        due_date=d.due_date,
    )


def line_ref(db: Session, line: EquipmentCertLine) -> CertLineRef:
    c = db.get(EquipmentCertificate, line.certificate_id)
    assert c is not None  # noqa: S101
    t = db.get(Tpi, c.tpi_id)
    return CertLineRef(
        certificate_id=c.id,
        line_id=line.id,
        cert_no=c.cert_no,
        tpi_code=t.tpi_code if t else "",
        status=c.status,
        valid_until=line.valid_until,
    )


def limitation_reads(items: list[dict[str, Any]] | None) -> list[EquipmentLimitationRead]:
    out = []
    for x in items or []:
        code = LimitationCode(x["code"])
        en, ar = ref.LIM_TEXT[code]
        out.append(
            EquipmentLimitationRead(
                code=code,
                value=Decimal(str(x["value"])) if x.get("value") is not None else None,
                text=x.get("text"),
                label_en=en,
                label_ar=ar,
            )
        )
    return out


def plimitation_reads(items: list[dict[str, Any]] | None) -> list[PersonnelLimitationRead]:
    out = []
    for x in items or []:
        code = PersonnelLimitationCode(x["code"])
        en, ar = ref.LIMP_TEXT[code]
        out.append(PersonnelLimitationRead(code=code, text=x.get("text"), label_en=en, label_ar=ar))
    return out


# ---- errors / warnings ---------------------------------------------------------------------------


def err(
    status: int,
    code: ErrorCode,
    en: str,
    ar: str,
    meta: dict[str, Any] | None = None,
) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta)


def warn(code: str, en: str, ar: str, field: str | None = None) -> ApiWarning:
    return ApiWarning(code=code, message=en, message_ar=ar, field=field)


def sod() -> ApiError:
    return err(
        422,
        ErrorCode.SOD_CONFLICT,
        "Segregation of duties: the same person cannot do both steps.",
        "فصل المهام: لا يجوز للشخص نفسه تنفيذ الخطوتين.",
    )


def outside_scope() -> ApiError:
    return forbidden_error("This record is outside your scope.")


def days_left(d: date | None) -> int | None:
    return None if d is None else (d - today()).days


# ---- audit ---------------------------------------------------------------------------------------

UNKNOWN_USER = UserRef(id=uuid.UUID(int=0), full_name_en="—")

_SKIP = frozenset({"created_at", "updated_at", "created_by_user_id", "updated_by_user_id"})


def snap(obj: Any, exclude: Iterable[str] = ()) -> dict[str, Any]:
    """Column snapshot for audit before/after (rule 35). Never contains ID numbers: Phase 4
    tables hold none (P4-2)."""
    from app.services import audit  # noqa: PLC0415

    skip = _SKIP | set(exclude)
    out = {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in skip}
    data: dict[str, Any] = audit.jsonable(out)
    return data


def record(
    db: Session,
    p: Principal | None,
    action: Any,
    entity_type: Any,
    obj: Any,
    project_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    from app.services import audit  # noqa: PLC0415

    actor = p.actor(project_id) if p is not None else audit.SYSTEM
    a = after if after is not None else snap(obj)
    if before is not None:
        b, a = audit.diff(before, a)
        if not a and not details:
            return
    else:
        b = None
    audit.record(
        db,
        action,
        actor,
        entity_type=entity_type,
        entity_id=obj.id,
        project_id=project_id,
        before=b,
        after=a,
        details=details,
    )


def stamp(obj: Any, p: Principal | None, create: bool = False) -> None:
    uid = p.user.id if p is not None else None
    if create:
        obj.created_by_user_id = uid
    obj.updated_by_user_id = uid
