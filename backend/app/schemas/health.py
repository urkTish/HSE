from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"] = Field(description="'degraded' when the database is down.")
    version: str = Field(description="API contract version.")
    database: Literal["ok", "error"]
    time: datetime = Field(description="Server time (UTC).")
