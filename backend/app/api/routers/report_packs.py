"""Report packs: monthly client HSE report (MCR), contractor scorecard packs (SCP), contractor
performance summary (CPS), OSHA 300-style log (OSHA300) and the heat season report (HEAT), with
issue / freeze / re-issue, files, distribution lists and the delivery log (spec
6g-scorecard-reports §3.6, §3.7, §4.4, RP, DL)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.scorecard_enums import RpFileKind, RpStatus, RpType
from app.schemas.scorecard import (
    RpDeliveryPage,
    RpDistributionList,
    RpDistributionUpdate,
    RpFileUrl,
    RpPackCreate,
    RpPackDetail,
    RpPackPage,
    RpPackTransition,
    RpPackUpdate,
    RpReissueRequest,
)
from app.services.scorecard import distribution, packs

router = APIRouter(tags=["report-packs"])


@router.get(
    "/projects/{project_id}/report-packs",
    response_model=RpPackPage,
    summary="Report-pack register with revisions (229 or 231)",
    description="Reps see their own SCPs only; Viewer / Client sees MCR, de-identified OSHA300 "
    "and HEAT packs once Issued.",
    responses=error_responses(401, 403, 404),
)
def list_report_packs(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    report_type: RpType | None = None,
    status_: Annotated[RpStatus | None, Query(alias="status")] = None,
) -> RpPackPage:
    return packs.list_packs(db, user, project_id, report_type, status_, pg.page, pg.page_size)


@router.post(
    "/report-packs",
    response_model=RpPackDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a Draft pack (229; CPS 226)",
    description="Doc numbers `<type>-<project>[-<engagement>]-<yyyy>[-<mm>]`. 409 when a Draft "
    "or In Review revision exists. OSHA300 `with_names` needs capability 43 and a purpose.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_report_pack(body: RpPackCreate, user: CurrentUser, db: DB) -> RpPackDetail:
    return packs.create(db, user, body)


@router.get(
    "/report-packs/{pack_id}",
    response_model=RpPackDetail,
    summary="One pack revision with its frozen snapshot",
    responses=error_responses(401, 403, 404),
)
def get_report_pack(pack_id: uuid.UUID, user: CurrentUser, db: DB) -> RpPackDetail:
    return packs.read(db, user, pack_id)


@router.patch(
    "/report-packs/{pack_id}",
    response_model=RpPackDetail,
    summary="Edit a Draft / In Review pack (229; 409 PACK_ISSUED_IMMUTABLE once Issued)",
    responses=error_responses(401, 403, 404, 409),
)
def update_report_pack(
    pack_id: uuid.UUID, body: RpPackUpdate, user: CurrentUser, db: DB
) -> RpPackDetail:
    return packs.update(db, user, pack_id, body)


@router.post(
    "/report-packs/{pack_id}/transitions",
    response_model=RpPackDetail,
    summary="Regenerate, submit for review, return, review (229) or issue (230) a pack (§4.4)",
    description="Issue: 422 SOURCE_REPORT_NOT_PUBLISHED, SELF_REVIEW, SCORECARDS_NOT_FINAL "
    "(unless `scorecards_provisional` with a reason ≥ 20 chars), PACK_TOO_LARGE_FOR_EMAIL. "
    "Renders the EN / AR PDFs and the XLSX, freezes the snapshot and distributes (DL-4).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_report_pack(
    pack_id: uuid.UUID, body: RpPackTransition, user: CurrentUser, db: DB
) -> RpPackDetail:
    return packs.transition(db, user, pack_id, body)


@router.post(
    "/report-packs/{pack_id}/reissue",
    response_model=RpPackDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Start revision n + 1 of an Issued pack as a Draft (230; RP-6, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_report_pack(
    pack_id: uuid.UUID, body: RpReissueRequest, user: CurrentUser, db: DB
) -> RpPackDetail:
    return packs.reissue(db, user, pack_id, body.reason)


@router.get(
    "/report-packs/{pack_id}/files/{kind}/url",
    response_model=RpFileUrl,
    summary="Signed URL (≤ 5 min) of a rendered pack file (231)",
    responses=error_responses(401, 403, 404),
)
def get_report_pack_file_url(
    pack_id: uuid.UUID, kind: RpFileKind, user: CurrentUser, db: DB
) -> RpFileUrl:
    return packs.file_url(db, user, pack_id, kind)


@router.get(
    "/report-packs/{pack_id}/deliveries",
    response_model=RpDeliveryPage,
    summary="Delivery log of a pack (231)",
    responses=error_responses(401, 403, 404),
)
def list_report_pack_deliveries(
    pack_id: uuid.UUID, user: CurrentUser, db: DB, pg: PageParams
) -> RpDeliveryPage:
    return distribution.deliveries(db, user, pack_id, pg.page, pg.page_size)


@router.get(
    "/projects/{project_id}/distribution-lists/{report_type}",
    response_model=RpDistributionList,
    summary="Distribution list of a project and report type (229 / 230)",
    responses=error_responses(401, 403, 404),
)
def get_distribution_list(
    project_id: uuid.UUID, report_type: RpType, user: CurrentUser, db: DB
) -> RpDistributionList:
    return distribution.get_list(db, user, project_id, report_type)


@router.put(
    "/projects/{project_id}/distribution-lists/{report_type}",
    response_model=RpDistributionList,
    summary="Replace a distribution list (230; DL-1…DL-3)",
    description="422 RECIPIENT_SCOPE (user without the view right, reps and receivers on MCR / "
    "OSHA300 / CPS), EXTERNAL_NOT_ALLOWED (type, setting or domain).",
    responses=error_responses(401, 403, 404, 422),
)
def put_distribution_list(
    project_id: uuid.UUID,
    report_type: RpType,
    body: RpDistributionUpdate,
    user: CurrentUser,
    db: DB,
) -> RpDistributionList:
    return distribution.put_list(db, user, project_id, report_type, body)
