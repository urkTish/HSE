"""Occupational health KPI page (GET /kpi/occupational-health, 6a §6.6). Contract stub."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import MedicalKpiResponse


def medical_kpis(*_: Any) -> MedicalKpiResponse:
    raise not_implemented()
