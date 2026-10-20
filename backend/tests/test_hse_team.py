"""HSE department hierarchy (D-270)."""

from tests.conftest import Api, Ids


def test_manager_sets_positions_and_reporting_lines(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    team = mgr.get("/api/v1/hse-team").json()["items"]
    emails = {m["email"] for m in team}
    assert "faisal.harbi@example.com" in emails and "noura.qahtani@example.com" in emails
    boss, officer = ids.user("faisal.harbi"), ids.user("noura.qahtani")
    res = mgr.patch(
        f"/api/v1/hse-team/{officer}",
        json={"hse_position": "hse_engineer", "reports_to_user_id": boss},
    )
    assert res.status_code == 200, res.text
    assert res.json()["reports_to_user_id"] == boss
    loop = mgr.patch(f"/api/v1/hse-team/{boss}", json={"reports_to_user_id": officer})
    assert loop.status_code == 422
    assert (
        mgr.patch(f"/api/v1/hse-team/{boss}", json={"reports_to_user_id": boss}).status_code == 422
    )
    other = api.as_("noura.qahtani").patch(
        f"/api/v1/hse-team/{boss}", json={"hse_position": "other"}
    )
    assert other.status_code == 403
