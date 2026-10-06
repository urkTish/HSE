"""List exports (spec §5.8 rule 49, capability 18)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DB, CurrentUser
from app.core.enums import ExportDataset, ExportFormat
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import ExportPurpose
from app.services import exports as svc

router = APIRouter(prefix="/exports", tags=["exports"])

PHASE1_DATASETS = frozenset(
    {
        ExportDataset.workforce_returns,
        ExportDataset.incidents,
        ExportDataset.observations,
        ExportDataset.inspections,
        ExportDataset.corrective_actions,
        ExportDataset.hse_meetings,
    }
)

_FILE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "The exported file (Content-Disposition: attachment).",
        "content": {
            "text/csv": {"schema": {"type": "string", "format": "binary"}},
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                "schema": {"type": "string", "format": "binary"}
            },
        },
    },
    **error_responses(401, 403, 404, 422),
}


@router.get(
    "/{dataset}",
    summary="Export a list as CSV or Excel",
    description="Contains only fields the caller may read (contact columns only with "
    "capability 9/12). `project_id` is required for sites, zones, engagements and every Phase 1 "
    "register. Writes an `export` audit entry with row count and filters. Incidents: identity "
    "columns only with `include_identity=true`, capability 43 and a `purpose` (422 "
    "EXPORT_PURPOSE_REQUIRED; recorded in the audit entry, P1-6); medical attachments are never "
    "exported.",
    response_class=Response,
    responses=_FILE_RESPONSES,
)
def export_dataset(
    dataset: ExportDataset,
    user: CurrentUser,
    db: DB,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.csv,
    project_id: uuid.UUID | None = None,
    status_: Annotated[str | None, Query(alias="status", max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_identity: Annotated[
        bool, Query(description="incidents only: add injured-person identity columns.")
    ] = False,
    purpose: Annotated[
        ExportPurpose | None, Query(description="Required with include_identity (P1-6).")
    ] = None,
    purpose_text: Annotated[
        str | None, Query(max_length=200, description="Required when purpose = other.")
    ] = None,
) -> Response:
    if dataset in PHASE1_DATASETS:
        raise not_implemented()
    content, media_type, filename = svc.export(db, user, dataset, format_, project_id, status_, q)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
