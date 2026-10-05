"""Projects, sites, zones — AC14-AC16, AC22, rules 17-23, §4.1, §4.4."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models import AuditEntry
from tests.conftest import Api, Ids

AIRSIDE = {
    "airside_area": "apron",
    "in_movement_area": True,
    "escort_required": True,
    "adp_required": True,
}


def _zone(code: str, zone_type: str, airside: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "code": code,
        "name_en": "Test zone",
        "name_ar": "منطقة اختبار",
        "zone_type": zone_type,
        "airside": airside,
    }


def test_AC14_airside_zone_rejected_on_non_airport(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    res = c.post(f"/api/v1/sites/{ids.site('S-TWR')}/zones", json=_zone("Z-X", "airside", AIRSIDE))
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["loc"] == ["body", "zone_type"]
    res = c.post(f"/api/v1/sites/{ids.site('S-TWR')}/zones", json=_zone("Z-Y", "landside"))
    assert res.status_code == 422


def test_AC15_movement_area_required_for_taxiway_strip(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    bad = {**AIRSIDE, "airside_area": "taxiway_strip", "in_movement_area": False}
    res = c.post(f"/api/v1/sites/{ids.site('S-AIR')}/zones", json=_zone("Z-TWC", "airside", bad))
    assert res.status_code == 422
    good = {**bad, "in_movement_area": True}
    res = c.post(f"/api/v1/sites/{ids.site('S-AIR')}/zones", json=_zone("Z-TWC", "airside", good))
    assert res.status_code == 201, res.text
    body = res.json()["airside"]
    assert body["notam_required_for_works"] is True  # defaults to in_movement_area
    assert body["security_restricted_area"] is True and body["fod_control_required"] is True


def test_AC16_landside_zone_with_airside_attributes_rejected(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    site = ids.site("S-LAND")
    res = c.post(
        f"/api/v1/sites/{site}/zones",
        json=_zone("Z-L1", "landside", {**AIRSIDE, "adp_required": True}),
    )
    assert res.status_code == 422
    flat = {**_zone("Z-L2", "landside"), "adp_required": True}
    flat.pop("airside")
    assert c.post(f"/api/v1/sites/{site}/zones", json=flat).status_code == 422
    # PATCH too
    res = c.patch(f"/api/v1/zones/{ids.zone('Z-PIERB')}", json={"airside": AIRSIDE})
    assert res.status_code == 422


def test_zone_type_must_match_site_side(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    res = c.post(f"/api/v1/sites/{ids.site('S-AIR')}/zones", json=_zone("Z-Q", "landside"))
    assert res.status_code == 422
    res = c.post(f"/api/v1/sites/{ids.site('S-LAND')}/zones", json=_zone("Z-Q", "airside", AIRSIDE))
    assert res.status_code == 422


def test_rule17_zone_code_unique_within_site(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    res = c.post(f"/api/v1/sites/{ids.site('S-LAND')}/zones", json=_zone("Z-MSCP", "landside"))
    assert res.status_code == 409 and res.json()["detail"]["code"] == "DUPLICATE_VALUE"


def test_rule21_airside_changes_audited(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("noura.qahtani")
    zid = ids.zone("Z-APR-21")
    current = c.get(f"/api/v1/zones/{zid}").json()["airside"]
    res = c.patch(
        f"/api/v1/zones/{zid}", json={"airside": {**current, "max_equipment_height_m_agl": 9.5}}
    )
    assert res.status_code == 200, res.text
    entry = db.scalars(
        select(AuditEntry).where(
            AuditEntry.action == AuditAction.update, AuditEntry.entity_id == zid
        )
    ).one()
    assert entry.before == {"max_equipment_height_m_agl": 12.0}
    assert entry.after == {"max_equipment_height_m_agl": 9.5}
    hist = c.get(f"/api/v1/history/zone/{zid}").json()["items"]
    assert hist[0]["after"] == {"max_equipment_height_m_agl": 9.5}
    assert hist[0]["actor_name"] == "Noura Al-Qahtani"


def test_AC22_closed_project_is_read_only(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    res = mgr.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "closed"})
    assert res.status_code == 422  # reason required
    res = mgr.post(
        f"/api/v1/projects/{pid}/transitions", json={"to_status": "closed", "reason": "Handover"}
    )
    assert res.status_code == 200 and res.json()["status"] == "closed"
    noura = api.as_("noura.qahtani")
    res = noura.patch(f"/api/v1/zones/{ids.zone('Z-PIERB')}", json={"name_en": "Pier B"})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "PROJECT_CLOSED"
    for r in [
        mgr.patch(f"/api/v1/projects/{pid}", json={"city": "Jeddah"}),
        mgr.patch(f"/api/v1/projects/{pid}/settings", json={"show_hijri": False}),
        noura.post(
            f"/api/v1/projects/{pid}/sites",
            json={"code": "S-N", "name_en": "N", "name_ar": "ن", "site_side": "landside"},
        ),
        noura.patch(
            f"/api/v1/engagements/{ids.engagement('NAJD')}", json={"scope_of_work_en": "x"}
        ),
    ]:
        assert r.status_code == 409 and r.json()["detail"]["code"] == "PROJECT_CLOSED"
    assert noura.get(f"/api/v1/zones/{ids.zone('Z-PIERB')}").status_code == 200
    reopen = mgr.post(
        f"/api/v1/projects/{pid}/transitions", json={"to_status": "active", "reason": "Snag works"}
    )
    assert reopen.status_code == 200
    assert (
        noura.patch(f"/api/v1/zones/{ids.zone('Z-PIERB')}", json={"name_en": "Pier B"}).status_code
        == 200
    )


def test_project_lifecycle(api: Api) -> None:
    mgr = api.as_("faisal.harbi")
    body = {
        "code": "JED-T2",
        "name_en": "Test Airport T2",
        "name_ar": "مطار تجريبي",
        "project_type": "airport",
        "client_name_en": "Client",
        "client_name_ar": "العميل",
        "city": "Jeddah",
        "start_date": "2026-01-01",
    }
    assert mgr.post("/api/v1/projects", json=body).status_code == 422  # ICAO required
    res = mgr.post("/api/v1/projects", json={**body, "airport_icao": "OEJX"})
    assert res.status_code == 201 and res.json()["status"] == "planning"
    assert res.json()["is_airport"] is True
    pid = res.json()["id"]
    dup = mgr.post("/api/v1/projects", json={**body, "airport_icao": "OEJX"})
    assert dup.status_code == 409
    act = mgr.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "active"})
    assert act.status_code == 409 and act.json()["detail"]["code"] == "TRANSITION_CONDITION_NOT_MET"
    site = mgr.post(
        f"/api/v1/projects/{pid}/sites",
        json={
            "code": "S-A",
            "name_en": "A",
            "name_ar": "أ",
            "site_side": "airside",
            "gps_lat": 21.67,
            "gps_lng": 39.15,
        },
    )
    assert site.status_code == 201, site.text
    act = mgr.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "active"})
    assert act.status_code == 409  # settings not saved yet
    assert mgr.patch(f"/api/v1/projects/{pid}/settings", json={}).status_code == 200
    act = mgr.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "active"})
    assert act.status_code == 200
    bad = mgr.post(f"/api/v1/projects/{pid}/transitions", json={"to_status": "planning"})
    assert bad.status_code == 409 and bad.json()["detail"]["code"] == "INVALID_TRANSITION"
    # rule 18: cannot turn into a non-airport project while it has airside sites
    res = mgr.patch(f"/api/v1/projects/{pid}", json={"project_type": "industrial"})
    assert res.status_code == 422
    # officers cannot create projects (capability 1)
    other = {**body, "code": "JED-T3", "airport_icao": "OEJY"}
    assert api.as_("noura.qahtani").post("/api/v1/projects", json=other).status_code == 403


def test_site_side_rules_and_gps_bbox(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    rbt = ids.project("RBT-52")
    res = c.post(
        f"/api/v1/projects/{rbt}/sites",
        json={"code": "S-X", "name_en": "X", "name_ar": "س", "site_side": "airside"},
    )
    assert res.status_code == 422
    res = c.post(
        f"/api/v1/projects/{rbt}/sites",
        json={
            "code": "S-X",
            "name_en": "X",
            "name_ar": "س",
            "site_side": "other",
            "gps_lat": 40.0,
            "gps_lng": 46.0,
        },
    )
    assert res.status_code == 422
    res = c.post(
        f"/api/v1/projects/{rbt}/sites",
        json={"code": "S-X", "name_en": "X", "name_ar": "not arabic", "site_side": "other"},
    )
    assert res.status_code == 422


def test_zone_lifecycle_and_archived(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    zid = ids.zone("Z-LAY1")
    assert (
        c.post(f"/api/v1/zones/{zid}/transitions", json={"to_status": "temporarily_closed"}).json()[
            "status"
        ]
        == "temporarily_closed"
    )
    assert (
        c.post(f"/api/v1/zones/{zid}/transitions", json={"to_status": "active"}).status_code == 200
    )
    assert (
        c.post(f"/api/v1/zones/{zid}/transitions", json={"to_status": "archived"}).status_code
        == 200
    )
    again = c.post(f"/api/v1/zones/{zid}/transitions", json={"to_status": "active"})
    assert again.status_code == 409
    edit = c.patch(f"/api/v1/zones/{zid}", json={"name_en": "x"})
    assert edit.status_code == 409 and edit.json()["detail"]["code"] == "ZONE_ARCHIVED"


def test_inactive_site_rejects_new_zones(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    site = ids.site("S-LAND")
    assert (
        c.post(f"/api/v1/sites/{site}/transitions", json={"to_status": "inactive"}).status_code
        == 200
    )
    res = c.post(f"/api/v1/sites/{site}/zones", json=_zone("Z-NEW", "landside"))
    assert res.status_code == 409 and res.json()["detail"]["code"] == "SITE_INACTIVE"


def test_change_zone_type_landside_to_other_and_airside_validation(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    zid = ids.zone("Z-MSCP")
    res = c.patch(f"/api/v1/zones/{zid}", json={"zone_type": "other"})
    assert res.status_code == 200 and res.json()["zone_type"] == "other"
    res = c.patch(f"/api/v1/zones/{ids.zone('Z-TWB')}", json={"zone_type": "landside"})
    assert res.status_code == 422  # airside site only allows airside zones


def test_zone_filters(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    pid = ids.project("ANIA-EXP")
    res = c.get(f"/api/v1/projects/{pid}/zones", params={"zone_type": "airside"})
    assert res.json()["total"] == 3
    res = c.get(f"/api/v1/projects/{pid}/zones", params={"airside_area": "ils_critical"})
    assert [z["code"] for z in res.json()["items"]] == ["Z-ILS33R"]
    res = c.get(f"/api/v1/projects/{pid}/zones", params={"q": "ساحه", "page_size": 1})
    assert res.json()["total"] == 2 and len(res.json()["items"]) == 1
