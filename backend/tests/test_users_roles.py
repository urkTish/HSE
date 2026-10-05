"""Users & role assignments — AC11-AC13, AC20, rules 13-16, 29."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import UserStatus
from app.main import app
from app.models import ProjectEngagement, RoleAssignment, User
from tests.conftest import PASSWORD, Api, Ids


def _manager_assignment(c: TestClient, uid: str) -> str:
    items = c.get(f"/api/v1/users/{uid}/role-assignments").json()["items"]
    return next(a["id"] for a in items if a["role"] == "hse_manager")


def test_AC11_last_hse_manager_cannot_deactivate_or_demote_self(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    uid = ids.user("faisal.harbi")
    res = c.post(
        f"/api/v1/users/{uid}/transitions", json={"to_status": "deactivated", "reason": "x"}
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "LAST_HSE_MANAGER"
    aid = _manager_assignment(c, uid)
    res = c.post(f"/api/v1/users/{uid}/role-assignments/{aid}/revoke")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "LAST_HSE_MANAGER"
    res = c.patch(
        f"/api/v1/users/{uid}/role-assignments/{aid}",
        json={"valid_to": (today() - timedelta(days=1)).isoformat()},
    )
    assert res.status_code == 409


def test_AC11_second_manager_still_cannot_modify_self(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    noura = ids.user("noura.qahtani")
    res = c.post(f"/api/v1/users/{noura}/role-assignments", json={"role": "hse_manager"})
    assert res.status_code == 201, res.text
    uid = ids.user("faisal.harbi")
    res = c.post(
        f"/api/v1/users/{uid}/transitions", json={"to_status": "deactivated", "reason": "x"}
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "SELF_MODIFICATION_FORBIDDEN"


def test_AC12_officer_cannot_assign_admin_roles(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    pid = ids.project("ANIA-EXP")
    target = ids.user("khalid.otaibi")
    for role, project in [("hse_manager", None), ("hse_officer", pid)]:
        res = c.post(
            f"/api/v1/users/{target}/role-assignments", json={"role": role, "project_id": project}
        )
        assert res.status_code == 403, res.text
        assert res.json()["detail"]["code"] == "ROLE_NOT_ASSIGNABLE"
    invite = c.post(
        "/api/v1/users",
        json={
            "email": "another.officer@example.com",
            "full_name_en": "Another Officer",
            "employer_type": "client",
            "role_assignments": [{"role": "hse_officer", "project_id": pid}],
        },
    )
    assert invite.status_code == 403


def test_officer_invites_on_own_project_only(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    body = {
        "email": "site.eng2@example.com",
        "full_name_en": "Turki Al-Anazi",
        "employer_type": "client",
        "role_assignments": [
            {
                "role": "site_engineer",
                "project_id": ids.project("ANIA-EXP"),
                "site_ids": [ids.site("S-LAND")],
            }
        ],
    }
    res = c.post("/api/v1/users", json=body)
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "invited"
    assert res.json()["preferred_language"] == "ar"  # ANIA-EXP default_language
    body["email"] = "site.eng3@example.com"
    body["role_assignments"] = [{"role": "site_engineer", "project_id": ids.project("RBT-52")}]
    assert c.post("/api/v1/users", json=body).status_code == 404
    dup = c.post(
        "/api/v1/users",
        json={
            **body,
            "email": "noura.qahtani@example.com",
            "role_assignments": [{"role": "viewer_client", "project_id": ids.project("ANIA-EXP")}],
        },
    )
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "DUPLICATE_VALUE"


def test_AC13_segregation_of_duties(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    khalid = ids.user("khalid.otaibi")
    res = c.post(
        f"/api/v1/users/{khalid}/role-assignments",
        json={
            "role": "permit_receiver",
            "project_id": ids.project("ANIA-EXP"),
            "contractor_engagement_id": ids.engagement("NAJD"),
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "SOD_CONFLICT"


def test_rule29_contractor_scope_must_match_employer(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    omar = ids.user("omar.siddiqui")  # employer RAWABI
    res = c.post(
        f"/api/v1/users/{omar}/role-assignments",
        json={
            "role": "contractor_hse_rep",
            "project_id": ids.project("ANIA-EXP"),
            "contractor_engagement_id": ids.engagement("NAJD"),
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["loc"] == ["body", "contractor_engagement_id"]
    ok = c.post(
        f"/api/v1/users/{omar}/role-assignments",
        json={
            "role": "contractor_hse_rep",
            "project_id": ids.project("ANIA-EXP"),
            "contractor_engagement_id": ids.engagement("RAWABI"),
        },
    )
    assert ok.status_code == 201


def test_rule15_no_self_role_change(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    res = c.post(
        f"/api/v1/users/{ids.user('faisal.harbi')}/role-assignments",
        json={"role": "viewer_client", "project_id": ids.project("RBT-52")},
    )
    assert res.json()["detail"]["code"] == "SELF_MODIFICATION_FORBIDDEN"


def test_deactivate_revokes_sessions_and_unlock(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    victim = api.as_("khalid.otaibi")
    kid = ids.user("khalid.otaibi")
    no_reason = mgr.post(f"/api/v1/users/{kid}/transitions", json={"to_status": "deactivated"})
    assert no_reason.status_code == 422
    res = mgr.post(
        f"/api/v1/users/{kid}/transitions", json={"to_status": "deactivated", "reason": "Left"}
    )
    assert res.status_code == 200 and res.json()["status"] == "deactivated"
    assert victim.get("/api/v1/auth/me").status_code == 401
    assert api.login("khalid.otaibi@example.com").status_code == 401
    bad = mgr.post(f"/api/v1/users/{kid}/transitions", json={"to_status": "locked"})
    assert bad.status_code == 409 and bad.json()["detail"]["code"] == "INVALID_TRANSITION"
    re = mgr.post(
        f"/api/v1/users/{kid}/transitions", json={"to_status": "active", "reason": "Back"}
    )
    assert re.status_code == 200
    # reactivation forces a password reset
    assert api.login("khalid.otaibi@example.com").status_code == 401


def test_manager_unlocks_locked_user(api: Api, ids: Ids) -> None:
    for _ in range(5):
        api.login("omar.siddiqui@example.com", "Wrong-Password-1!")
    mgr = api.as_("faisal.harbi")
    res = mgr.post(
        f"/api/v1/users/{ids.user('omar.siddiqui')}/transitions", json={"to_status": "active"}
    )
    assert res.status_code == 200 and res.json()["status"] == "active"
    assert api.login("omar.siddiqui@example.com").status_code == 200


def test_AC20_blacklisting_deactivates_users_and_ends_roles(
    api: Api, ids: Ids, db: Session
) -> None:
    mgr = api.as_("faisal.harbi")
    # A SAHARA user with an active session
    invite = mgr.post(
        "/api/v1/users",
        json={
            "email": "sahara.rep@example.com",
            "full_name_en": "Bilal Hussain",
            "employer_type": "contractor",
            "employer_contractor_id": ids.contractor("SAHARA"),
            "role_assignments": [
                {
                    "role": "contractor_hse_rep",
                    "project_id": ids.project("ANIA-EXP"),
                    "contractor_engagement_id": ids.engagement("SAHARA"),
                }
            ],
        },
    )
    assert invite.status_code == 201
    from app.core.config import get_settings
    from app.core.security import hash_password

    db.execute(
        User.__table__.update()
        .where(User.email == "sahara.rep@example.com")
        .values(
            status="active",
            password_hash=hash_password(PASSWORD),
            privacy_notice_version=get_settings().privacy_notice_version,
        )
    )
    db.commit()
    sahara = api.as_("sahara.rep")
    assert sahara.get("/api/v1/auth/me").status_code == 200
    no_reason = mgr.post(
        f"/api/v1/contractors/{ids.contractor('SAHARA')}/transitions",
        json={"to_status": "blacklisted"},
    )
    assert no_reason.status_code == 422
    res = mgr.post(
        f"/api/v1/contractors/{ids.contractor('SAHARA')}/transitions",
        json={"to_status": "blacklisted", "reason": "Falsified inspection records (test)"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "blacklisted"
    db.expire_all()
    u = db.scalars(select(User).where(User.email == "sahara.rep@example.com")).one()
    assert u.status == UserStatus.deactivated
    assignments = db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == u.id)).all()
    assert assignments and all(a.valid_to == today() for a in assignments)
    me = sahara.get("/api/v1/auth/me")
    assert me.status_code == 401  # session ended immediately (≤ 60 s)
    lift = mgr.post(
        f"/api/v1/contractors/{ids.contractor('SAHARA')}/transitions",
        json={"to_status": "suspended", "reason": "Appeal accepted"},
    )
    assert lift.status_code == 200


def test_AC20_descendants_flagged_not_blacklisted(api: Api, ids: Ids, db: Session) -> None:
    mgr = api.as_("faisal.harbi")
    res = mgr.post(
        f"/api/v1/contractors/{ids.contractor('NAJD')}/transitions",
        json={"to_status": "blacklisted", "reason": "test"},
    )
    assert res.status_code == 200
    sahara = db.get(ProjectEngagement, ids.engagement("SAHARA"))
    assert sahara is not None and sahara.parent_blacklisted is True
    assert mgr.get(f"/api/v1/contractors/{ids.contractor('SAHARA')}").json()["status"] == "approved"
    ramesh = db.scalars(select(User).where(User.email == "ramesh.kumar@example.com")).one()
    assert ramesh.status == UserStatus.deactivated
    cleared = mgr.post(f"/api/v1/engagements/{ids.engagement('SAHARA')}/clear-parent-blacklisted")
    assert cleared.status_code == 200 and cleared.json()["parent_blacklisted"] is False


def test_role_assignment_sites_must_belong_to_project(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    res = c.post(
        f"/api/v1/users/{ids.user('khalid.otaibi')}/role-assignments",
        json={
            "role": "site_engineer",
            "project_id": ids.project("ANIA-EXP"),
            "site_ids": [ids.site("S-TWR")],
        },
    )
    assert res.status_code == 422


def test_revoked_role_no_longer_grants_access(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    omar = ids.user("omar.siddiqui")
    aid = mgr.get(f"/api/v1/users/{omar}/role-assignments").json()["items"][0]["id"]
    res = mgr.post(f"/api/v1/users/{omar}/role-assignments/{aid}/revoke")
    assert res.status_code == 200 and res.json()["is_active"] is False
    c = api.as_("omar.siddiqui")
    assert c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}").status_code == 404


def test_future_assignment_not_active_yet(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    res = mgr.post(
        f"/api/v1/users/{ids.user('omar.siddiqui')}/role-assignments",
        json={
            "role": "viewer_client",
            "project_id": ids.project("RBT-52"),
            "valid_from": (today() + timedelta(days=3)).isoformat(),
        },
    )
    assert res.status_code == 201 and res.json()["is_active"] is False
    c = api.as_("omar.siddiqui")
    assert c.get(f"/api/v1/projects/{ids.project('RBT-52')}").status_code == 404


def test_cookie_and_bearer_clients_isolated() -> None:
    assert TestClient(app).get("/api/v1/auth/me").status_code == 401
