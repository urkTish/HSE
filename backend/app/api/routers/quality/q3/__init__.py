"""HTTP routes of package Q3 logistics: receiving, storage and cold chain, stock, recalls,
transport (spec 8-quality Part D).

`app.api.routers.quality` includes this router (Q0 stub, §3.3a); Q3's routes live in `storage`
(products, imports, zones, readings, excursions, mapping, hygiene, pest, metrics) and `flows`
(receiving, holds, stock, returns, recalls, transport)."""

from fastapi import APIRouter

from app.api.routers.quality.q3 import flows, storage

router = APIRouter(tags=["quality"])
router.include_router(storage.router)
router.include_router(flows.router)
