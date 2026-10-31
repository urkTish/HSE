"""HTTP routes of package Q2 materials, testing and lab, welding, calibration, competence
(spec 8-quality Part C). `app.api.routers.quality` includes this router, so Q2 adds routes here
without touching `app/main.py`."""

from fastapi import APIRouter

from app.api.routers.quality.q2 import calibration, competence, materials, testing, welding

router = APIRouter(tags=["quality"])
for _m in (materials, testing, welding, calibration, competence):
    router.include_router(_m.router)
