# ruff: noqa: E501
"""Helpers for Phase 6f tests (6f Appendix A world, clock 2026-10-06 10:00 Riyadh). Tests use the
``fu_seed`` fixture (Phase 0-6e template + the 6f seed, cloned per test) and ``clock``."""

from __future__ import annotations

import base64
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FuDistribution, FuLesson, FuRequirement, Incident
from app.schemas.followup import FuFileInput
from app.services.followup import common as fc
from tests.cert_helpers import API, P, expect, project
from tests.heat_helpers import eng, local, notified, tick, uid, zone
from tests.train_helpers import kpi

__all__ = [
    "API",
    "P",
    "due",
    "eng",
    "expect",
    "f64",
    "fu2",
    "inc",
    "item",
    "kpi",
    "kpis",
    "lesson",
    "local",
    "make_inc",
    "notified",
    "project",
    "reqs",
    "rules_from",
    "set_case",
    "status",
    "tick",
    "uid",
    "zone",
]  # fmt: skip


def inc(db: Session, ref: str) -> Incident:
    x = db.scalar(select(Incident).where(Incident.ref == ref))
    assert x is not None, ref
    return x


def fu2(db: Session) -> Incident:
    x = db.scalar(
        select(Incident).where(Incident.title == "Escort vehicle contacts parked aircraft wingtip")
    )
    assert x is not None
    return x


def reqs(db: Session, i: Incident) -> dict[str, FuRequirement]:
    rows = db.scalars(select(FuRequirement).where(FuRequirement.incident_id == i.id))
    return {f"{r.rule_code}{':' + r.case_key if r.case_key else ''}": r for r in rows}


def lesson(db: Session, no: str) -> FuLesson:
    x = db.scalar(select(FuLesson).where(FuLesson.lesson_no == no))
    assert x is not None, no
    return x


def item(db: Session, no: str, short: str) -> FuDistribution:
    ls = lesson(db, no)
    for it in db.scalars(select(FuDistribution).where(FuDistribution.lesson_id == ls.id)):
        if fc.eng_code(db, it.engagement_id) == short:
            return it
    raise AssertionError(short)


def f64(name: str = "evidence.txt", text: str = "TEST evidence") -> FuFileInput:
    return FuFileInput(file_name=name, content_base64=base64.b64encode(text.encode()).decode())


def kpis(
    c: TestClient, pid: Any, start: str = "2026-10-01", end: str = "2026-10-31", **params: Any
) -> dict[str, Any]:
    r = c.get(
        f"{API}/kpi/incident-followup",
        params={"project_id": str(pid), "period": "custom", "start": start, "end": end, **params},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def make_inc(
    db: Session,
    pcode: str,
    site: str,
    occurred: Any,
    eng_short: str,
    cases: list[dict[str, Any]] | None = None,
    inv_days: int | None = 14,
    **kw: Any,
) -> Incident:
    """A reported incident (with optional cases and an L3 investigation) built from rows, then
    derived as the followup job would (NR-1…NR-7)."""
    import uuid

    from app.core import crypto
    from app.core.hse_enums import (
        Agency,
        BodyPart,
        CaseCategory,
        ClassificationStatus,
        IdType,
        IncidentStatus,
        IncidentType,
        InjuryNature,
        InvestigationLevel,
        Mechanism,
        PermanentDisability,
        PersonType,
        Trade,
        TreatedAt,
    )  # fmt: skip
    from app.models import InjuryCase, Investigation, Site
    from app.services.followup import requirements as rq
    from app.services.hse_common import next_seq

    pr = project(db, pcode)
    s = db.scalar(select(Site).where(Site.code == site))
    assert s is not None
    d = fc.local_day(occurred)
    seq = next_seq(db, Incident, pr.id, d.year)
    types = kw.pop(
        "incident_types",
        [IncidentType.injury_illness.value if cases else IncidentType.near_miss.value],
    )
    i = Incident(
        id=uuid.uuid4(), project_id=pr.id, ref=f"INC-{pcode}-{d.year}-{seq:04d}", year=d.year, seq=seq,
        site_id=s.id, responsible_engagement_id=eng(db, pcode, eng_short).id, occurred_at=occurred,
        occurred_date=d, reported_at=occurred, incident_types=types,
        primary_type=IncidentType(types[0]), title=kw.pop("title", "Test incident (TEST)"),
        description=kw.pop("description", "Test incident description."),
        status=kw.pop("status", IncidentStatus.under_investigation),
        potential_severity=kw.pop("potential_severity", 2), alerts_sent=[], airside_flags=[], **kw,
    )  # fmt: skip
    db.add(i)
    db.flush()
    for c in cases or []:
        cat = CaseCategory(c.get("cat", "MTC"))
        db.add(InjuryCase(
            id=uuid.uuid4(), incident_id=i.id, project_id=pr.id, person_no=c.get("no", 1),
            person_type=PersonType.contractor_worker, employer_engagement_id=eng(db, pcode, c.get("emp", eng_short)).id,
            person_name=c.get("name", "Rashid Hamdan"), id_type=IdType.iqama,
            id_number_enc=crypto.encrypt(c.get("id", "2345678901")), id_number_masked="******8901",
            nationality="PK", trade=Trade(c.get("trade", "steel_fixer")), body_part=BodyPart.hand,
            nature=InjuryNature.laceration, mechanism=Mechanism(c.get("mech", "struck_against")),
            agency=Agency.hand_tool, treatments=["sutures"], treated_at=TreatedAt.site_clinic,
            fatal=cat == CaseCategory.FAT, permanent_disability=PermanentDisability.none,
            derived_category=cat, confirmed_category=cat,
            classification_status=ClassificationStatus.confirmed,
        ))  # fmt: skip
    if inv_days is not None:
        from datetime import timedelta

        db.add(Investigation(
            incident_id=i.id, level=InvestigationLevel.L3, lead_investigator_id=uid(db, "noura.qahtani"),
            team_member_ids=[], due_date=d + timedelta(days=inv_days), extensions=[], root_causes=[],
            ptw_ids=[], alerts_sent=[],
        ))  # fmt: skip
    db.flush()
    fc.clear_cache(db)
    rq.derive(db, i)
    db.flush()
    return i


def set_case(db: Session, i: Incident, no: int, cat: str) -> None:
    from app.core.hse_enums import CaseCategory
    from app.models import InjuryCase

    c = db.scalar(
        select(InjuryCase).where(InjuryCase.incident_id == i.id, InjuryCase.person_no == no)
    )
    assert c is not None
    c.derived_category = c.confirmed_category = CaseCategory(cat)
    db.flush()


def due(r: FuRequirement) -> str:
    return fc.to_local(r.due_at).strftime("%m-%d %H:%M")


def status(db: Session, r: FuRequirement) -> str:
    from app.core.clock import now
    from app.services.followup import requirements as rq

    return rq.status_of(r, rq._valid_subs(db, [r.id]).get(r.id, []), now()).value


def rules_from(db: Session, pcode: str, d: Any) -> None:
    s = fc.settings_row(db, project(db, pcode).id)
    s.followup_rules_from = d
    db.flush()
    fc.clear_cache(db)
