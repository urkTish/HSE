"""Phase 8 Quality routes (spec 8-quality §3.3a): the only router module `app/main.py` includes.
It includes Q0's router and the routers of `q1` … `q4` (each part adds its routes there) and
registers every part's providers once (`app.services.quality.ensure_registered`)."""

from fastapi import APIRouter

from app.api.routers.quality import q0, q1, q2, q3, q4
from app.services.quality import ensure_registered

ensure_registered()

router = APIRouter()
for _part in (q0, q1, q2, q3, q4):
    router.include_router(_part.router)
