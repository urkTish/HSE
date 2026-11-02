"""HTTP routes of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Part B). `app.api.routers.quality` includes this router, so Q1 adds routes here
without touching `app/main.py`. Every write follows the licence read-only guard (D-290)."""

from fastapi import APIRouter

from app.api.routers.quality.q1 import dossiers, irs, itps, punch

router = APIRouter(tags=["quality"])
for _r in (itps, irs, punch, dossiers):
    router.include_router(_r.router)
