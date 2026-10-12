"""Expiring items of 7b (spec 7b-fleet-driver §8): `site_vehicle_doc_expiry` (Istimara, insurance,
MVPI, operating card) and `driver_auth_expiry` (effective_valid_until of Active authorisations).
Empty when 7b is off on the project, without capability 233, or for the Viewer / Client
(aggregates only)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import VehicleStatus
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.hse_enums import ExpiringItemKind
from app.core.site_vehicle_enums import SiteVehAuthStatus
from app.models import DriverAuthorisation, Project, Worker
from app.schemas.dashboard import ExpiringItem
from app.services.hse_common import Refs
from app.services.permissions import Principal
from app.services.site_vehicle import common as c
from app.services.site_vehicle.reference import DOC_LABEL


def expiring(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    horizon: date,
    include_overdue: bool,
) -> list[ExpiringItem]:
    g = p.grant(project.id, Capability.site_vehicle_view)
    if g is None or c.is_viewer(p, project.id) or not c.cfg(db, project.id).live:
        return []
    lo = date.min if include_overdue else day
    refs = Refs(db)
    out: list[ExpiringItem] = []
    engs = c.register_engs(p, project.id)
    for v in db.scalars(c.site_vehicle_query(project.id)):
        if v.status == VehicleStatus.withdrawn or not c.covers_eng(db, g, v.engagement_id):
            continue
        if engs is not None and v.engagement_id not in engs:
            continue
        for kind, d in c.documents(v):
            if not lo <= d <= horizon:
                continue
            en, ar = DOC_LABEL[kind]
            out.append(
                ExpiringItem(
                    kind=ExpiringItemKind.site_vehicle_doc_expiry,
                    entity_type=EntityType.vehicle,
                    entity_id=v.id,
                    ref=v.vehicle_no,
                    title_en=f"{v.vehicle_no} ({v.fleet_no}): {en} expires {d}",
                    title_ar=f"{v.vehicle_no}: تنتهي {ar} في {d}",
                    due_date=d,
                    days_left=(d - day).days,
                    engagement=refs.eng(v.engagement_id),
                    detail_path=f"{API_PREFIX}/site-vehicles/{v.id}",
                )
            )
    for a, wno in db.execute(
        select(DriverAuthorisation, Worker.worker_no)
        .join(Worker, Worker.id == DriverAuthorisation.worker_id)
        .where(
            DriverAuthorisation.project_id == project.id,
            DriverAuthorisation.status == SiteVehAuthStatus.active,
            DriverAuthorisation.effective_valid_until.is_not(None),
        )
    ).all():
        due = a.effective_valid_until
        if due is None or not lo <= due <= horizon or not c.covers_eng(db, g, a.engagement_id):
            continue
        out.append(
            ExpiringItem(
                kind=ExpiringItemKind.driver_auth_expiry,
                entity_type=EntityType.driver_authorisation,
                entity_id=a.id,
                ref=a.auth_no,
                title_en=f"{wno}: driver authorisation {a.auth_no} valid until {due}",
                title_ar=f"{wno}: تفويض القيادة {a.auth_no} ساري حتى {due}",
                due_date=due,
                days_left=(due - day).days,
                engagement=refs.eng(a.engagement_id),
                detail_path=f"{API_PREFIX}/driver-authorisations/{a.id}",
            )
        )
    return out
