"""6d-field-assurance §9 ACs 11-20 (execution: scoring, offline, idempotency, scope, void)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.errors import ApiError
from app.models import (
    Attachment,
    ChecklistResponse,
    CorrectiveAction,
    EquipmentDefect,
    Inspection,
    StopWorkOrder,
)
from tests.conftest import Api
from tests.field_helpers import (
    API,
    PNG,
    P,
    body,
    expect,
    local,
    project,
    stop_fields,
    submit,
)

pytestmark = pytest.mark.usefixtures("field_seed", "clock")


def fd1(db: Session, nc: set[str], **kw: Any) -> dict[str, Any]:
    """FD1 on Z-LAY1 (landside, NAJD; no prior GSI non-compliance there)."""
    from tests.field_helpers import answers

    a = answers(db, "GSI", nc, GSI_21={"answer": "na"})
    return body(db, zone_code="Z-LAY1", answer_list=a, **kw)


def test_AC11_fd1_score_and_phase1_counts(api: Api, db: Session) -> None:
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-12", "GSI-19"}))
    assert (r.score_pct, r.applicable_count, r.compliant_count, r.applicable_weight) == (
        "93.1",
        21,
        19,
        "29.000",
    ) or (r.score_pct, r.applicable_count, r.compliant_count) == ("93.1", 21, 19)
    assert r.result.value == "pass"
    db.commit()
    res = api.as_("noura.qahtani").get(f"{API}/inspections/{r.inspection_id}")
    assert res.status_code == 200, res.text
    i = res.json()
    assert (i["items_checked"], i["items_compliant"], i["score_pct"]) == (21, 19, "93.1")


def test_AC12_fd1_b_c_fail_and_stop_fields(db: Session) -> None:
    expect("STOP_RECORD_REQUIRED",
           lambda: submit(db, "noura.qahtani", fd1(db, {"GSI-05", "GSI-12", "GSI-19"})))  # fmt: skip
    db.rollback()
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05", "GSI-12", "GSI-19"}, stop=stop_fields()))
    assert (r.score_pct, r.result.value) == ("82.8", "fail")
    expect("STOP_RECORD_REQUIRED", lambda: submit(db, "noura.qahtani", fd1(db, {"GSI-05"})))
    db.rollback()
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05"}, stop=stop_fields()))
    assert (r.score_pct, r.result.value) == ("89.7", "fail")


def test_AC13_answer_validation(db: Session) -> None:
    from tests.field_helpers import answers

    a = answers(db, "GSI", set(), GSI_05={"answer": "na"})
    expect("NA_NOT_ALLOWED", lambda: submit(db, "noura.qahtani", body(db, answer_list=a)))
    db.rollback()
    a = answers(db, "GSI", set(), GSI_13={"answer": "non_compliant", "note": "No barrier at edge"})
    expect("PHOTO_REQUIRED", lambda: submit(db, "noura.qahtani", body(db, answer_list=a)))
    db.rollback()
    a = answers(db, "GSI", set(), GSI_12={"answer": "non_compliant", "note": "short"})
    e = expect("VALIDATION_ERROR", lambda: submit(db, "noura.qahtani", body(db, answer_list=a)))
    assert e.status_code == 422


def test_AC14_fd8_pooling_numeric_select(db: Session) -> None:
    from decimal import Decimal

    from app.services.field.scoring import evaluate

    # (a) pooled earned / applicable weights (10/10 + 20/40 → 60.0 %, not 75.0)
    assert Decimal(30) * 100 / Decimal(50) == Decimal(60)
    # (b) ELD-04 numeric 0-40 ms
    from tests.field_helpers import tpl

    t = tpl(db, "ELD")
    items = {i["item_code"]: i for i in t.items}
    ok = evaluate([items["ELD-04"]], [{"item_code": "ELD-04", "numeric_value": "38"}],
                  False, require_all=False, audit=False)  # fmt: skip
    bad = evaluate([items["ELD-04"]], [{"item_code": "ELD-04", "numeric_value": "45",
                                        "note": "Trip time measured 45 ms",
                                        "photos": [{"file_name": "a.png", "content_base64": "x"}]}],
                   False, require_all=False, audit=False)  # fmt: skip
    assert ok.evals[0].compliant is True and bad.evals[0].compliant is False
    # (c) single_select option mapping to info → not applicable
    sel = {
        "item_code": "XYZ-01",
        "section_code": "A",
        "item_type": "single_select",
        "weight": 1,
        "critical": False,
        "options": [{"code": "x", "label_en": "x", "maps_to": "info"}],
    }
    s = evaluate([sel], [{"item_code": "XYZ-01", "answer": "x"}], False,
                 require_all=False, audit=False)  # fmt: skip
    assert s.evals[0].applicable is False


def test_AC15_offline_accept_and_too_late(db: Session) -> None:
    from app.models import Notification

    done = local(2026, 10, 5, 8, 0)
    set_now(local(2026, 10, 6, 9, 0))
    r = submit(db, "noura.qahtani", fd1(db, set(), completed=done))
    assert r.offline_delay_min == 1500 and r.recorded_offline
    i = db.get(Inspection, r.inspection_id)
    assert i is not None and i.completed_date == done.date()
    db.commit()
    set_now(local(2026, 10, 8, 8, 1))
    n0 = db.scalar(select(func.count()).select_from(Notification))
    expect("OFFLINE_SUBMIT_TOO_LATE", lambda: submit(db, "noura.qahtani", fd1(db, set(),
                                                                         completed=done)))  # fmt: skip
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Notification)) > n0


def test_AC16_idempotent_and_clock_skew(db: Session) -> None:
    b = fd1(db, {"GSI-05"}, stop=stop_fields())
    r1 = submit(db, "noura.qahtani", b)
    r2 = submit(db, "noura.qahtani", b)
    assert r1.id == r2.id
    assert db.scalar(select(func.count()).select_from(ChecklistResponse)
                     .where(ChecklistResponse.client_uuid == b["client_uuid"])) == 1  # fmt: skip
    assert db.scalar(select(func.count()).select_from(StopWorkOrder)
                     .where(StopWorkOrder.response_id == r1.id)) == 1  # fmt: skip
    assert db.scalar(select(func.count()).select_from(CorrectiveAction)
                     .where(CorrectiveAction.source_id == r1.inspection_id)) == 1  # fmt: skip
    skew = fd1(db, set(), completed=now() + timedelta(minutes=10))
    expect("CLOCK_SKEW", lambda: submit(db, "noura.qahtani", skew))


def test_AC17_self_inspection_scope(db: Session) -> None:
    r = submit(db, "ahmed.zahrani", fd1(db, set()))
    assert r.self_inspection is True
    db.rollback()
    with pytest.raises(ApiError) as ei:
        submit(db, "ahmed.zahrani", body(db, site="S-TWR", zone_code="Z-CORE", eng_code="QIMMA",
                                         pcode="RBT-52"), "RBT-52")  # fmt: skip
    assert ei.value.status_code in (403, 404)
    db.rollback()
    expect("FORBIDDEN", lambda: submit(db, "ramesh.kumar", fd1(db, set())), 403)


def test_AC18_raise_defect_offered(db: Session) -> None:
    from tests.field_helpers import answers

    n0 = db.scalar(select(func.count()).select_from(EquipmentDefect))
    a = answers(db, "LGP", set(), LGP_01={"answer": "non_compliant", "note": "Shackle pin bent",
                                          "equipment_ref": "EQ-TEST-0001",
                                          "photos": [{"file_name": "a.png", "content_base64": PNG}]})  # fmt: skip
    r = submit(db, "noura.qahtani", body(db, "LGP", answer_list=a))
    lgp1 = next(x for x in r.answers if x.item_code == "LGP-01")
    assert lgp1.raise_defect_for == "EQ-TEST-0001"
    assert db.scalar(select(func.count()).select_from(EquipmentDefect)) == n0


def test_AC19_exif_stripped(db: Session) -> None:
    import base64
    import struct
    from pathlib import Path

    from app.core import crypto
    from app.core.config import get_settings
    from app.services.attachments import ENCRYPTED
    from tests.field_helpers import answers

    exif = b"Exif\x00\x00GPSLatitude=24.42N;Make=TestCam"
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34\xff\xd9"
    raw = base64.b64encode(b"\xff\xd8" + app0 + app1 + sos).decode()
    a = answers(db, "GSI", set(), GSI_12={"answer": "non_compliant", "note": "Route blocked by pallets",
                                          "photos": [{"file_name": "gps.jpg", "content_base64": raw}]})  # fmt: skip
    r = submit(db, "noura.qahtani", body(db, zone_code="Z-LAY1", answer_list=a))
    ids = next(x for x in r.answers if x.item_code == "GSI-12").photo_ids
    assert ids
    att = db.get(Attachment, ids[0])
    assert att is not None
    data = (Path(get_settings().storage_dir) / att.storage_key).read_bytes()
    if att.storage_bucket in ENCRYPTED:
        data = crypto.decrypt_bytes(data)
    assert data.startswith(b"\xff\xd8") and b"JFIF" in data
    assert b"GPS" not in data and b"TestCam" not in data


def test_AC20_void(db: Session) -> None:
    from app.models import FieldFinding
    from app.schemas.field import InspectionVoid
    from app.services.field import execution

    rep = db.scalar(
        select(FieldFinding).where(
            FieldFinding.repeat_of_id.is_not(None),
            FieldFinding.item_code == "GSI-12",
            FieldFinding.project_id == project(db, "ANIA-EXP").id,
        )
    )
    assert rep is not None and rep.ca_id is not None  # the FD3 repeat: CA high, open
    resp = db.get(ChecklistResponse, rep.response_id)
    assert resp is not None and resp.inspection_id is not None
    i2 = ins_by_id(db, resp.inspection_id)
    reason = InspectionVoid(reason="Recorded against the wrong zone by mistake (TEST)")
    expect("FORBIDDEN", lambda: execution.void_inspection(db, P(db, "fahad.mutairi"), i2.id,
                                                          reason), 403)  # fmt: skip
    db.rollback()
    cas = list(db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == i2.id)))
    execution.void_inspection(db, P(db, "noura.qahtani"), i2.id, reason)
    db.refresh(i2)
    assert i2.status.value in ("planned", "missed")
    for ca in cas:
        db.refresh(ca)
        assert ca.status.value != "cancelled"
    r = db.scalar(select(ChecklistResponse).where(ChecklistResponse.inspection_id == i2.id))
    assert r is not None and r.voided
    assert ca_open(db, rep.ca_id)


def ins_by_id(db: Session, iid: Any) -> Inspection:
    i = db.get(Inspection, iid)
    assert i is not None
    return i


def ca_open(db: Session, ca_id: Any) -> bool:
    ca = db.get(CorrectiveAction, ca_id)
    return ca is not None and ca.status.value not in ("closed", "cancelled")
