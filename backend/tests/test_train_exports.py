"""5-training §9 AC 140 (training exports, P5-5)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.train import exports as texports
from tests.conftest import Api
from tests.train_helpers import API, project

pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def head(text: str) -> list[str]:
    return text.lstrip("﻿").splitlines()[0].lower().split(",")


def test_P5AC140_record_register_export(
    api: Api, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = str(project(db, "RBT-52").id)
    res = api.as_("lina.haddad").get(
        f"{API}/exports/training_records", params={"project_id": pid, "format": "csv"}
    )
    assert res.status_code == 200, res.text
    h = head(res.text)
    assert "theory_score_pct" in h and any("name" in x for x in h), h
    assert not any("id_number" in x or "scan" in x for x in h), h
    monkeypatch.setattr(texports.acommon, "can_see_names", lambda p, pid: False)
    res = api.as_("omar.siddiqui").get(
        f"{API}/exports/training_records",
        params={"project_id": str(project(db, "ANIA-EXP").id), "format": "csv"},
    )
    assert res.status_code == 200, res.text
    h = head(res.text)
    assert "worker_no" in h and "theory_score_pct" not in h, h
    assert not any(x.startswith("worker_name") or x == "name_en" for x in h), h


def test_P5AC140_all_datasets_answer(api: Api, db: Session) -> None:
    pid = str(project(db, "ANIA-EXP").id)
    c = api.as_("faisal.harbi")
    for ds in texports.DATASETS:
        res = c.get(f"{API}/exports/{ds.value}", params={"project_id": pid, "format": "csv"})
        assert res.status_code == 200, (ds, res.text[:300])


def test_P5AC140_viewer_cannot_export_names(api: Api, db: Session) -> None:
    pid = str(project(db, "ANIA-EXP").id)
    res = api.as_("sarah.mitchell").get(
        f"{API}/exports/training_records", params={"project_id": pid, "format": "csv"}
    )
    assert res.status_code in (200, 403), res.text
    if res.status_code == 200:
        assert "Biju" not in res.text
