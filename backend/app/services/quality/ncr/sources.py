"""Q0's NCR source adapters (list NS): `observation` and `complaint` (`manual` needs none).
Wave-2 parts register their own in their `register()` (§3.2 `NCR_SOURCES`)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.quality.common import QDetectionStage, QNcrClass, QRecordType
from app.models import Project
from app.models.quality import QComplaint, QObservation
from app.services.quality import common as qc
from app.services.quality import registry as reg


def observation(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    o = db.get(QObservation, source_id)
    if o is None or o.project_id != project.id:
        raise qc.field_err("source_id", "The observation is not on this project.")
    return reg.SourceInfo(
        ref=o.obs_no,
        title=o.description[:150],
        site_id=o.site_id,
        zone_id=o.zone_id,
        system_id=o.system_id,
        engagement_id=o.engagement_id,
        finding_en=o.description,
        location_ref=o.location_ref,
        detection_stage=QDetectionStage.in_process,
        proposed_class=QNcrClass.minor,
        item_key=f"OBS:{o.category.value}",
        record_type=QRecordType.observation,
    )


def complaint(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    c = db.get(QComplaint, source_id)
    if c is None or c.project_id != project.id:
        raise qc.field_err("source_id", "The complaint is not on this project.")
    return reg.SourceInfo(
        ref=c.complaint_no,
        title=c.description[:150],
        site_id=c.site_id,
        customer_id=c.customer_id,
        finding_en=c.description,
        detection_stage=QDetectionStage.at_customer,
        proposed_class=QNcrClass.major,
        item_key=f"CCM:{c.category.value}",
        record_type=QRecordType.complaint,
    )
