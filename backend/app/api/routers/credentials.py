"""Common credential lifecycle for induction records, airport passes, ADPs, AVPs and access
cards (spec 2-access-permits §3.18, §4.5, §4.9, §5.9). `{credential_id}` is the record id; for
`access_card` it is the deployment id."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import CredentialKind
from app.core.errors import error_responses, not_implemented
from app.schemas.credentials import (
    AuthorityNotifiedRequest,
    ConfirmSuspensionRequest,
    CredentialEventPage,
    CredentialState,
    LossReportRequest,
    ReinstateRequest,
    ReturnRequest,
    RevokeRequest,
    SuspendRequest,
)

router = APIRouter(prefix="/credentials", tags=["credentials"])

KindPath = Annotated[
    CredentialKind,
    Path(description="induction | airport_pass | adp | avp | access_card (wap/worker → 404)."),
]
ERRORS = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/{kind}/{credential_id}",
    response_model=CredentialState,
    summary="Validity, custody, open suspensions and recent events of a credential",
    responses=error_responses(401, 403, 404),
)
def get_credential_state(
    kind: KindPath, credential_id: uuid.UUID, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.get(
    "/{kind}/{credential_id}/events",
    response_model=CredentialEventPage,
    summary="Full §3.18 status-event log of a credential",
    responses=error_responses(401, 403, 404, 422),
)
def list_credential_events(
    kind: KindPath, credential_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> CredentialEventPage:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/suspend",
    response_model=CredentialState,
    summary="Suspend: raise (capability 57, ≤ raised_suspension_max_hours) or confirmed (58)",
    responses=ERRORS,
)
def suspend_credential(
    kind: KindPath, credential_id: uuid.UUID, body: SuspendRequest, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/confirm-suspension",
    response_model=CredentialState,
    summary="Confirm a raised suspension (capability 58; inductions 52)",
    responses=ERRORS,
)
def confirm_credential_suspension(
    kind: KindPath,
    credential_id: uuid.UUID,
    body: ConfirmSuspensionRequest,
    user: CurrentUser,
    db: DB,
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/reinstate",
    response_model=CredentialState,
    summary="Lift manual suspensions (capability 58; DP-8 after suspension_end)",
    responses=ERRORS,
)
def reinstate_credential(
    kind: KindPath, credential_id: uuid.UUID, body: ReinstateRequest, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/revoke",
    response_model=CredentialState,
    summary="Revoke (terminal; capability 58, inductions 52; custody → return due)",
    responses=ERRORS,
)
def revoke_credential(
    kind: KindPath, credential_id: uuid.UUID, body: RevokeRequest, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/return",
    response_model=CredentialState,
    summary="Record the physical return (capability 59; LC-11)",
    responses=ERRORS,
)
def return_credential(
    kind: KindPath, credential_id: uuid.UUID, body: ReturnRequest, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/loss",
    response_model=CredentialState,
    summary="Report loss/theft (capability 59; rotates/revokes the token, LC-12)",
    responses=ERRORS,
)
def report_credential_loss(
    kind: KindPath, credential_id: uuid.UUID, body: LossReportRequest, user: CurrentUser, db: DB
) -> CredentialState:
    raise not_implemented()


@router.post(
    "/{kind}/{credential_id}/authority-notified",
    response_model=CredentialState,
    summary="Record when the pass office was told about a loss (capability 59)",
    responses=ERRORS,
)
def record_authority_notified(
    kind: KindPath,
    credential_id: uuid.UUID,
    body: AuthorityNotifiedRequest,
    user: CurrentUser,
    db: DB,
) -> CredentialState:
    raise not_implemented()
