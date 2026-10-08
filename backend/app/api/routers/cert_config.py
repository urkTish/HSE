"""Phase 4 project settings, EQC / PCT catalogue, hook policy (warn → transition → block) and
the readiness report (spec 4-third-party-cert §3.14, §3.16, §3.17, §4.8, §6.5, §6.8,
HK4-1…HK4-7, BD-3, TP-5)."""

import uuid
from datetime import date

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.access_enums import HookKind
from app.core.errors import error_responses
from app.schemas.cert_config import (
    CertCatalogue,
    CertSettingsRead,
    CertSettingsUpdate,
    CertSettingsUpdateResult,
    CertTypeCreate,
    CertTypeInfo,
    CertTypeUpdate,
    HookDeferralRequest,
    HookEnableRequest,
    HookPolicyRead,
    HookReadinessReport,
    HookSwitchRequest,
)
from app.services.cert import policy, readiness
from app.services.cert import settings as cset

router = APIRouter(tags=["cert-config"])


@router.get(
    "/projects/{project_id}/cert-settings",
    response_model=CertSettingsRead,
    summary="Phase 4 project settings (§3.17)",
    responses=error_responses(401, 403, 404),
)
def get_cert_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> CertSettingsRead:
    return cset.read(db, user, project_id)


@router.patch(
    "/projects/{project_id}/cert-settings",
    response_model=CertSettingsUpdateResult,
    summary="Edit Phase 4 settings (capability 124; tighten-only ranges; audited)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_cert_settings(
    project_id: uuid.UUID, body: CertSettingsUpdate, user: CurrentUser, db: DB
) -> CertSettingsUpdateResult:
    return cset.update(db, user, project_id, body)


@router.get(
    "/cert-catalogue",
    response_model=CertCatalogue,
    summary="EQC and PCT catalogues with the project's intervals / caps and hook codes",
    responses=error_responses(401, 403, 404, 422),
)
def get_cert_catalogue(
    user: CurrentUser, db: DB, project_id: uuid.UUID | None = None
) -> CertCatalogue:
    return cset.catalogue(db, user, project_id)


@router.post(
    "/cert-types",
    response_model=CertTypeInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Add a personnel certificate type (capability 124; BD-3 catalogue boundary)",
    responses=error_responses(401, 403, 409, 422),
)
def create_cert_type(body: CertTypeCreate, user: CurrentUser, db: DB) -> CertTypeInfo:
    return cset.create_type(db, user, body)


@router.patch(
    "/cert-types/{code}",
    response_model=CertTypeInfo,
    summary="Edit a certificate type's labels (capability 124; code immutable)",
    responses=error_responses(401, 403, 404, 422),
)
def update_cert_type(code: str, body: CertTypeUpdate, user: CurrentUser, db: DB) -> CertTypeInfo:
    return cset.update_type(db, user, code, body)


@router.get(
    "/projects/{project_id}/hook-policy",
    response_model=HookPolicyRead,
    summary="Hook policy state per kind: stage, block dates, per-code policy (§3.14)",
    responses=error_responses(401, 403, 404),
)
def get_hook_policy(project_id: uuid.UUID, user: CurrentUser, db: DB) -> HookPolicyRead:
    return policy.read(db, user, project_id)


@router.post(
    "/projects/{project_id}/hook-policy/enable",
    response_model=HookPolicyRead,
    summary="Enable Phase 4 providers on the project → transition stage (HK4-1; 124)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def enable_hook_policy(
    project_id: uuid.UUID, body: HookEnableRequest, user: CurrentUser, db: DB
) -> HookPolicyRead:
    return policy.enable(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/hook-policy/{kind}/switch",
    response_model=HookPolicyRead,
    summary="Early switch of codes to block (HK4-5; 124); never back to warn",
    responses=error_responses(401, 403, 404, 409, 422),
)
def switch_hook_policy(
    project_id: uuid.UUID, kind: HookKind, body: HookSwitchRequest, user: CurrentUser, db: DB
) -> HookPolicyRead:
    return policy.switch(db, user, project_id, kind, body)


@router.post(
    "/projects/{project_id}/hook-policy/{kind}/deferral",
    response_model=HookPolicyRead,
    summary="Defer the general block date once, ≤ 30 days (HK4-6; 124)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def defer_hook_policy(
    project_id: uuid.UUID, kind: HookKind, body: HookDeferralRequest, user: CurrentUser, db: DB
) -> HookPolicyRead:
    return policy.defer(db, user, project_id, kind, body)


@router.get(
    "/projects/{project_id}/hook-readiness",
    response_model=HookReadinessReport,
    summary="Readiness report per code before the block date (HK4-7, §6.8; capability 122)",
    responses=error_responses(401, 403, 404, 422),
)
def get_hook_readiness(
    project_id: uuid.UUID,
    kind: HookKind,
    user: CurrentUser,
    db: DB,
    on_date: date | None = None,
) -> HookReadinessReport:
    return readiness.report(db, user, project_id, kind, on_date)
