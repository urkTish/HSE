"""Automatic daily returns from gate entries / deployments (D-268)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.hse_enums import Shift, WorkforceSource, WorkforceStatus
from app.models import Project, WorkforceReturn
from app.services import hse_settings, workforce_auto
from tests.conftest import Api, Ids

DAY = date(2026, 10, 5)  # a Monday in the Appendix A world


@pytest.fixture
def project(access_seed: None, db: Session) -> Project:
    p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    assert p is not None
    db.execute(delete(WorkforceReturn).where(WorkforceReturn.project_id == p.id))
    db.commit()
    return p


def test_fill_day_counts_people_once_and_applies_standard_hours(
    project: Project, db: Session
) -> None:
    counts = workforce_auto.headcounts(db, project, DAY)
    assert counts, "the Appendix A world has people at work on a weekday"
    res = workforce_auto.fill_day(db, None, project, DAY)
    db.commit()
    assert res["created"] == len(counts)
    rows = db.scalars(select(WorkforceReturn).where(WorkforceReturn.project_id == project.id))
    std = hse_settings.get(db, project.id).standard_hours_per_person_day
    for r in rows:
        assert r.source == WorkforceSource.auto and r.status == WorkforceStatus.submitted
        assert r.headcount == counts[(r.engagement_id, r.site_id)]
        assert r.man_hours == Decimal(r.headcount * std)
    # A second run changes nothing.
    assert workforce_auto.fill_day(db, None, project, DAY) == {
        "created": 0,
        "updated": 0,
        "removed": 0,
        "skipped": 0,
    }


def test_rest_day_without_gate_entries_gets_no_rows(project: Project, db: Session) -> None:
    s = hse_settings.get(db, project.id)
    s.rest_days = ["monday"]
    db.flush()
    if not workforce_auto.headcounts(db, project, DAY):
        assert workforce_auto.fill_day(db, None, project, DAY)["created"] == 0


def test_manual_rows_win_and_auto_rows_take_absence_and_overtime(
    project: Project, db: Session, api: Api
) -> None:
    counts = workforce_auto.headcounts(db, project, DAY)
    (eng_id, site_id), _n = next(iter(counts.items()))
    db.add(
        WorkforceReturn(
            project_id=project.id,
            site_id=site_id,
            engagement_id=eng_id,
            work_date=DAY,
            shift=Shift.day,
            headcount=1,
            man_hours=Decimal(8),
            source=WorkforceSource.manual,
            status=WorkforceStatus.submitted,
            warnings=[],
        )
    )
    db.commit()
    res = workforce_auto.fill_day(db, None, project, DAY)
    db.commit()
    assert res["skipped"] == 1 and res["created"] == len(counts) - 1

    auto = db.scalar(
        select(WorkforceReturn).where(
            WorkforceReturn.project_id == project.id,
            WorkforceReturn.source == WorkforceSource.auto,
        )
    )
    assert auto is not None
    mgr = api.as_("faisal.harbi")
    url = f"/api/v1/workforce-returns/{auto.id}"
    assert mgr.patch(url, json={"headcount": 3}).status_code == 422
    res2 = mgr.patch(url, json={"absent_count": 1, "overtime_hours": "4.50"})
    assert res2.status_code == 200, res2.text
    std = hse_settings.get(db, project.id).standard_hours_per_person_day
    assert Decimal(res2.json()["man_hours"]) == Decimal((auto.headcount - 1) * std) + Decimal(
        "4.50"
    )


def test_auto_fill_endpoint(project: Project, api: Api, ids: Ids, db: Session) -> None:
    mgr = api.as_("faisal.harbi")
    res = mgr.post(
        f"/api/v1/projects/{project.id}/workforce-returns/auto-fill",
        json={"from_date": "2026-10-04", "to_date": "2026-10-05"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["days"] == 2 and res.json()["created"] > 0
    n = db.scalar(
        select(func.count())
        .select_from(WorkforceReturn)
        .where(WorkforceReturn.source == WorkforceSource.auto)
    )
    assert n == res.json()["created"]
    too_long = mgr.post(
        f"/api/v1/projects/{project.id}/workforce-returns/auto-fill",
        json={"from_date": "2026-01-01", "to_date": "2026-10-05"},
    )
    assert too_long.status_code == 422


def test_manual_all_shift_row_blocks_the_auto_row_and_a_new_manual_row_retires_it(
    project: Project, db: Session, api: Api
) -> None:
    counts = workforce_auto.headcounts(db, project, DAY)
    (eng_id, site_id), _n = next(iter(counts.items()))
    # A typed "all"-shift return for the engagement × site × day: no auto row may join it.
    db.add(
        WorkforceReturn(
            project_id=project.id,
            site_id=site_id,
            engagement_id=eng_id,
            work_date=DAY,
            shift=Shift.all,
            headcount=5,
            man_hours=Decimal(50),
            source=WorkforceSource.manual,
            status=WorkforceStatus.submitted,
            warnings=[],
        )
    )
    db.commit()
    res = workforce_auto.fill_day(db, None, project, DAY)
    db.commit()
    assert res["skipped"] == 1
    n = db.scalar(
        select(func.count())
        .select_from(WorkforceReturn)
        .where(
            WorkforceReturn.engagement_id == eng_id,
            WorkforceReturn.site_id == site_id,
            WorkforceReturn.work_date == DAY,
        )
    )
    assert n == 1
    # The reverse: typing a return on top of an auto row retires the auto row.
    (eng2, site2), _n2 = next(k for k in counts.items() if k[0] != (eng_id, site_id))
    auto = db.scalar(
        select(WorkforceReturn).where(
            WorkforceReturn.engagement_id == eng2,
            WorkforceReturn.site_id == site2,
            WorkforceReturn.work_date == DAY,
        )
    )
    assert auto is not None and auto.source == WorkforceSource.auto
    auto_id = auto.id
    mgr = api.as_("faisal.harbi")
    res2 = mgr.post(
        f"/api/v1/projects/{project.id}/workforce-returns",
        json={
            "site_id": str(site2),
            "engagement_id": str(eng2),
            "work_date": DAY.isoformat(),
            "shift": "all",
            "headcount": 3,
            "man_hours": "30.00",
            "submit": True,
        },
    )
    assert res2.status_code == 201, res2.text
    db.expire_all()
    assert db.get(WorkforceReturn, auto_id) is None


def test_auto_rows_are_retired_when_nobody_is_at_work_any_more(
    project: Project, db: Session
) -> None:
    res = workforce_auto.fill_day(db, None, project, DAY)
    db.commit()
    assert res["created"] > 0
    s = hse_settings.get(db, project.id)
    s.auto_man_hours = False
    db.commit()
    res2 = workforce_auto.fill_day(db, None, project, DAY)
    db.commit()
    assert res2["removed"] == res["created"] and res2["created"] == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(WorkforceReturn)
            .where(WorkforceReturn.source == WorkforceSource.auto)
        )
        == 0
    )
