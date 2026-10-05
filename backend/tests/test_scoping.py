"""Spec §5.2 roles & scoping — AC6-AC10, AC19."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, AuditResult
from app.models import AuditEntry, Zone
from tests.conftest import Api, Ids


def _codes(res: object) -> set[str]:
    return {e["contractor"]["short_code"] for e in res.json()["items"]}  # type: ignore[attr-defined]


def test_AC6_contractor_rep_sees_own_tree(api: Api, ids: Ids) -> None:
    c = api.as_("ahmed.zahrani")
    res = c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/engagements")
    assert res.status_code == 200
    assert _codes(res) == {"RAWABI", "NAJD", "GULFPAVE", "SAHARA"}
    names = {x["short_code"] for x in c.get("/api/v1/contractors").json()["items"]}
    assert names == {"RAWABI", "NAJD", "GULFPAVE", "SAHARA"}
    assert "QIMMA" not in names and "DLIFT" not in names


def test_AC6_rep_cannot_read_other_project_engagement(api: Api, ids: Ids) -> None:
    c = api.as_("ahmed.zahrani")
    assert c.get(f"/api/v1/engagements/{ids.engagement('QIMMA')}").status_code == 404
    assert c.get(f"/api/v1/contractors/{ids.contractor('DLIFT')}").status_code == 404


def test_AC7_out_of_scope_project_404_and_audited(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("yousef.ghamdi")
    pid = ids.project("ANIA-EXP")
    res = c.get(f"/api/v1/projects/{pid}")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "NOT_FOUND"
    entry = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.access_denied)
    ).one()
    assert str(entry.entity_id) == pid
    assert entry.result == AuditResult.denied
    assert str(entry.actor_user_id) == ids.user("yousef.ghamdi")
    # unknown ids are indistinguishable from out-of-scope ones
    assert c.get(f"/api/v1/projects/{uuid.uuid4()}").status_code == 404
    assert c.get(f"/api/v1/projects/{ids.project('RBT-52')}").status_code == 200


def test_AC8_receiver_sees_only_own_contractor(api: Api, ids: Ids) -> None:
    c = api.as_("ramesh.kumar")
    items = c.get("/api/v1/contractors").json()["items"]
    assert [x["short_code"] for x in items] == ["NAJD"]
    assert items[0]["primary_contact_email"] == "najd.hse@example.com"
    engs = c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/engagements")
    assert _codes(engs) == {"NAJD"}
    assert c.get(f"/api/v1/contractors/{ids.contractor('RAWABI')}").status_code == 404


def test_AC8_viewer_never_gets_contact_fields(api: Api) -> None:
    items = api.as_("sarah.mitchell").get("/api/v1/contractors").json()["items"]
    assert items
    for x in items:
        assert "primary_contact_name" not in x
        assert "primary_contact_mobile" not in x
        assert "primary_contact_email" not in x


def test_AC9_viewer_writes_forbidden(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("sarah.mitchell")
    pid = ids.project("ANIA-EXP")
    before = db.scalar(select(func.count()).select_from(Zone))
    attempts = [
        c.patch(f"/api/v1/projects/{pid}", json={"city": "Jeddah"}),
        c.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "on_hold", "reason": "x"}),
        c.post(
            f"/api/v1/projects/{pid}/sites",
            json={"code": "S-X", "name_en": "X", "name_ar": "س", "site_side": "landside"},
        ),
        c.post(
            f"/api/v1/sites/{ids.site('S-LAND')}/zones",
            json={"code": "Z-X", "name_en": "X", "name_ar": "س", "zone_type": "other"},
        ),
        c.patch(f"/api/v1/zones/{ids.zone('Z-PIERB')}", json={"name_en": "Changed"}),
        c.patch(f"/api/v1/projects/{pid}/settings", json={"show_hijri": False}),
        c.patch(f"/api/v1/engagements/{ids.engagement('NAJD')}", json={"scope_of_work_en": "x"}),
        c.patch(f"/api/v1/contractors/{ids.contractor('NAJD')}", json={"vat_number": None}),
    ]
    for res in attempts:
        assert res.status_code == 403, res.text
    assert db.scalar(select(func.count()).select_from(Zone)) == before
    assert c.get(f"/api/v1/projects/{pid}").json()["city"] == "Riyadh"


def test_AC10_site_engineer_sees_only_assigned_site(api: Api, ids: Ids) -> None:
    c = api.as_("omar.siddiqui")
    res = c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/zones")
    assert res.status_code == 200
    assert {z["code"] for z in res.json()["items"]} == {"Z-APR-21", "Z-TWB", "Z-ILS33R"}
    assert {z["site_id"] for z in res.json()["items"]} == {ids.site("S-AIR")}
    sites = c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/sites").json()["items"]
    assert [s["code"] for s in sites] == ["S-AIR"]
    assert c.get(f"/api/v1/zones/{ids.zone('Z-PIERB')}").status_code == 404
    # project-level records remain visible (rule 11)
    assert c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/settings").status_code == 200
    assert c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/engagements").json()["total"] == 4


def test_AC19_suspended_contractor_user_read_only(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    invite = mgr.post(
        "/api/v1/users",
        json={
            "email": "dlift.rep@example.com",
            "full_name_en": "Saeed Al-Dosari",
            "employer_type": "contractor",
            "employer_contractor_id": ids.contractor("DLIFT"),
            "role_assignments": [
                {
                    "role": "contractor_hse_rep",
                    "project_id": ids.project("RBT-52"),
                    "contractor_engagement_id": ids.engagement("DLIFT"),
                }
            ],
        },
    )
    assert invite.status_code == 201, invite.text
    from sqlalchemy import update

    from app.core.config import get_settings
    from app.core.enums import UserStatus
    from app.core.security import hash_password
    from app.db.session import get_sessionmaker
    from app.models import User
    from tests.conftest import PASSWORD

    with get_sessionmaker()() as s:
        s.execute(
            update(User)
            .where(User.email == "dlift.rep@example.com")
            .values(
                status=UserStatus.active,
                password_hash=hash_password(PASSWORD),
                privacy_notice_version=get_settings().privacy_notice_version,
            )
        )
        s.commit()
    c = api.as_("dlift.rep")
    zone = ids.zone("Z-TC01")
    assert c.get(f"/api/v1/zones/{zone}").status_code == 200
    assert c.get(f"/api/v1/projects/{ids.project('RBT-52')}/engagements").status_code == 200
    for res in [
        c.patch(f"/api/v1/zones/{zone}", json={"name_en": "x"}),
        c.post(
            "/api/v1/contractors",
            json={
                "legal_name_en": "X Co",
                "legal_name_ar": "شركة س",
                "short_code": "XCO",
                "cr_number": "1010000099",
                "contractor_category": "other",
                "primary_contact_name": "X",
                "primary_contact_mobile": "+966500000099",
                "primary_contact_email": "x@example.com",
            },
        ),
    ]:
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "CONTRACTOR_SUSPENDED"


def test_assignment_on_project_a_grants_nothing_on_b(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    rbt = ids.project("RBT-52")
    assert c.get(f"/api/v1/projects/{rbt}").status_code == 404
    assert c.get(f"/api/v1/projects/{rbt}/zones").status_code == 404
    assert c.get(f"/api/v1/zones/{ids.zone('Z-CORE')}").status_code == 404
    assert {p["code"] for p in c.get("/api/v1/projects").json()["items"]} == {"ANIA-EXP"}


def test_user_directory_scoping(api: Api) -> None:
    ahmed = {
        u["full_name_en"] for u in api.as_("ahmed.zahrani").get("/api/v1/users").json()["items"]
    }
    # Rep sees users of RAWABI tree on ANIA-EXP (Omar, Ramesh, himself), not client staff
    assert ahmed == {"Ahmed Al-Zahrani", "Omar Siddiqui", "Ramesh Kumar"}
    viewer = api.as_("sarah.mitchell").get("/api/v1/users")
    assert viewer.status_code == 403
    noura = api.as_("noura.qahtani").get("/api/v1/users").json()["items"]
    assert "Yousef Al-Ghamdi" not in {u["full_name_en"] for u in noura}
    assert all("email" in u for u in noura)
