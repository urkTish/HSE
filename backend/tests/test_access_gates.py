"""Spec 2-access-permits §9 AC54-AC66 (gate check, pairing, scope, device sessions)."""

import re
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    CrewMemberStatus,
    CrewRole,
    GateResult,
    PairingState,
    PairingWaitingFor,
    QrTokenStatus,
    SuspendedContractorGateMode,
)
from app.core.clock import set_now
from app.core.enums import NotificationKind, Role
from app.main import app
from app.models import AccessSettings, GateCheck, GatePairing, QrToken, RoleAssignment, WapCrew
from app.services.access import common, gates
from tests.access_helpers import (
    API,
    avp,
    deployment,
    gate,
    notifications,
    project_id,
    riyadh,
    wap,
    worker,
)
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def card(db: Session, name: str) -> str:
    t = common.active_qr(db, deployment(db, name).id)
    assert t is not None, name
    return common.payload(t)


def sticker(db: Session, vehicle_no: str) -> str:
    t = common.active_qr(db, avp(db, vehicle_no).id)
    assert t is not None, vehicle_no
    return common.payload(t)


def scan(
    c: TestClient,
    db: Session,
    gate_code: str,
    zone: str | None = None,
    *,
    payload: str | None = None,
    printed_ref: str | None = None,
    pairing_id: str | None = None,
    status: int = 200,
) -> dict[str, Any]:
    body: dict[str, Any] = {"gate_id": str(gate(db, gate_code).id)}
    if zone:
        body["zone_id"] = Ids(db).zone(zone)
    if payload:
        body["payload"] = payload
    if printed_ref:
        body["printed_ref"] = printed_ref
    if pairing_id:
        body["pairing_id"] = pairing_id
    res = c.post(f"{API}/gate-checks", json=body)
    assert res.status_code == status, res.text
    out: dict[str, Any] = res.json()
    return out


def codes(r: dict[str, Any]) -> list[str]:
    return [x["code"] for x in r["reasons"]]


# Appendix A puts training_course AVSEC-AWR on every airside zone profile with hook policy
# `warn`, so GC-5 turns every otherwise clean airside scan into GRANTED_WITH_WARNING
# (HOOK_NOT_AVAILABLE). The ACs' "GRANTED" is read as "no DENY reason".
HOOK = "HOOK_NOT_AVAILABLE"


def granted(r: dict[str, Any], *expected_warn: str) -> bool:
    return r["result"] in ("GRANTED", "GRANTED_WITH_WARNING") and set(codes(r)) <= {
        HOOK,
        *expected_warn,
    }


def test_P2AC54_induction_expired_no_id_or_nationality(api: Api, db: Session) -> None:
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=card(db, "Suman Tamang"))
    assert r["result"] == "DENIED"
    assert "INDUCTION_EXPIRED" in codes(r)
    assert r["person"]["full_name_en"] == "Suman Tamang"
    text = str(r)
    assert "2000001006" not in text and "NP" not in re.findall(r"\b[A-Z]{2}\b", text)
    assert "nationality" not in text and "id_number" not in text


def test_P2AC55_suspended_contractor_deny_then_warn(api: Api, db: Session) -> None:
    y = api.as_("yousef.ghamdi")
    r = scan(y, db, "G-RBT-01", payload=card(db, "Bikash Rai"))
    assert r["result"] == "DENIED" and "CONTRACTOR_SUSPENDED" in codes(r)
    s = db.scalar(
        select(AccessSettings).where(AccessSettings.project_id == project_id(db, "RBT-52"))
    )
    assert s is not None
    s.suspended_contractor_gate = SuspendedContractorGateMode.warn
    db.commit()
    r = scan(y, db, "G-RBT-01", payload=card(db, "Bikash Rai"))
    assert r["result"] == "GRANTED_WITH_WARNING", r
    assert "CONTRACTOR_SUSPENDED" in codes(r)


def test_P2AC56_escort_pairing_within_and_after_timeout(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 10, 6, 23, 30))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Abdul Karim Mia"))
    assert r["result"] == "PENDING_ESCORT", r
    assert r["pairing"]["waiting_for"] == "escort"
    pid = r["pairing"]["pairing_id"]
    set_now(riyadh(2026, 10, 6, 23, 31, 59))
    r2 = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Tariq Mahmood"), pairing_id=pid)
    assert granted(r2), r2
    (abdul,) = r2["paired_results"][:1]
    assert abdul["display_ref"] == worker(db, "Abdul Karim Mia").worker_no
    assert abdul["result"] == "GRANTED_WITH_WARNING"
    assert "EXPIRING_7D" in [x["code"] for x in abdul["reasons"]]
    assert {x["severity"] for x in abdul["reasons"]} == {"warn"}

    set_now(riyadh(2026, 10, 6, 23, 40))
    r = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Abdul Karim Mia"))
    pid = r["pairing"]["pairing_id"]
    set_now(riyadh(2026, 10, 6, 23, 42, 1))
    scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Tariq Mahmood"), pairing_id=pid)
    res = n.get(f"{API}/gate-checks/pairings/{pid}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pairing"]["state"] == "timed_out"
    (final,) = body["results"]
    assert final["result"] == "DENIED"
    deny = [x["code"] for x in final["reasons"] if x["severity"] == "deny"]
    assert deny == ["ESCORT_REQUIRED"]


def test_pairing_timeout_job_writes_denied_row(api: Api, db: Session) -> None:
    """Coordinator: a job closes timed-out pairings and writes the escorted person's DENIED
    row at the timeout instant."""
    set_now(riyadh(2026, 10, 6, 23, 30))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Abdul Karim Mia"))
    pid = uuid.UUID(r["pairing"]["pairing_id"])
    assert gates.pairing_timeout_job(db, riyadh(2026, 10, 6, 23, 31)) == 0
    assert gates.pairing_timeout_job(db, riyadh(2026, 10, 6, 23, 35)) == 1
    db.commit()
    pr = db.get(GatePairing, pid)
    assert pr is not None and pr.state == PairingState.timed_out
    rows = list(db.scalars(select(GateCheck).where(GateCheck.pairing_id == pid, GateCheck.final)))
    assert len(rows) == 1
    assert rows[0].result == GateResult.DENIED
    assert rows[0].first_deny_reason == "ESCORT_REQUIRED"
    assert rows[0].reason_codes[0] == "ESCORT_REQUIRED"
    assert rows[0].occurred_at == pr.expires_at


def test_P2AC57_escort_ratio_exceeded(api: Api, db: Session) -> None:
    mahmoud = deployment(db, "Mahmoud Fathy")
    pid = project_id(db, "ANIA-EXP")
    g = gate(db, "G-AAP3")
    at = riyadh(2026, 10, 6, 9)
    for _ in range(5):
        db.add(
            GatePairing(
                id=uuid.uuid4(),
                project_id=pid,
                gate_id=g.id,
                started_check_id=uuid.uuid4(),
                waiting_for=PairingWaitingFor.escort,
                state=PairingState.completed,
                started_at=at,
                expires_at=at + timedelta(seconds=120),
                ended_at=at,
                escort_deployment_id=mahmoud.id,
                escort_day=at.date(),
                subjects=[],
            )
        )
    # the visitor is listed on WAP-0033 (Z-APR-21) as escorted by Mahmoud (ZP-4 step 7)
    db.add(
        WapCrew(
            id=uuid.uuid4(),
            wap_id=wap(db, "2026-0033").id,
            worker_id=worker(db, "David Brown").id,
            crew_role=CrewRole.worker,
            escort_worker_id=mahmoud.worker_id,
            status=CrewMemberStatus.included,
            exclusion_reasons=[],
            escorted=True,
        )
    )
    db.commit()
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=card(db, "David Brown"))
    assert r["result"] == "PENDING_ESCORT", r
    r2 = scan(
        n, db, "G-AAP3", "Z-APR-21", payload=card(db, "Mahmoud Fathy"),
        pairing_id=r["pairing"]["pairing_id"],
    )  # fmt: skip
    assert r2["result"] == "DENIED"
    assert "ESCORT_RATIO_EXCEEDED" in codes(r2)
    assert r2["paired_results"][0]["result"] == "DENIED"


def test_P2AC58_wap_window(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 10, 6, 22, 0))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Rajesh Nair"))
    assert r["result"] == "DENIED" and "WAP_OUTSIDE_WINDOW" in codes(r), r
    set_now(riyadh(2026, 10, 7, 4, 30))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-TWB", payload=card(db, "Rajesh Nair"))
    assert granted(r), r


def test_P2AC59_demobilised_and_lost_card(api: Api, db: Session) -> None:
    n = api.as_("noura.qahtani")
    t = db.scalars(
        select(QrToken)
        .where(QrToken.subject_id == deployment(db, "Arjun Pillai").id)
        .order_by(QrToken.created_at.desc())
    ).first()
    assert t is not None
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=common.payload(t))
    assert r["result"] == "DENIED" and "WORKER_NOT_DEPLOYED" in codes(r), r
    rajesh = deployment(db, "Rajesh Nair")
    old = common.active_qr(db, rajesh.id)
    assert old is not None
    old_payload = common.payload(old)
    common.end_qr(db, rajesh.id, QrTokenStatus.rotated, lost=True)
    common.issue_qr(db, old.kind, old.project_id, rajesh.id, old.printed_ref)
    db.commit()
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=old_payload)
    assert r["result"] == "DENIED" and codes(r) == ["CREDENTIAL_LOST"]
    assert r.get("person") is None
    assert notifications(db, NotificationKind.revoked_token_scanned)


def test_P2AC60_vehicle_escort_vehicle_and_driver(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 10, 6, 10, 0))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-APR-21", printed_ref="VEH-0004")
    assert r["result"] == "PENDING_ESCORT_VEHICLE", r
    assert r["vehicle"]["vehicle_no"] == "VEH-0004" and r["qr_kind"] is None
    pid = r["pairing"]["pairing_id"]
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=sticker(db, "VEH-0006"), pairing_id=pid)
    assert r["result"] == "PENDING_DRIVER", r
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=card(db, "Mahmoud Fathy"), pairing_id=pid)
    assert granted(r), r
    assert {x["result"] for x in r["paired_results"]} <= {"GRANTED", "GRANTED_WITH_WARNING"}
    assert {x["display_ref"] for x in r["paired_results"]} >= {"VEH-0004", "VEH-0006"}
    # VEH-0002 is not on a Z-APR-21 WAP: as escort vehicle → DENIED WAP_MISSING
    r = scan(n, db, "G-AAP3", "Z-APR-21", printed_ref="VEH-0004")
    pid = r["pairing"]["pairing_id"]
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=sticker(db, "VEH-0002"), pairing_id=pid)
    assert r["result"] == "DENIED" and "WAP_MISSING" in codes(r), r


def test_P2AC61_wap_not_active_and_height(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 10, 9, 10, 0))
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-ILS33R", printed_ref="VEH-0005")
    assert r["result"] == "DENIED", r
    assert {"WAP_NOT_ACTIVE", "HEIGHT_CLEARANCE_REQUIRED"} <= set(codes(r))


def test_P2AC62_hook_warns(api: Api, db: Session) -> None:
    y = api.as_("yousef.ghamdi")
    r = scan(y, db, "G-RBT-TC", "Z-TC01", payload=card(db, "Ali Hassan"))
    assert r["result"] == "GRANTED_WITH_WARNING", r
    assert codes(r) == ["HOOK_NOT_AVAILABLE"]


def test_P2AC63_out_of_scope(api: Api, db: Session) -> None:
    r = scan(api.as_("yousef.ghamdi"), db, "G-RBT-01", payload=card(db, "Bikash Rai"))
    assert r["person"]["full_name_en"] == "Bikash Rai"
    # Ahmed has no RBT-52 assignment: at his own gate an RBT-52 card is out of scope (GC-13)
    a = api.as_("ahmed.zahrani")
    assert scan(a, db, "G-RBT-01", payload=card(db, "Bikash Rai"), status=403)
    r = scan(a, db, "G-AAP3", "Z-APR-21", payload=card(db, "Bikash Rai"))
    assert r["result"] == "DENIED" and codes(r) == ["OUT_OF_SCOPE"]
    assert r.get("person") is None and r.get("vehicle") is None
    assert "Bikash" not in str(r)


def test_P2AC64_qr_payload_format(db: Session) -> None:
    pat = re.compile(r"^HSE2:(AC|VS|WP):[A-Za-z0-9_-]{22}$")
    toks = list(db.scalars(select(QrToken)))
    assert toks
    for t in toks:
        p = common.payload(t)
        assert pat.match(p), p
        assert t.printed_ref is None or t.printed_ref not in p


def test_P2AC65_admitted_despite_denial(api: Api, db: Session) -> None:
    n = api.as_("noura.qahtani")
    r = scan(n, db, "G-AAP3", "Z-APR-21", payload=card(db, "Suman Tamang"))
    assert r["result"] == "DENIED"
    res = n.post(
        f"{API}/gate-checks/{r['check_id']}/admitted-despite-denial",
        json={"reason": "Supervisor insisted, escorted by guard TEST"},
    )
    assert res.status_code in (200, 201), res.text
    row = db.get(GateCheck, uuid.UUID(r["check_id"]))
    assert row is not None and row.admitted_despite_denial is True
    sent = notifications(db, NotificationKind.admitted_despite_denial)
    users = {nt.user_id for nt in sent}
    roles = set(db.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id.in_(users))))
    assert {Role.hse_officer, Role.hse_manager} <= roles


def test_P2AC66_gate_device_cannot_list_workers(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    g = gate(db, "G-AAP3")
    res = n.post(
        f"{API}/gates/{g.id}/devices", json={"device_id": "GATE-TAB-99", "label": "Test tab"}
    )
    assert res.status_code == 201, res.text
    token = res.json()["device_token"]
    login = TestClient(app).post(f"{API}/gate-device/login", json={"device_token": token})
    assert login.status_code == 200, login.text
    dev = TestClient(app)
    dev.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    for path in ("/workers", f"/projects/{ids.project('ANIA-EXP')}/deployments"):
        res = dev.get(f"{API}{path}")
        assert res.status_code == 403, res.text
        assert res.json()["detail"]["code"] == "GATE_DEVICE_FORBIDDEN"
    r = scan(dev, db, "G-AAP3", "Z-APR-21", payload=card(db, "Suman Tamang"))
    assert r["result"] == "DENIED"
    other = gate(db, "G-ANIA-01")
    res = dev.post(f"{API}/gate-checks", json={"gate_id": str(other.id), "payload": "x"})
    assert res.status_code == 403, res.text
