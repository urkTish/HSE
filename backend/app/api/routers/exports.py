"""List exports (spec §5.8 rule 49, capability 18)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DB, CurrentUser
from app.core.enums import ExportDataset, ExportFormat
from app.core.errors import error_responses
from app.core.hse_enums import ExportPurpose
from app.services import exports as svc
from app.services import hse_exports
from app.services.access import exports as access_exports
from app.services.ptw import exports as ptw_exports

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

PHASE2_DATASETS = access_exports.DATASETS

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
    "exported. Phase 2 access registers (capability 78) mask IDs; `include_identity=true` adds "
    "full ID numbers with capability 79 and a purpose (pass_office, authority_request, legal, "
    "other + purpose_text) recorded in the audit entry (P2-10); photos and ID copies are never "
    "exported; gate_log needs capability 76. Phase 3 PTW registers need capability 104; person "
    "names only with capability 46; signatures, gas readings and medical data are never exported.",
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
        bool,
        Query(
            description="incidents: add injured-person identity columns; Phase 2 registers: "
            "full ID numbers (capability 79)."
        ),
    ] = False,
    purpose: Annotated[
        ExportPurpose | None, Query(description="Required with include_identity (P1-6).")
    ] = None,
    purpose_text: Annotated[
        str | None, Query(max_length=200, description="Required when purpose = other.")
    ] = None,
) -> Response:
    if dataset in PHASE2_DATASETS:
        content, media_type, filename = access_exports.export(
            db,
            user,
            dataset,
            format_,
            project_id,
            status_,
            q,
            include_identity,
            purpose,
            purpose_text,
        )
    elif dataset in PHASE1_DATASETS:
        content, media_type, filename = hse_exports.export(
            db,
            user,
            dataset,
            format_,
            project_id,
            status_,
            q,
            include_identity,
            purpose,
            purpose_text,
        )
    elif dataset in ptw_exports.DATASETS:
        content, media_type, filename = ptw_exports.export(
            db, user, dataset, format_, project_id, status_, q
        )
    else:
        content, media_type, filename = svc.export(
            db, user, dataset, format_, project_id, status_, q
        )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
