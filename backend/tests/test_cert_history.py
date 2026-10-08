"""GET /history/{entity_type}/{id} for Phase 4 entity types (gap found by the Phase 4 design
pass: every Phase 4 type answered 404) and the Phase 5 types (501 until Phase 5 stage 2)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.core.enums import Role
from tests.cert_helpers import API, project
from tests.conftest import Api

PHASE4_MODELS: dict[str, Any] = {
    "tpi": m.Tpi,
    "tpi_accreditation": m.TpiAccreditation,
    "tpi_client_approval": m.TpiClientApproval,
    "equipment_item": m.EquipmentItem,
    "equipment_deployment": m.EquipmentDeployment,
    "equipment_certificate": m.EquipmentCertificate,
    "configuration_event": m.ConfigurationEvent,
    "scaffold": m.Scaffold,
    "scaffold_inspection": m.ScaffoldInspection,
    "personnel_certificate": m.PersonnelCertificate,
    "cert_verification": m.CertVerification,
    "equipment_defect": m.EquipmentDefect,
    "certification_ban": m.CertificationBan,
    "hook_policy_state": m.HookPolicyState,
    "cert_import_batch": m.CertImportBatch,
}


def test_phase4_history_endpoints(cert_seed: None, clock: None, db: Session, api: Api) -> None:
    c = api.as_("faisal.harbi")
    seen = 0
    for et, model in PHASE4_MODELS.items():
        eid = db.scalar(select(model.id).limit(1))
        if eid is None:
            continue
        res = c.get(f"{API}/history/{et}/{eid}")
        assert res.status_code == 200, (et, res.text)
        assert isinstance(res.json()["items"], list)
        seen += 1
    assert seen >= 12
    pid = project(db, "ANIA-EXP").id
    assert c.get(f"{API}/history/cert_settings/{pid}").status_code == 200
    # an unknown id is 404 for every Phase 4 type (not a silent empty history)
    for et in PHASE4_MODELS:
        assert c.get(f"{API}/history/{et}/{pid}").status_code == 404, et
    # cert_type changes carry no entity id → no per-record history
    assert c.get(f"{API}/history/cert_type/{pid}").status_code == 404


def test_phase4_history_respects_scope(cert_seed: None, clock: None, db: Session, api: Api) -> None:
    """Rule 38: history only for records the caller can already see. Viewer/Client reads the
    org-wide TPI register (capabilities 17 and 105) but never personnel certificates (P4-1:
    no capability 117) — 404/403, not an empty history."""
    cert = db.scalar(select(m.PersonnelCertificate.id).limit(1))
    tpi_id = db.scalar(select(m.Tpi.id).limit(1))
    viewer = db.scalar(
        select(m.User.email)
        .join(m.RoleAssignment, m.RoleAssignment.user_id == m.User.id)
        .where(m.RoleAssignment.role == Role.viewer_client)
        .limit(1)
    )
    assert viewer is not None
    c = api.as_(viewer)
    assert c.get(f"{API}/history/tpi/{tpi_id}").status_code == 200
    assert c.get(f"{API}/history/personnel_certificate/{cert}").status_code in (403, 404)
    officer = api.as_("noura.qahtani")  # HSE Officer on ANIA-EXP only
    rbt = project(db, "RBT-52").id
    assert officer.get(f"{API}/history/cert_settings/{rbt}").status_code in (403, 404)


def test_phase5_history_types_answer_501_until_stage2(
    cert_seed: None, clock: None, db: Session, api: Api
) -> None:
    c = api.as_("faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    for et in ("training_course", "training_record", "training_session", "training_provider"):
        res = c.get(f"{API}/history/{et}/{pid}")
        assert res.status_code == 501, (et, res.text)
