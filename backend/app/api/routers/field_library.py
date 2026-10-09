"""Field assurance libraries and settings (spec 6d-field-assurance §3.1, §3.2, §3.10, §3.14, §4.1,
TPL-1…TPL-6, TBT-1, TBT-2): org-wide versioned checklist templates and toolbox topics, the reference
lists and the project settings with the two register switches."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.field_enums import TemplateKind, TopicCategory, VersionStatus
from app.core.hse_enums import InspectionType
from app.schemas.field import (
    FieldReference,
    FieldSettingsRead,
    FieldSettingsUpdate,
    TemplateCreate,
    TemplatePage,
    TemplateRead,
    TemplateUpdate,
    TopicCreate,
    TopicPage,
    TopicRead,
    TopicUpdate,
    VersionTransition,
)
from app.services.field import config, library

router = APIRouter(tags=["field-library"])


@router.get(
    "/field-reference",
    response_model=FieldReference,
    summary="6d reference lists IT, FS, AT, AF, AG, categories (§3.15)",
    responses=error_responses(401),
)
def get_field_reference(user: CurrentUser) -> FieldReference:
    return config.reference()


@router.get(
    "/projects/{project_id}/field-settings",
    response_model=FieldSettingsRead,
    summary="6d project settings and register switches (§3.14)",
    responses=error_responses(401, 403, 404),
)
def get_field_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FieldSettingsRead:
    return config.read_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/field-settings",
    response_model=FieldSettingsRead,
    summary="Edit 6d settings (193; tighten only, SETTING_LOOSENING)",
    responses=error_responses(401, 403, 404, 422),
)
def update_field_settings(
    project_id: uuid.UUID, body: FieldSettingsUpdate, user: CurrentUser, db: DB
) -> FieldSettingsRead:
    return config.update_settings(db, user, project_id, body)


# ---- templates -----------------------------------------------------------------------------------


@router.get(
    "/checklist-templates",
    response_model=TemplatePage,
    summary="Checklist template library (191); `project_id` limits to templates offered there",
    responses=error_responses(401, 403),
)
def list_checklist_templates(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    kind: TemplateKind | None = None,
    inspection_type: InspectionType | None = None,
    status_: Annotated[list[VersionStatus] | None, Query(alias="status")] = None,
    template_code: str | None = None,
    project_id: uuid.UUID | None = None,
) -> TemplatePage:
    return library.list_templates(
        db, user, kind, inspection_type, status_, template_code, project_id, pg.page, pg.page_size
    )


@router.post(
    "/checklist-templates",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="New template code or next version (192; Draft)",
    responses=error_responses(401, 403, 409, 422),
)
def create_checklist_template(body: TemplateCreate, user: CurrentUser, db: DB) -> TemplateRead:
    return library.create_template(db, user, body)


@router.get(
    "/checklist-templates/{template_id}",
    response_model=TemplateRead,
    summary="One template version with its items",
    responses=error_responses(401, 403, 404),
)
def get_checklist_template(template_id: uuid.UUID, user: CurrentUser, db: DB) -> TemplateRead:
    return library.read_template(db, user, template_id)


@router.patch(
    "/checklist-templates/{template_id}",
    response_model=TemplateRead,
    summary="Edit a Draft (192; Published → 409 TEMPLATE_IMMUTABLE)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_checklist_template(
    template_id: uuid.UUID, body: TemplateUpdate, user: CurrentUser, db: DB
) -> TemplateRead:
    return library.update_template(db, user, template_id, body)


@router.delete(
    "/checklist-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a never-published Draft (author)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_checklist_template(template_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    library.delete_template(db, user, template_id)


@router.post(
    "/checklist-templates/{template_id}/new-version",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Copy this version into the next Draft version (192; TPL-3)",
    responses=error_responses(401, 403, 404, 409),
)
def new_checklist_template_version(
    template_id: uuid.UUID, user: CurrentUser, db: DB
) -> TemplateRead:
    return library.new_version(db, user, template_id)


@router.post(
    "/checklist-templates/{template_id}/transitions",
    response_model=TemplateRead,
    summary="Publish (TPL-2, supersedes) or retire (TPL-5) a version (193)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_checklist_template(
    template_id: uuid.UUID, body: VersionTransition, user: CurrentUser, db: DB
) -> TemplateRead:
    return library.transition_template(db, user, template_id, body)


# ---- topics --------------------------------------------------------------------------------------


@router.get(
    "/toolbox-topics",
    response_model=TopicPage,
    summary="Toolbox topic library (191)",
    responses=error_responses(401, 403),
)
def list_toolbox_topics(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    category: TopicCategory | None = None,
    status_: Annotated[list[VersionStatus] | None, Query(alias="status")] = None,
    topic_code: str | None = None,
) -> TopicPage:
    return library.list_topics(db, user, category, status_, topic_code, pg.page, pg.page_size)


@router.post(
    "/toolbox-topics",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
    summary="New topic code or next version (192; Draft)",
    responses=error_responses(401, 403, 409, 422),
)
def create_toolbox_topic(body: TopicCreate, user: CurrentUser, db: DB) -> TopicRead:
    return library.create_topic(db, user, body)


@router.get(
    "/toolbox-topics/{topic_id}",
    response_model=TopicRead,
    summary="One topic version",
    responses=error_responses(401, 403, 404),
)
def get_toolbox_topic(topic_id: uuid.UUID, user: CurrentUser, db: DB) -> TopicRead:
    return library.read_topic(db, user, topic_id)


@router.patch(
    "/toolbox-topics/{topic_id}",
    response_model=TopicRead,
    summary="Edit a Draft topic (192)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_toolbox_topic(
    topic_id: uuid.UUID, body: TopicUpdate, user: CurrentUser, db: DB
) -> TopicRead:
    return library.update_topic(db, user, topic_id, body)


@router.delete(
    "/toolbox-topics/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a never-published Draft topic (author)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_toolbox_topic(topic_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    library.delete_topic(db, user, topic_id)


@router.post(
    "/toolbox-topics/{topic_id}/new-version",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
    summary="Copy this version into the next Draft version (192)",
    responses=error_responses(401, 403, 404, 409),
)
def new_toolbox_topic_version(topic_id: uuid.UUID, user: CurrentUser, db: DB) -> TopicRead:
    return library.new_topic_version(db, user, topic_id)


@router.post(
    "/toolbox-topics/{topic_id}/transitions",
    response_model=TopicRead,
    summary="Publish (TBT-1) or retire a topic version (193)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_toolbox_topic(
    topic_id: uuid.UUID, body: VersionTransition, user: CurrentUser, db: DB
) -> TopicRead:
    return library.transition_topic(db, user, topic_id, body)
