"""Phase 6e waste streams, storage areas and consignments (6e §9 AC 9-19, 56)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.env_jobs import env_alerts, env_daily
from app.models import CorrectiveAction, Project, WasteConsignment
from app.schemas.env import AreaCreate, ConsignmentTransition, ConsignmentUpdate, ReceiptInput
from app.services.env import waste
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.env_helpers import (
    D,
    P,
    area,
    con,
    con_body,
    eng,
    expect,
    kpi,
    kpis,
    local,
    notified,
    project,
    prov,
    tick,
    zone,
)


def _area(db: Session, site: str, z: str | None, typ: str, streams: list[str], **kw: object) -> AreaCreate:
    from app.models import Site

    sid = db.scalar(select(Site.id).where(Site.code == site))
    data = {"area_code": "T-01", "site_id": sid, "zone_id": zone(db, z).id if z else None,
            "type": typ, "accepted_streams": streams, "capacity_m3": D("10")}  # fmt: skip
    data.update(kw)
    return AreaCreate.model_validate(data)


def test_storage_area_rules(env_seed: None, clock: None, db: Session) -> None:
    """AC 9-10: containment, hazardous streams, airside and wildlife rules (WST-2, AIR-2)."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    haz = ["used_oil"]
    expect("CONTAINMENT_INSUFFICIENT", lambda: waste.create_area(
        db, p, pid, _area(db, "S-LAND", "Z-LAY1", "hazardous_store", haz, secondary_containment_pct=100)))  # fmt: skip
    ok = waste.create_area(db, p, pid, _area(db, "S-LAND", "Z-LAY1", "hazardous_store", haz,
                                             secondary_containment_pct=110))  # fmt: skip
    assert ok.area_code == "T-01"
    expect("STREAM_NOT_ACCEPTED", lambda: waste.create_area(
        db, p, pid, _area(db, "S-LAND", "Z-LAY1", "skip", haz, area_code="T-02")))  # fmt: skip
    for typ, lid in (("skip", True), ("sealed_bin_station", False)):
        expect("AIRSIDE_STORAGE_NOT_SECURED", lambda t=typ, lk=lid: waste.create_area(  # type: ignore[misc]
            db, p, pid, _area(db, "S-AIR", "Z-APR-21", t, ["general_mixed"], area_code="T-03",
                              lidded_secured=lk)))  # fmt: skip
    with pytest.raises(ApiError) as ei:
        waste.create_area(db, p, pid, _area(db, "S-LAND", "Z-LAY1", "skip", ["food_domestic"],
                                            area_code="T-04"))  # fmt: skip
    assert ei.value.status_code == 422


def _ticket(api: Api, cid: object) -> str:
    return upload_pdf(api.as_("noura.qahtani"), "consignment_ticket", cid)


def test_ev5_receipt_discrepancy_and_close(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 11-12: EV5 estimate 0.900 t, 8.9 % closes, 13.3 % needs a reason, closed is locked;
    a hazardous load needs the manifest reference, a non-hazardous one does not."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    oil = {"storage_area_id": area(db, "HWS-SLAND-01").id, "quantity": D("1000"), "unit": "L",
           "transporter_id": prov(db, "HAZMOVE").id, "facility_provider_id": prov(db, "OILREF").id,
           "facility_code": "OILREF-1"}  # fmt: skip
    expect("MANIFEST_REF_REQUIRED", lambda: waste.create_consignment(db, p, pid, con_body(db, "used_oil", **oil)))
    assert waste.create_consignment(db, p, pid, con_body(db)).status == "dispatched"
    outs = []
    for net in ("0.820", "0.780"):
        c = waste.create_consignment(
            db, p, pid, con_body(db, "used_oil", mwan_manifest_ref="MWAN-MF-TEST-1", **oil))
        assert c.estimated_t == "0.900"
        db.commit()
        fid = _ticket(api, c.id)
        r = waste.record_receipt(db, p, c.id, ReceiptInput(
            received_at=local(2026, 10, 6, 9, 50), received_net_t=D(net), ticket_ref="TKT-TEST-1",
            ticket_file_id=fid))  # fmt: skip
        outs.append((c.id, r.discrepancy_pct))
    assert [D(x[1] or 0).quantize(D("0.1")) for x in outs] == [D("8.9"), D("13.3")]
    close = ConsignmentTransition(action="close")
    assert waste.transition_consignment(db, p, outs[0][0], close).status == "closed"
    expect("DISCREPANCY_REASON_REQUIRED", lambda: waste.transition_consignment(db, p, outs[1][0], close))
    closed = waste.transition_consignment(db, p, outs[1][0], ConsignmentTransition(
        action="close", discrepancy_reason="Moisture evaporated from the drums in transit."))  # fmt: skip
    assert closed.status == "closed"
    err = expect("CONSIGNMENT_CLOSED", lambda: waste.update_consignment(
        db, p, outs[1][0], ConsignmentUpdate(driver_name="X")))  # fmt: skip
    assert err.status_code == 409


def test_overdue_alert_and_late_custody(env_seed: None, db: Session) -> None:
    """AC 13: 00412 not received by 09-29 → 09-30 07:08 alert to Fahad, Ahmed and Noura."""
    c = con(db, "WCN-ANIA-EXP-2026-00412")
    rec = c.receipt_recorded_at
    c.status, c.receipt_recorded_at, c.received_at, c.received_net_t = "dispatched", None, None, None
    db.flush()
    since = tick(2026, 9, 30, 7, 8)
    env_alerts(db)
    got = notified(db, "consignment_overdue", since)
    assert {"fahad.mutairi", "ahmed.zahrani", "noura.qahtani"} <= set(got), got
    assert rec is not None and rec.date() > c.due_on


def test_provisional_tonnes_and_exclusions(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 14-16, 56: EV1b provisional 3.600 t then 3.420; voided / rejected leave K-119; rejection
    raises one CA high and a re-dispatch may reference it; Fahad cannot void (214)."""
    pid = project(db, "ANIA-EXP").id
    c = db.scalar(select(WasteConsignment).where(
        WasteConsignment.project_id == pid, WasteConsignment.stream_code == "general_mixed",
        WasteConsignment.dispatched_date == date(2026, 9, 29),
        WasteConsignment.status == "dispatched"))  # fmt: skip
    assert c is not None
    p = P(db, "noura.qahtani")
    r = waste.read_consignment(db, p, c.id)
    assert (r.tonnes, r.provisional) == ("3.600", True)
    f = api.as_("faisal.harbi")
    assert kpi(kpis(f, pid), "K119")["value"] == "717.4"
    db.commit()
    fid = _ticket(api, c.id)
    waste.record_receipt(db, p, c.id, ReceiptInput(
        received_at=local(2026, 10, 6, 9), received_net_t=D("3.420"), ticket_ref="TKT-TEST-2",
        ticket_file_id=fid))  # fmt: skip
    db.commit()
    assert kpi(kpis(f, pid), "K119")["value"] == "717.2"
    # void (Fahad 403, Noura ok) and reject leave K-119…K-121
    other = db.scalars(select(WasteConsignment).where(
        WasteConsignment.project_id == pid, WasteConsignment.stream_code == "inert_cd",
        WasteConsignment.dispatched_date >= date(2026, 9, 1))).first()  # fmt: skip
    assert other is not None
    void = ConsignmentTransition(action="void", reason="Duplicate entry made by mistake on site")
    with pytest.raises(ApiError) as ei:
        waste.transition_consignment(db, P(db, "fahad.mutairi"), other.id, void)
    assert ei.value.status_code == 403
    waste.transition_consignment(db, p, other.id, void)
    db.commit()
    assert kpi(kpis(f, pid), "K119")["value"] == "703.2"
    new = waste.create_consignment(db, p, pid, con_body(db))
    rej = waste.transition_consignment(db, p, new.id, ConsignmentTransition(
        action="reject", reason="Load contaminated with plastics"))  # fmt: skip
    ca = db.get(CorrectiveAction, rej.ca_id)
    assert ca is not None and ca.priority.value == "high" and ca.source_type.value == "environmental"
    again = waste.create_consignment(db, p, pid, con_body(db, redispatch_of_id=new.id))
    assert again.redispatch_of_id == new.id


def test_hazardous_storage_deadline(env_seed: None, api: Api, db: Session) -> None:
    """AC 17: EV8 reminder 10-04, 12 days left at the clock, CA high on 10-19, a dispatch clears."""
    hws = area(db, "HWS-SLAND-01")
    since = tick(2026, 10, 4, 7, 8)
    env_alerts(db)
    got = notified(db, "haz_storage_deadline", since)
    assert {"fahad.mutairi", "noura.qahtani"} <= set(got), got
    tick(2026, 10, 6, 10)
    h = [x for x in waste.haz_deadlines(db, hws) if x.stream_code == "chemical_containers"][0]
    assert (h.deadline, h.days_left) == (date(2026, 10, 18), 12)
    tick(2026, 10, 19, 0, 11)
    n0 = db.scalar(select(CorrectiveAction.id).where(CorrectiveAction.source_id == hws.id))
    env_daily(db)
    env_daily(db)
    cas = db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == hws.id)).all()
    assert n0 is None and len(cas) == 1 and cas[0].priority.value == "high"
    tick(2026, 10, 19, 10)
    p = P(db, "noura.qahtani")
    waste.create_consignment(db, p, hws.project_id, con_body(
        db, "chemical_containers", storage_area_id=hws.id, quantity=D("0.4"),
        transporter_id=prov(db, "HAZMOVE").id, facility_provider_id=prov(db, "HAZTREAT").id,
        facility_code="HAZTREAT-1", mwan_manifest_ref="MWAN-MF-TEST-77",
        dispatched_at=local(2026, 10, 19, 9)))  # fmt: skip
    assert not [x for x in waste.haz_deadlines(db, hws) if x.stream_code == "chemical_containers"]


def test_scope_and_avp(env_seed: None, clock: None, db: Session) -> None:
    """AC 18-19: Ahmed records for NAJD; RBT-52 is 404 for him; he cannot close (207);
    WSA-SAIR-01 with a plate without an Active AVP → warning AVP_NOT_FOUND."""
    ahmed = P(db, "ahmed.zahrani")
    pid = project(db, "ANIA-EXP").id
    c = waste.create_consignment(db, ahmed, pid, con_body(
        db, generator_engagement_id=eng(db, "ANIA-EXP", "NAJD").id))  # fmt: skip
    assert c.generator_code == "NAJD"
    rbt = db.scalar(select(Project.id).where(Project.code == "RBT-52"))
    with pytest.raises(ApiError) as ei:
        waste.create_consignment(db, ahmed, rbt, con_body(
            db, generator_engagement_id=eng(db, "RBT-52", "QIMMA").id))  # fmt: skip
    assert ei.value.status_code == 404
    with pytest.raises(ApiError) as ei:
        waste.transition_consignment(db, ahmed, c.id, ConsignmentTransition(action="reject",
                                                                            reason="Wrong load"))  # fmt: skip
    assert ei.value.status_code == 403
    p = P(db, "noura.qahtani")
    sair = waste.create_consignment(db, p, pid, con_body(
        db, "general_mixed", storage_area_id=area(db, "WSA-SAIR-01").id, quantity=D("3"),
        facility_provider_id=prov(db, "RIYADH-LF").id, facility_code="RIYADH-LF",
        vehicle_plate="1234 ZZZ"))  # fmt: skip
    assert [w.code for w in sair.warnings] == ["AVP_NOT_FOUND"]
    ok = waste.create_consignment(db, p, pid, con_body(
        db, "general_mixed", storage_area_id=area(db, "WSA-SAIR-01").id, quantity=D("3"),
        facility_provider_id=prov(db, "RIYADH-LF").id, facility_code="RIYADH-LF",
        vehicle_plate="9006 SXN"))  # fmt: skip
    assert ok.warnings == []
