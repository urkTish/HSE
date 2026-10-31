from tests.conftest import Api, Ids


def test_manager_can_list_projects(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    res = c.get("/api/v1/projects")
    assert res.status_code == 200, res.text
    # RUH-CCH is the Quality logistics project (8-quality Appendix A.2)
    assert {p["code"] for p in res.json()["items"]} == {"ANIA-EXP", "RBT-52", "RUH-CCH"}
    me = c.get("/api/v1/auth/me").json()
    assert me["is_hse_manager"] is True
