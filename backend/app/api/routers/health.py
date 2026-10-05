from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import CONTRACT_VERSION
from app.db.session import get_engine
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness and database check")
def health() -> HealthResponse:
    db_ok = True
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=CONTRACT_VERSION,
        database="ok" if db_ok else "error",
        time=datetime.now(UTC),
    )
