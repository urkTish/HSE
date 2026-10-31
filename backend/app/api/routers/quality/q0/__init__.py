"""HTTP routes of package Q0 (spec 8-quality Part A)."""

from fastapi import APIRouter

from app.api.routers.quality.q0 import records, registers, setup

router = APIRouter()
router.include_router(setup.router)
router.include_router(registers.router)
router.include_router(records.router)
