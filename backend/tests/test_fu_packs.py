# ruff: noqa: E501
"""Phase 6f packs and PDPL (6f §9 AC 11-17, 44-45)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.followup_enums import FuChannel, FuPackAction, FuPackStatus
from app.models import AuditEntry, FuPack, InjuryCase
from app.schemas.followup import FuPackCreate, FuPackTransition, FuPackUpdate, FuSettingsUpdate, FuSubmissionCreate
from app.services.followup import common as fc
from app.services.followup import config, packs, submissions
from app.services.followup import requirements as rq
from tests.fu_helpers import P, expect, f64, fu2, local, make_inc, project, reqs, rules_from, tick

pytestmark = pytest.mark.usefixtures("fu_seed", "clock")


def fu1(db: Session):  # type: ignore[no-untyped-def]
    tick(2026, 10, 3, 15, 0)
    return make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 3, 14, 20), "NAJD", [{"cat": "MTC", "emp": "NAJD"}])


def fu3(db: Session):  # type: ignore[no-untyped-def]
    rules_from(db, "RBT-52", date(2026, 10, 1))
    tick(2026, 10, 10, 8, 5)
    return make_inc(db, "RBT-52", "S-TWR", local(2026, 10, 10, 8, 0), "QIMMA",
                    [{"cat": "FAT", "emp": "QIMMA", "trade": "steel_erector"}], potential_severity=5)  # fmt: skip


def test_ac11_ac12_gosi_pack_identity(db: Session) -> None:
    i = fu1(db)
    g = reqs(db, i)["GOSI-W:P1"]
    ahmed = P(db, "ahmed.zahrani")
    pk = packs.generate(db, ahmed, g.id, FuPackCreate())
    row = pk.snapshot["cases"][0]  # type: ignore[index]
    assert row["person_name"] == "Rashid Hamdan" and row["id_number"] == "2345678901"
    assert row["body_part"] == "hand" and row["nature"] == "laceration" and row["treated_at"] == "site_clinic"
    acts = {(a.action.value, (a.details or {}).get("purpose")) for a in db.scalars(select(AuditEntry).where(AuditEntry.entity_id == pk.id))}
    assert ("sensitive_field_read", None) in acts or any(x[0] == "sensitive_field_read" for x in acts)
    assert ("export", "gosi") in acts
    row_pk = db.get(FuPack, pk.id)
    assert row_pk is not None
    html = packs.render_html(db, row_pk, g, i)
    assert fc.hijri_str(fc.local_day()) in html and fc.local_day().isoformat() in html
    # AC 12: Fahad (no 29) → 403; he still sees the requirement (215)
    expect("FORBIDDEN", lambda: packs.generate(db, P(db, "fahad.mutairi"), g.id, FuPackCreate()))
    assert rq.read_requirement(db, P(db, "fahad.mutairi"), g.id).rule_code == "GOSI-W"


def test_ac13_client_flash_identity(db: Session) -> None:
    i = fu3(db)
    clf = reqs(db, i)["CL-F"]
    lina = P(db, "lina.haddad")
    pk = packs.generate(db, lina, clf.id, FuPackCreate())
    case = pk.snapshot["cases"][0]  # type: ignore[index]
    assert case["label"] == "Person 1 · steel_erector · QIMMA" and "person_name" not in case
    assert "id_number" not in case and "nationality" not in case and pk.languages == ["en", "ar"]
    pid = project(db, "RBT-52").id
    config.update_settings(db, P(db, "faisal.harbi"), pid, FuSettingsUpdate(
        client_pack_identity="name_and_trade", client_identity_clause="Contract clause 14.3: name and trade in client reports (TEST)."))  # fmt: skip
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.project_id == pid, AuditEntry.action == "settings_changed")) is not None
    pk2 = packs.generate(db, lina, clf.id, FuPackCreate())
    assert pk2.snapshot["cases"][0]["person_name"] == "Rashid Hamdan"  # type: ignore[index]


def test_ac14_identity_in_narrative(db: Session) -> None:
    i = fu3(db)
    clf = reqs(db, i)["CL-F"]
    lina = P(db, "lina.haddad")
    expect("IDENTITY_IN_TEXT", lambda: packs.generate(db, lina, clf.id, FuPackCreate(narrative_en="Rashid fell from the deck.")))
    expect("IDENTITY_IN_TEXT", lambda: packs.generate(db, lina, clf.id, FuPackCreate(narrative_ar="سقط العامل hamdan من السطح")))
    pk = packs.generate(db, lina, clf.id, FuPackCreate(narrative_en="Worker ref 2123456789 fell."))
    assert any(w.code == "POSSIBLE_ID_NUMBER" for w in pk.warnings)


def test_ac15_ac16_final_pack_versions(db: Session) -> None:
    from app.models import Investigation

    i = fu3(db)
    fin = reqs(db, i)["CL-FIN"]
    lina = P(db, "lina.haddad")
    expect("INVESTIGATION_NOT_APPROVED", lambda: packs.generate(db, lina, fin.id, FuPackCreate()))
    inv = db.get(Investigation, i.id)
    assert inv is not None
    inv.root_causes = [{"code": "AD-01", "text": "Permit not followed"}]
    inv.approved_at = local(2026, 10, 12, 9, 0)
    db.flush()
    pk = packs.generate(db, lina, fin.id, FuPackCreate())
    assert pk.snapshot["root_cause_codes"] == ["AD-01"] and "lesson_no" in pk.snapshot  # type: ignore[index]
    # AC 16: incident change flag; v2 supersedes v1; a Submitted pack is immutable
    clf = reqs(db, i)["CL-F"]
    v1 = packs.generate(db, lina, clf.id, FuPackCreate())
    packs.transition_pack(db, P(db, "faisal.harbi"), v1.id, FuPackTransition(action=FuPackAction.approve))
    i.description = "Changed description"
    db.flush()
    assert packs.read_pack(db, lina, v1.id).incident_changed
    v2 = packs.generate(db, lina, clf.id, FuPackCreate())
    assert v2.version == 2 and db.get(FuPack, v1.id).status == FuPackStatus.superseded  # type: ignore[union-attr]
    packs.transition_pack(db, P(db, "faisal.harbi"), v2.id, FuPackTransition(action=FuPackAction.approve))
    tick(2026, 10, 10, 12, 0)
    submissions.record(db, lina, clf.id, FuSubmissionCreate(pack_id=v2.id, channel=FuChannel.email,
                       submitted_at=local(2026, 10, 10, 11, 0), reference_no="CL-TEST-1"))  # fmt: skip
    expect("PACK_IMMUTABLE", lambda: packs.generate(db, lina, clf.id, FuPackCreate()))
    expect("PACK_IMMUTABLE", lambda: packs.update_pack(db, lina, v2.id, FuPackUpdate(narrative_en="x")))


def test_ac17_rep_approval_scope(db: Session) -> None:
    i = fu1(db)
    g = reqs(db, i)["GOSI-W:P1"]
    ahmed = P(db, "ahmed.zahrani")
    pk = packs.generate(db, ahmed, g.id, FuPackCreate())
    expect("NOT_FOUND", lambda: packs.transition_pack(db, P(db, "yousef.ghamdi"), pk.id, FuPackTransition(action=FuPackAction.approve)))
    assert packs.transition_pack(db, ahmed, pk.id, FuPackTransition(action=FuPackAction.approve)).status == FuPackStatus.approved
    aow = reqs(db, fu2(db))["GACA-W"]
    ao = packs.generate(db, P(db, "noura.qahtani"), aow.id, FuPackCreate())
    expect("FORBIDDEN", lambda: packs.transition_pack(db, ahmed, ao.id, FuPackTransition(action=FuPackAction.approve)))


def test_ac44_ac45_viewer_signed_url_and_purge(db: Session) -> None:
    i = fu1(db)
    g = reqs(db, i)["GOSI-W:P1"]
    pk = packs.generate(db, P(db, "ahmed.zahrani"), g.id, FuPackCreate())
    packs.transition_pack(db, P(db, "noura.qahtani"), pk.id, FuPackTransition(action=FuPackAction.approve))
    sarah = P(db, "sarah.mitchell")
    assert rq.read_requirement(db, sarah, g.id).status.value == "due"
    expect("FORBIDDEN", lambda: packs.read_pack(db, sarah, pk.id))
    url = packs.file_url(db, P(db, "noura.qahtani"), pk.id)
    from datetime import UTC, datetime

    from app.core.clock import now

    assert (url.expires_at - datetime.now(UTC)).total_seconds() <= 300  # signed with the wall clock
    # AC 45: anonymisation → identity fields and file deleted; pack_no and dates remain
    tick(2026, 10, 5, 11, 5)
    submissions.record(db, P(db, "ahmed.zahrani"), g.id, FuSubmissionCreate(pack_id=pk.id, channel=FuChannel.portal,
                       submitted_at=local(2026, 10, 5, 11, 0), reference_no="GOSI-TEST-0412", evidence_files=[f64()]))  # fmt: skip
    c = db.scalar(select(InjuryCase).where(InjuryCase.incident_id == i.id))
    assert c is not None
    c.anonymised_at = now()
    db.flush()
    assert packs.purge_identity(db) >= 1
    row = db.get(FuPack, pk.id)
    assert row is not None and row.file_id is None and row.identity_deleted_at is not None
    assert "person_name" not in row.snapshot["cases"][0] and row.pack_no
    sub = submissions.list_submissions(db, P(db, "noura.qahtani"), i.project_id, g.id, 1, 20).items[0]
    assert sub.reference_no == "GOSI-TEST-0412"
