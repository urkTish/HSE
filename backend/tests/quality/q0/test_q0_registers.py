"""Q0 numbering, criteria, quality checklists, suppliers, M&TE and links (spec 8-quality §A.16,
AC-Q0-17…25, AC-Q0-49)."""

import threading
import uuid

from sqlalchemy import select

from app.core.quality.common import QRecordType
from app.db.session import get_sessionmaker
from app.models import Project
from app.models.quality import QMteItem, QSupplier
from app.services.quality import numbering
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, err, ok, raise_ncr


def test_AC17_concurrent_numbers_never_collide_or_reuse(qsetup: None, api: Api, ids: Ids) -> None:
    results: list[str] = []
    pid = uuid.UUID(ids.project("ANIA-EXP"))

    def take() -> None:
        with get_sessionmaker()() as db:
            p = db.get(Project, pid)
            assert p is not None
            results.append(numbering.assign(db, p, QRecordType.ncr))
            db.commit()

    threads = [threading.Thread(target=take) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = sorted(int(r.rsplit("-", 1)[1]) for r in results)
    assert seqs == [1, 2]
    hatem = api.as_("hatem.shehri")
    n = raise_ncr(hatem, ids)
    assert n["ncr_no"] == "NCR-ANIA-EXP-2026-0003"
    ok(
        hatem.post(
            f"{API}/quality/ncrs/{n['id']}/void",
            json={"reason": "Raised against the wrong project by mistake"},
        )
    )
    assert raise_ncr(hatem, ids)["ncr_no"] == "NCR-ANIA-EXP-2026-0004"


def test_AC18_number_formats(q_seed: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    err(
        hatem.put(
            f"{API}/projects/{pid}/quality/numbering/ncr",
            json={"format": "{PFX}-{PROJECT}", "reset": "yearly"},
        ),
        422,
        "NUMBER_FORMAT_INVALID",
    )
    ok(
        hatem.put(
            f"{API}/projects/{pid}/quality/numbering/ncr",
            json={"format": "{PFX}/{PROJECT}/{YY}/{SEQ5}", "reset": "yearly"},
        )
    )
    n = raise_ncr(hatem, ids)
    assert n["ncr_no"] == "NCR/ANIA-EXP/26/00045"
    old = ok(
        hatem.get(f"{API}/projects/{pid}/quality/ncrs", params={"q": "NCR-ANIA-EXP-2026-0044"})
    )
    assert old["items"][0]["ncr_no"] == "NCR-ANIA-EXP-2026-0044"


def _criterion(api: Api, code: str) -> dict[str, object]:
    res = ok(api.as_("hatem.shehri").get(f"{API}/quality/criteria", params={"code": code}))
    return res["items"][0]


def test_AC19_simple_criteria_verdicts(qsetup: None, api: Api) -> None:
    hatem = api.as_("hatem.shehri")
    c = _criterion(api, "COMP-95")
    for v, verdict in (("96.2", "pass"), ("95.0", "pass"), ("94.4", "fail")):
        r = ok(hatem.post(f"{API}/quality/criteria/{c['id']}/evaluate", json={"value": v}))
        assert r["verdict"] == verdict, v
    faisal = api.as_("faisal.harbi")
    t = ok(
        faisal.post(
            f"{API}/quality/criteria",
            json={
                "code": "SLUMP-TOL",
                "title_en": "Slump 100 ± 25",
                "title_ar": "الهبوط",
                "kind": "target_tolerance",
                "unit": "mm",
                "target": "100",
                "tol_minus": "25",
                "tol_plus": "25",
            },
        ),
        201,
    )
    for v, verdict in (("75", "pass"), ("125", "pass"), ("130", "fail")):
        r = ok(faisal.post(f"{API}/quality/criteria/{t['id']}/evaluate", json={"value": v}))
        assert r["verdict"] == verdict, v


def test_AC20_version_pinning(qsetup: None, api: Api) -> None:
    faisal = api.as_("faisal.harbi")
    v1 = _criterion(api, "COMP-95")
    v2 = ok(faisal.post(f"{API}/quality/criteria/{v1['id']}/new-version"), 201)
    err(
        faisal.patch(f"{API}/quality/criteria/{v1['id']}", json={"min_value": "98.0"}),
        409,
        "CRITERION_IMMUTABLE",
    )
    ok(faisal.patch(f"{API}/quality/criteria/{v2['id']}", json={"min_value": "98.0"}))
    ok(faisal.post(f"{API}/quality/criteria/{v2['id']}/transitions", json={"action": "publish"}))
    assert ok(faisal.get(f"{API}/quality/criteria/{v1['id']}"))["status"] == "superseded"
    r = ok(faisal.post(f"{API}/quality/criteria/{v1['id']}/evaluate", json={"value": "96.2"}))
    assert r["verdict"] == "pass" and r["version"] == 1
    r2 = ok(faisal.post(f"{API}/quality/criteria/{v2['id']}/evaluate", json={"value": "96.2"}))
    assert r2["verdict"] == "fail"


def _template(code: str, stop: bool) -> dict[str, object]:
    return {
        "template_code": code,
        "kind": "quality",
        "quality_type": "receiving",
        "sector_profiles": "logistics",
        "title_en": "Receiving vehicle check",
        "title_ar": "فحص مركبة الاستلام",
        "sections": [{"code": "A", "title_en": "Vehicle", "title_ar": "المركبة"}],
        "items": [
            {
                "item_code": f"{code}-01",
                "section_code": "A",
                "text_en": "Reefer running",
                "text_ar": "وحدة التبريد تعمل",
                "item_type": "yes_no",
                "weight": 3,
                "critical": True,
                "stop_rule": "stop_work" if stop else "none",
            }
        ],
    }


def test_AC21_quality_checklists_on_6d(qsetup: None, api: Api) -> None:
    noura = api.as_("noura.qahtani")
    assert (
        noura.post(f"{API}/checklist-templates", json=_template("QRCVX", False)).status_code == 403
    )
    faisal = api.as_("faisal.harbi")
    bad = ok(faisal.post(f"{API}/checklist-templates", json=_template("QRCVS", True)), 201)
    err(
        faisal.post(
            f"{API}/checklist-templates/{bad['id']}/transitions", json={"action": "publish"}
        ),
        422,
        "STOP_RULE_NOT_ALLOWED",
    )
    good = ok(faisal.post(f"{API}/checklist-templates", json=_template("QRCVG", False)), 201)
    assert good["quality_type"] == "receiving" and good["sector_profiles"] == "logistics"
    pub = ok(
        faisal.post(
            f"{API}/checklist-templates/{good['id']}/transitions", json={"action": "publish"}
        )
    )
    assert pub["status"] == "published"
    # the QA/QC Manager (240) authors kind quality without the 6d capabilities
    hatem = api.as_("hatem.shehri")
    ok(hatem.post(f"{API}/checklist-templates", json=_template("QRCVH", False)), 201)


def test_AC23_supplier_status_on_records(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    with get_sessionmaker()() as db:
        gp = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "GULFPIPE"))
        assert gp is not None
        gid = str(gp.id)
    n = raise_ncr(hatem, ids, supplier_id=gid)
    assert "SUPPLIER_NOT_APPROVED" in {w["code"] for w in n["warnings"]}
    ok(
        api.as_("faisal.harbi").post(
            f"{API}/quality/suppliers/{gid}/transitions",
            json={
                "to_status": "disqualified",
                "reason": "Repeated falsified mill certificates found",
            },
        )
    )
    body = {"site_id": ids.site("S-LAND"), "title": "x", "supplier_id": gid}
    err(
        hatem.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/ncrs", json=body),
        422,
        "SUPPLIER_DISQUALIFIED",
    )


def test_SHR01_supplier_approval_through_matrix(qsetup: None, api: Api, ids: Ids) -> None:
    faisal, hatem = api.as_("faisal.harbi"), api.as_("hatem.shehri")
    s = ok(
        hatem.post(
            f"{API}/quality/suppliers",
            json={
                "supplier_code": "NEWSUP",
                "legal_name_en": "New Supplier Co.",
                "legal_name_ar": "شركة المورد الجديد",
                "categories": ["material_supplier"],
            },
        ),
        201,
    )
    ok(
        hatem.post(
            f"{API}/quality/suppliers/{s['id']}/transitions", json={"to_status": "pending_approval"}
        )
    )
    pid = ids.project("ANIA-EXP")
    err(
        hatem.post(
            f"{API}/quality/suppliers/{s['id']}/transitions",
            json={"to_status": "approved", "project_id": pid},
        ),
        422,
        "SOD_CONFLICT",
    )
    assert (
        faisal.post(
            f"{API}/quality/suppliers/{s['id']}/transitions",
            json={"to_status": "approved", "project_id": pid},
        ).status_code
        == 403
    )


def _mte(api: Api, who: str, project: str, ids: Ids, serial: str) -> object:
    return api.as_(who).post(
        f"{API}/projects/{ids.project(project)}/quality/mte",
        json={
            "mte_type": "temp_logger",
            "description": "Logger",
            "manufacturer": "Acme",
            "serial_no": serial,
            "interval_months": 12,
            "site_id": ids.site("S-DC1"),
        },
    )


def test_AC49_mte_register_in_q0(qsetup: None, api: Api, ids: Ids) -> None:
    m = ok(_mte(api, "imran.siddiq", "RUH-CCH", ids, "LG-0001"), 201)
    assert m["cal_status"] == "unknown" and m["mte_no"] == "MTE-0001"
    imran = api.as_("imran.siddiq")
    u = ok(
        imran.post(
            f"{API}/quality/mte/{m['id']}/usage", json={"record_type": "mte", "record_id": m["id"]}
        ),
        201,
    )
    assert u["verdict"] == "warned"
    assert "MTE_NOT_CALIBRATED" in {w["code"] for w in u["warnings"]}
    assert _mte(api, "sarah.mitchell", "RUH-CCH", ids, "LG-0002").status_code == 403  # type: ignore[attr-defined]
    err(_mte(api, "imran.siddiq", "RUH-CCH", ids, "LG-0001"), 422, "MTE_SERIAL_DUPLICATE")


def test_AC24_mte_use_policy(qsetup: None, api: Api, ids: Ids) -> None:
    m = ok(_mte(api, "imran.siddiq", "RUH-CCH", ids, "LG-0015"), 201)
    with get_sessionmaker()() as db:
        row = db.get(QMteItem, uuid.UUID(m["id"]))
        assert row is not None
        row.cal_status = "overdue"  # type: ignore[assignment]
        db.commit()
    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    body = {"record_type": "mte", "record_id": m["id"]}
    u = ok(imran.post(f"{API}/quality/mte/{m['id']}/usage", json=body), 201)
    assert u["verdict"] == "warned" and u["cal_status_at_use"] == "overdue"
    pid = ids.project("RUH-CCH")
    ok(
        reem.patch(
            f"{API}/projects/{pid}/quality/settings", json={"values": {"mte_use_policy": "block"}}
        )
    )
    err(imran.post(f"{API}/quality/mte/{m['id']}/usage", json=body), 422, "MTE_NOT_CALIBRATED")


def test_AC25_links_stay_inside_one_project(qsetup: None, api: Api, ids: Ids) -> None:
    faisal = api.as_("faisal.harbi")
    a = raise_ncr(faisal, ids)
    b = raise_ncr(faisal, ids, "RUH-CCH")
    err(
        faisal.post(
            f"{API}/quality/links",
            json={"from_type": "ncr", "from_id": a["id"], "to_type": "ncr", "to_id": b["id"]},
        ),
        422,
        "LINK_NOT_ALLOWED",
    )
    c = raise_ncr(faisal, ids)
    link = ok(
        faisal.post(
            f"{API}/quality/links",
            json={"from_type": "ncr", "from_id": a["id"], "to_type": "ncr", "to_id": c["id"]},
        ),
        201,
    )
    assert link["ref"] == c["ncr_no"]
    back = ok(
        faisal.get(f"{API}/quality/links", params={"record_type": "ncr", "record_id": c["id"]})
    )
    assert back[0]["direction"] == "incoming" and back[0]["record_id"] == a["id"]


def test_systems_are_construction_only(qsetup: None, api: Api, ids: Ids) -> None:
    body = {"code": "SYS-X", "name_en": "X", "name_ar": "س", "discipline": "PLB"}
    err(
        api.as_("reem.mutairi").post(
            f"{API}/projects/{ids.project('RUH-CCH')}/quality/systems", json=body
        ),
        409,
        "PROFILE_INACTIVE",
    )
    ok(
        api.as_("hatem.shehri").post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/systems", json=body
        ),
        201,
    )
