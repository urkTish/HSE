"""Q1 HTTP routes: handover dossiers — scope, as-built list, compile, submit, accept / return,
revisions and downloads (spec 8-quality §B.7)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.q1 import QDossierStatus
from app.schemas.quality.q1 import (
    QAsbuiltCreate,
    QAsbuiltUpdate,
    QDossierCreate,
    QDossierDecide,
    QDossierPage,
    QDossierRead,
    QDossierUpdate,
)
from app.services.quality.q1 import dossier

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


def _r(db: Any, user: Any, d: Any) -> dict[str, Any]:
    return dossier.read(db, user, d)


@router.get(
    "/projects/{project_id}/quality/dossiers",
    response_model=QDossierPage,
    summary="Handover dossiers",
    responses=E,
)
def q1_list_dossiers(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QDossierStatus] | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return dossier.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    "/projects/{project_id}/quality/dossiers",
    response_model=QDossierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dossier (253): scope by zones and / or systems, sections",
    responses=E,
)
def q1_create_dossier(
    project_id: uuid.UUID, body: QDossierCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, dossier.create(db, user, project_id, body.model_dump(mode="python")))


@router.get(
    "/quality/dossiers/{dossier_id}",
    response_model=QDossierRead,
    summary="One dossier with its blockers",
    responses=E,
)
def q1_get_dossier(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, dossier.get_dossier(db, user, dossier_id))


@router.patch(
    "/quality/dossiers/{dossier_id}",
    response_model=QDossierRead,
    summary="Edit scope, title or sections",
    responses=E,
)
def q1_update_dossier(
    dossier_id: uuid.UUID, body: QDossierUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(
        db,
        user,
        dossier.update(db, user, dossier_id, body.model_dump(exclude_unset=True, mode="python")),
    )


@router.post(
    "/quality/dossiers/{dossier_id}/asbuilt",
    response_model=QDossierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an as-built drawing",
    responses=E,
)
def q1_add_asbuilt(
    dossier_id: uuid.UUID, body: QAsbuiltCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, dossier.add_asbuilt(db, user, dossier_id, body.model_dump(mode="python")))


@router.patch(
    "/quality/asbuilt/{item_id}",
    response_model=QDossierRead,
    summary="Edit, approve or delete an as-built drawing",
    responses=E,
)
def q1_update_asbuilt(
    item_id: uuid.UUID, body: QAsbuiltUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(
        db,
        user,
        dossier.update_asbuilt(
            db, user, item_id, body.model_dump(exclude_unset=True, mode="python")
        ),
    )


@router.post(
    "/quality/dossiers/{dossier_id}/compile",
    response_model=QDossierRead,
    summary="Compile: snapshot, index PDFs EN / AR, ZIP (accepted → 409 DOSSIER_IMMUTABLE)",
    responses=E,
)
def q1_compile_dossier(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, dossier.compile_(db, user, dossier_id))


@router.post(
    "/quality/dossiers/{dossier_id}/submit",
    response_model=QDossierRead,
    summary="Submit (blockers → 422 DOSSIER_BLOCKED)",
    responses=E,
)
def q1_submit_dossier(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, dossier.submit(db, user, dossier_id))


@router.post(
    "/quality/dossiers/{dossier_id}/decide",
    response_model=QDossierRead,
    summary="Accept or return (254 + RPM dossier.accept)",
    responses=E,
)
def q1_decide_dossier(
    dossier_id: uuid.UUID, body: QDossierDecide, user: CurrentUser, db: DB
) -> dict[str, Any]:
    paper = body.paper.model_dump(mode="python") if body.paper else None
    return _r(db, user, dossier.decide(db, user, dossier_id, body.decision, body.comment, paper))


@router.post(
    "/quality/dossiers/{dossier_id}/reopen",
    response_model=QDossierRead,
    summary="Returned → Draft",
    responses=E,
)
def q1_reopen_dossier(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, dossier.reopen(db, user, dossier_id))


@router.post(
    "/quality/dossiers/{dossier_id}/revisions",
    response_model=QDossierRead,
    status_code=status.HTTP_201_CREATED,
    summary="New revision after acceptance",
    responses=E,
)
def q1_new_dossier_revision(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, dossier.new_revision(db, user, dossier_id))


_PDF: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
}
_ZIP: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}
}


@router.get(
    "/quality/dossiers/{dossier_id}/index",
    summary="Index PDF EN / AR (Viewer / Client once accepted, Q-DOS-05)",
    responses={**E, **_PDF},
    response_class=Response,
)
def q1_dossier_index(
    dossier_id: uuid.UUID, user: CurrentUser, db: DB, lang: Literal["en", "ar"] = "en"
) -> Response:
    content, ctype, name = dossier.index_file(db, user, dossier_id, lang)
    return Response(
        content=content,
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/quality/dossiers/{dossier_id}/package",
    summary="ZIP package (253 or 254, Q-DOS-05)",
    responses={**E, **_ZIP},
    response_class=Response,
)
def q1_dossier_package(dossier_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    content, ctype, name = dossier.package_file(db, user, dossier_id)
    return Response(
        content=content,
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
