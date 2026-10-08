"""6a-occupational-health §9 ACs 1-14, 24-31 (role, tiers, catalogue, providers, plan, profiles)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models import AuditEntry, Deployment
from tests.conftest import Api, Ids
from tests.med_helpers import API, body, err, fit, ok, post, project, worker

pytestmark = pytest.mark.usefixtures("med_seed", "clock")


def _fitness(api: Api, who: str, db: Session, wno: str, pcode: str = "ANIA-EXP") -> Any:
    w = worker(db, wno)
    return api.as_(who).get(
        f"{API}/workers/{w.id}/fitness", params={"project_id": str(project(db, pcode).id)}
    )


def _dep(db: Session, wno: str, pcode: str = "ANIA-EXP") -> Deployment:
    d = db.scalar(
        select(Deployment).where(
            Deployment.worker_id == worker(db, wno).id,
            Deployment.project_id == project(db, pcode).id,
        )
    )
    assert d is not None
    return d


def _line(api: Api, db: Session, line_no: str, pcode: str = "ANIA-EXP") -> dict[str, Any]:
    res = api.as_("faisal.harbi").get(f"{API}/projects/{project(db, pcode).id}/medical-plan")
    assert res.status_code == 200, res.text
    return next(x for x in res.json()["lines"] if x["line_no"] == line_no)  # type: ignore[no-any-return]


# ---- role and tiers (OH-1, OH-3, §4 tiers) -------------------------------------------------------


def test_AC1_AC2_role_assignment_and_manager_boundary(api: Api, ids: Ids, db: Session) -> None:
    uid = ids.user("sarah.mitchell")
    pid = str(project(db, "ANIA-EXP").id)
    role = {"role": "oh_practitioner", "project_id": pid}
    url = f"{API}/users/{uid}/role-assignments"
    assert api.as_("noura.qahtani").post(url, json=role).status_code == 403
    assert api.as_("faisal.harbi").post(url, json=role).status_code == 201
    faisal = api.as_("faisal.harbi")
    res = post(faisal, db, body(db, "WKR-000014", [fit()]))
    assert res.status_code == 403, res.text
    me = faisal.get(f"{API}/auth/me").json()
    assert "fitness.record_clinic" not in me["org_capabilities"]


def test_AC3_AC4_AC5_tiers(api: Api, db: Session) -> None:
    assert _fitness(api, "omar.siddiqui", db, "WKR-000009").status_code == 404
    n0 = len(
        list(
            db.scalars(
                select(AuditEntry.id).where(AuditEntry.action == AuditAction.sensitive_field_read)
            )
        )
    )
    res = _fitness(api, "fahad.mutairi", db, "WKR-000009")
    assert res.status_code == 200, res.text
    gen = next(x for x in res.json()["items"] if x["code"] == "GEN-FIT")
    assert gen["status"] in ("met", "expiring") and gen["valid_until"] == "2026-12-15"
    assert gen["outcome"] == "fit_with_restrictions"
    assert [r["code"] for r in gen["restrictions"]] == ["no_work_at_height"]
    for hidden in ("assessment_type", "examiner", "provider", "reason_code"):
        assert not gen.get(hidden), hidden
    assert (
        len(
            list(
                db.scalars(
                    select(AuditEntry.id).where(
                        AuditEntry.action == AuditAction.sensitive_field_read
                    )
                )
            )
        )
        > n0
    )
    res = _fitness(api, "ramesh.kumar", db, "WKR-000009")
    assert res.status_code == 200, res.text
    items = {x["code"]: x for x in res.json()["items"]}
    assert res.json()["tier"] == "status" and items["GEN-FIT"].get("outcome") is None
    assert items["WAH-FIT"]["text_en"].startswith("Not eligible")
    res = _fitness(api, "ahmed.zahrani", db, "WKR-000034")
    assert res.status_code == 200 and res.json()["on_hold"] is True, res.text
    assert "referral" not in res.text.lower() or "reason" not in res.text


# ---- catalogue (MC-1 … MC-5) ---------------------------------------------------------------------


def test_AC6_code_in_other_catalogue(api: Api) -> None:
    b = {
        "name_en": "x",
        "name_ar": "x",
        "category": "task",
        "validity_months": 12,
        "examiner_classes": ["occupational_physician"],
        "provider_kinds": ["site_clinic"],
    }
    for code in ("WAH", "CRANE-OPERATOR"):
        res = api.as_("faisal.harbi").post(f"{API}/fitness-codes", json={"code": code, **b})
        assert err(res) == "CODE_IN_OTHER_CATALOGUE", res.text


def test_AC7_to_AC11_catalogue_tightening(api: Api, db: Session) -> None:
    faisal = api.as_("faisal.harbi")
    url = f"{API}/fitness-codes"
    res = api.as_("noura.qahtani").patch(f"{url}/GEN-FIT", json={"validity_months": 12})
    assert res.status_code == 403
    assert err(faisal.patch(f"{url}/CSE-ENTRY-FIT", json={"validity_months": 24})) == (
        "CATALOGUE_LOOSENING"
    )
    ok(faisal.patch(f"{url}/CSE-ENTRY-FIT", json={"validity_months": 6}))
    from tests.med_helpers import hook

    assert hook(db, "WKR-000016", "CSE-ENTRY-FIT").status.value != "met"  # Kamal → 2026-09-01
    ok(faisal.patch(f"{url}/GEN-FIT", json={"provider_kinds": ["site_clinic", "external_clinic"]}))
    res = faisal.patch(
        f"{url}/WAH-FIT",
        json={"provider_kinds": ["site_clinic", "external_clinic", "contractor_clinic"]},
    )
    assert err(res) == "PROVIDER_KIND_NOT_ALLOWED", res.text
    res = faisal.patch(
        f"{url}/RAD-WORKER-FIT", json={"examiner_classes": ["occupational_physician", "physician"]}
    )
    assert err(res) == "CATALOGUE_LOOSENING", res.text
    assert faisal.delete(f"{url}/GEN-FIT").status_code == 409
    ok(faisal.patch(f"{url}/GEN-FIT", json={"active": False}))
    from tests.med_helpers import check

    assert check(db, "WKR-000014", "GEN-FIT").ok  # existing lines stay in force


def test_AC12_project_validity_override(api: Api, db: Session) -> None:
    pid = project(db, "RBT-52").id
    faisal = api.as_("faisal.harbi")
    url = f"{API}/projects/{pid}/medical-settings"
    res = faisal.patch(url, json={"fitness_validity_months": {"GEN-FIT": 30}})
    assert res.status_code == 422, res.text
    ok(faisal.patch(url, json={"fitness_validity_months": {"GEN-FIT": 12}}))
    res = _fitness(api, "faisal.harbi", db, "WKR-000102", "RBT-52")
    gen = next(x for x in res.json()["items"] if x["code"] == "GEN-FIT")
    assert gen["valid_until"] == "2027-06-13", gen


# ---- providers (MP-1, MP-2) ----------------------------------------------------------------------


def test_AC13_AC14_provider_approval(api: Api, db: Session) -> None:
    from tests.med_helpers import provider

    sal = provider(db, "SALAMA")
    url = f"{API}/medical-providers"
    res = api.as_("noura.qahtani").post(f"{url}/{sal.id}/transitions", json={"action": "approve"})
    assert res.status_code == 403, res.text
    faisal = api.as_("faisal.harbi")
    new = ok(
        faisal.post(
            url,
            json={
                "provider_code": "TESTCLIN",
                "legal_name_en": "Test Clinic",
                "legal_name_ar": "عيادة تجريبية",
                "kind": "external_clinic",
                "moh_licence_no": "MOH-TEST-1",
                "licence_valid_until": "2027-12-31",
                "verification_domains": ["testclinic.example"],
            },
        )
    )
    res = faisal.post(f"{url}/{new['id']}/transitions", json={"action": "submit"})
    assert res.status_code == 422, res.text


# ---- plan and profiles (MR-2, MR-5, MR-6, WP-1, WP-2) -------------------------------------------


def test_AC24_AC25_AC26_AC28_derived_lines(api: Api, db: Session) -> None:
    h01 = _line(api, db, "MRL-ANIA-EXP-H01")
    assert h01["read_only"] and h01["code"] == "GEN-FIT"
    noura = api.as_("noura.qahtani")
    res = noura.patch(f"{API}/medical-plan-lines/{h01['line_id']}", json={"due_within_days": 5})
    assert err(res) == "LINE_DERIVED_FROM_HOOK", res.text
    assert _line(api, db, "MRL-ANIA-EXP-E01")["kpi_counted"] is False
    pid = project(db, "ANIA-EXP").id
    res = noura.post(
        f"{API}/projects/{pid}/medical-plan/lines",
        json={"applies_to_kind": "trade", "applies_to_values": ["driver"], "code": "DRIVER-FIT",
              "due_within_days": 14},
    )  # fmt: skip
    assert err(res) == "DUE_DAYS_NOT_ALLOWED", res.text
    res = noura.post(f"{API}/projects/{pid}/medical-exemptions", json={})
    assert err(res) == "EXEMPTION_NOT_ALLOWED", res.text


def test_AC27_remove_line_is_manager_only(api: Api, db: Session) -> None:
    noise = _line(api, db, "MRL-ANIA-EXP-006")
    url = f"{API}/medical-plan-lines/{noise['line_id']}/remove"
    why = {"reason": "Noise survey programme moved to the client (test)"}
    assert err(api.as_("noura.qahtani").post(url, json=why)) == "PLAN_LOOSENING"
    ok(api.as_("faisal.harbi").post(url, json=why))
    res = api.as_("faisal.harbi").get(f"{API}/medical-plan-lines/{noise['line_id']}/versions")
    assert res.status_code == 200 and len(res.json()["items"]) >= 1, res.text


def test_AC29_AC30_AC31_health_profiles(api: Api, db: Session) -> None:
    welder = _dep(db, "WKR-000014")
    res = api.as_("noura.qahtani").get(f"{API}/deployments/{welder.id}/health-profile")
    assert res.status_code == 200 and "noise_85" in res.json()["exposure_groups"], res.text
    ahmed = api.as_("ahmed.zahrani")
    from app.models import Contractor, ProjectEngagement

    qimma = db.scalar(
        select(Deployment)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(Contractor.short_code == "QIMMA", Deployment.status == "mobilised")
        .limit(1)
    )
    assert qimma is not None
    res = ahmed.patch(
        f"{API}/deployments/{qimma.id}/health-profile",
        json={"exposure_groups": ["noise_85"], "reason": "Grinding added to scope"},
    )
    assert res.status_code in (403, 404), res.text
    res = ahmed.patch(
        f"{API}/deployments/{welder.id}/health-profile",
        json={"exposure_groups": ["noise_85", "silica_rcs"], "reason": "Grinding added to scope"},
    )
    assert res.status_code == 200, res.text  # NAJD worker (RAWABI tree)
    from app.services.med import common
    from app.services.med import requirements as rq

    pe = rq.evaluate_project(db, project(db, "ANIA-EXP").id, common.today_local())
    gap = next(r for r in pe.reqs if r.code == "SILICA-SURV" and r.state.value == "gap")
    url = f"{API}/deployments/{gap.dep.id}/health-profile"
    noura = api.as_("noura.qahtani")
    cur = noura.get(url).json()["exposure_groups"]
    keep = [g for g in cur if g != "silica_rcs"]
    res = noura.patch(url, json={"exposure_groups": keep, "reason": "not needed"})
    assert res.status_code == 422, res.text
    why = "Mason moved to finishing works without cutting"
    ok(noura.patch(url, json={"exposure_groups": keep, "reason": why}))
    from app.models import Notification

    assert db.scalar(select(Notification.id).where(Notification.kind == "exposure_group_removed"))
