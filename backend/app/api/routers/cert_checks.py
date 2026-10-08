"""Certification check: EQ sticker, AC card in certificates mode, or a typed cert_no
(spec 4-third-party-cert VF-8, VF-9)."""

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses, not_implemented
from app.schemas.cert_check import CertCheckRequest, CertCheckResponse

router = APIRouter(tags=["certification-checks"])


@router.post(
    "/certification-checks",
    response_model=CertCheckResponse,
    summary="Check an equipment / scaffold sticker or a worker's certificates (capability 121)",
    description="Unknown or revoked tokens return 200 with result unknown / revoked_token (the "
    "screen shows them); out-of-scope subjects return result unknown with reason_code "
    "OUT_OF_SCOPE and no card. Logs `cert_check_view`; records no entry.",
    responses=error_responses(401, 403, 404, 422),
)
def check_certification(body: CertCheckRequest, user: CurrentUser, db: DB) -> CertCheckResponse:
    raise not_implemented()
