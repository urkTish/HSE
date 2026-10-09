"""Environmental reference, settings, aspects, providers, permits and licences (spec
6e-environmental §3.1–§3.3, §3.16, §3.17, §4.1, §4.2, ASP, PRM, PRV)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.env_enums import AspectStatus, EnvPermitStatus, EnvPermitType, ProviderKind
from app.core.errors import error_responses
from app.schemas.env import (
    AspectCreate,
    AspectPage,
    AspectRead,
    AspectTransition,
    AspectUpdate,
    EnvPermitCreate,
    EnvPermitRead,
    EnvPermitUpdate,
    EnvProviderCreate,
    EnvProviderPage,
    EnvProviderRead,
    EnvProviderUpdate,
    EnvReference,
    EnvSettingsRead,
    EnvSettingsUpdate,
    PermitPage,
    PermitTransition,
    ProviderTransition,
)
from app.services.env import config, register

router = APIRouter(tags=["env-config"])


@router.get(
    "/env-reference",
    response_model=EnvReference,
    summary="6e reference lists with EN/AR labels and the DL limit library (§3.17)",
    responses=error_responses(401),
)
def get_env_reference(user: CurrentUser, db: DB) -> EnvReference:
    return config.reference(db, user)


@router.get(
    "/projects/{project_id}/env-settings",
    response_model=EnvSettingsRead,
    summary="6e project settings (§3.16; capability 202)",
    responses=error_responses(401, 403, 404),
)
def get_env_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvSettingsRead:
    return config.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/env-settings",
    response_model=EnvSettingsRead,
    summary="Edit 6e settings (213, HSE Manager; tighten only → 422 SETTING_LOOSENING)",
    responses=error_responses(401, 403, 404, 422),
)
def update_env_settings(
    project_id: uuid.UUID, body: EnvSettingsUpdate, user: CurrentUser, db: DB
) -> EnvSettingsRead:
    return config.update_settings(db, user, project_id, body)


# ---- aspects -------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/env-aspects",
    response_model=AspectPage,
    summary="Aspects and impacts register (202)",
    responses=error_responses(401, 403, 404),
)
def list_env_aspects(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[AspectStatus] | None, Query(alias="status")] = None,
    significant: bool | None = None,
    site_id: uuid.UUID | None = None,
) -> AspectPage:
    return register.list_aspects(
        db, user, project_id, status_, significant, site_id, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/env-aspects",
    response_model=AspectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft aspect (203)",
    responses=error_responses(401, 403, 404, 422),
)
def create_env_aspect(
    project_id: uuid.UUID, body: AspectCreate, user: CurrentUser, db: DB
) -> AspectRead:
    return register.create_aspect(db, user, project_id, body)


@router.get(
    "/env-aspects/{aspect_id}",
    response_model=AspectRead,
    summary="One aspect",
    responses=error_responses(401, 403, 404),
)
def get_env_aspect(aspect_id: uuid.UUID, user: CurrentUser, db: DB) -> AspectRead:
    return register.read_aspect(db, user, aspect_id)


@router.patch(
    "/env-aspects/{aspect_id}",
    response_model=AspectRead,
    summary="Edit an aspect (203)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_env_aspect(
    aspect_id: uuid.UUID, body: AspectUpdate, user: CurrentUser, db: DB
) -> AspectRead:
    return register.update_aspect(db, user, aspect_id, body)


@router.post(
    "/env-aspects/{aspect_id}/transitions",
    response_model=AspectRead,
    summary="Activate (ASP-2), archive or review an aspect (203)",
    description="422 ASPECT_CONTROL_REQUIRED / CONTROL_LEVEL_TOO_LOW on activate.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_env_aspect(
    aspect_id: uuid.UUID, body: AspectTransition, user: CurrentUser, db: DB
) -> AspectRead:
    return register.transition_aspect(db, user, aspect_id, body)


# ---- providers -----------------------------------------------------------------------------------


@router.get(
    "/env-providers",
    response_model=EnvProviderPage,
    summary="Environmental service providers (org-wide; any 202 holder)",
    responses=error_responses(401, 403),
)
def list_env_providers(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    kind: ProviderKind | None = None,
) -> EnvProviderPage:
    return register.list_providers(db, user, kind, pg.page, pg.page_size)


@router.post(
    "/env-providers",
    response_model=EnvProviderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a provider (204)",
    responses=error_responses(401, 403, 409, 422),
)
def create_env_provider(body: EnvProviderCreate, user: CurrentUser, db: DB) -> EnvProviderRead:
    return register.create_provider(db, user, body)


@router.get(
    "/env-providers/{provider_id}",
    response_model=EnvProviderRead,
    summary="One provider with its licences",
    responses=error_responses(401, 403, 404),
)
def get_env_provider(provider_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvProviderRead:
    return register.read_provider(db, user, provider_id)


@router.patch(
    "/env-providers/{provider_id}",
    response_model=EnvProviderRead,
    summary="Edit a provider (204)",
    responses=error_responses(401, 403, 404, 422),
)
def update_env_provider(
    provider_id: uuid.UUID, body: EnvProviderUpdate, user: CurrentUser, db: DB
) -> EnvProviderRead:
    return register.update_provider(db, user, provider_id, body)


@router.post(
    "/env-providers/{provider_id}/transitions",
    response_model=EnvProviderRead,
    summary="Approve, suspend or blacklist a provider (213, HSE Manager; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_env_provider(
    provider_id: uuid.UUID, body: ProviderTransition, user: CurrentUser, db: DB
) -> EnvProviderRead:
    return register.transition_provider(db, user, provider_id, body)


@router.post(
    "/env-providers/{provider_id}/licences",
    response_model=EnvPermitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a provider licence (204; mwan_licence, facility_authorisation, …)",
    responses=error_responses(401, 403, 404, 422),
)
def create_provider_licence(
    provider_id: uuid.UUID, body: EnvPermitCreate, user: CurrentUser, db: DB
) -> EnvPermitRead:
    return register.create_permit(db, user, None, provider_id, body)


# ---- project permits -----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/env-permits",
    response_model=PermitPage,
    summary="Project permits and approvals register (202; §4.2 status at today)",
    responses=error_responses(401, 403, 404),
)
def list_env_permits(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[EnvPermitStatus] | None, Query(alias="status")] = None,
    permit_type: EnvPermitType | None = None,
    expiring_within_days: int | None = Query(default=None, ge=0, le=365),
) -> PermitPage:
    return register.list_permits(
        db, user, project_id, status_, permit_type, expiring_within_days, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/env-permits",
    response_model=EnvPermitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a project permit or renewal (204; PRM-1)",
    responses=error_responses(401, 403, 404, 422),
)
def create_env_permit(
    project_id: uuid.UUID, body: EnvPermitCreate, user: CurrentUser, db: DB
) -> EnvPermitRead:
    return register.create_permit(db, user, project_id, None, body)


@router.get(
    "/env-permits/{permit_id}",
    response_model=EnvPermitRead,
    summary="One permit or licence",
    responses=error_responses(401, 403, 404),
)
def get_env_permit(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvPermitRead:
    return register.read_permit(db, user, permit_id)


@router.patch(
    "/env-permits/{permit_id}",
    response_model=EnvPermitRead,
    summary="Edit a permit or licence (204)",
    responses=error_responses(401, 403, 404, 422),
)
def update_env_permit(
    permit_id: uuid.UUID, body: EnvPermitUpdate, user: CurrentUser, db: DB
) -> EnvPermitRead:
    return register.update_permit(db, user, permit_id, body)


@router.post(
    "/env-permits/{permit_id}/transitions",
    response_model=EnvPermitRead,
    summary="Suspend, reinstate or cancel a permit or licence (204; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_env_permit(
    permit_id: uuid.UUID, body: PermitTransition, user: CurrentUser, db: DB
) -> EnvPermitRead:
    return register.transition_permit(db, user, permit_id, body)
