"""HTTP routes of package Q4: documents, audits, suppliers, KPIs, SPC, COPQ, report packs (spec
8-quality Part E). `app.api.routers.quality` includes this router (§3.3a)."""

from fastapi import APIRouter

from app.api.routers.quality.q4 import analytics, audits, documents

router = APIRouter(tags=["quality"])
for _m in (documents, audits, analytics):
    router.include_router(_m.router)
