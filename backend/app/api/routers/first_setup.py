"""First-time setup screen API (D-306). Public; locked once the install has a user."""

from fastapi import APIRouter, Response, status

from app.api.deps import DB
from app.api.routers.auth import _login_response
from app.core.errors import error_responses
from app.schemas.auth import LoginResponse
from app.schemas.setup import SetupRequest, SetupStatus
from app.services import first_setup as svc

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get(
    "",
    response_model=SetupStatus,
    summary="Is the first-time setup still open? (public)",
    description="`needed` is true only on an install with no users that was never set up.",
)
def get_setup_status(db: DB) -> SetupStatus:
    return svc.status(db)


@router.post(
    "",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the organisation, first project and first administrator (public, once)",
    description="Creates the organisation record, the first project (with default settings) and "
    "the first user as an organisation-wide HSE Manager, acknowledges the privacy notice and "
    "signs them in. 409 SETUP_ALREADY_DONE once any user exists; 403 when SETUP_TOKEN is set "
    "and `setup_token` does not match. The HSE Manager role needs two-step verification, so the "
    "new administrator is asked to set it up (D-299).",
    responses=error_responses(403, 409, 422),
)
def run_setup(body: SetupRequest, response: Response, db: DB) -> LoginResponse:
    issued, user = svc.run(db, body)
    return _login_response(db, response, issued, user)
