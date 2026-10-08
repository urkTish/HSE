# ruff: noqa: E501
"""Phase 3 named records (3-ptw Appendix A.7, A.8), driven through the services.

Each permit follows its own timeline with the clock pinned (`set_now`) so signatures, hashes,
shifts, gas tests and audit trails carry the Appendix A times. Permit numbers are set right
after creation (before the first signature, which hashes the number).
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.clock import set_now
from app.core.ptw_enums import PermitType
from app.models import Permit, Worker
from app.seed_ptw import Ctx, at, principal

T = PermitType
PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63f8ffff3f0005fe02fea7d6a7d10000000049454e44ae426082"
    )
).decode()
EMERGENCY = "Assembly point AP-3 (gate L2); emergency 997; first aid: site clinic L2"
DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def win(start: str, end: str) -> list[dict[str, Any]]:
    return [{"start_local": start, "end_local": end, "weekdays": DAYS}]


@dataclass
class N:
    ctx: Ctx
    password: str

    @property
    def db(self) -> Any:
        return self.ctx.db

    def p(self, key: str) -> Any:
        return principal(self.ctx, key)

    def w(self, no: str) -> uuid.UUID:
        return self.ctx.workers[no].id

    def bulk_worker(
        self,
        project: str,
        contractor: str,
        n: int,
        skip: set[uuid.UUID] | None = None,
        site: str | None = None,
        zone: str | None = None,
        until: datetime | None = None,
    ) -> list[uuid.UUID]:
        """`n` Phase 2 bulk workers of the engagement with a valid GEN induction (A.7 "bulk")."""
        from app.models import Deployment
        from app.seed_ptw import _valid_courses

        eng = self.ctx.eng(project, contractor)
        out: list[uuid.UUID] = []
        sid = self.ctx.site(project, site).id if site else None
        used = skip or set()
        for wk, dep in self.db.execute(
            select(Worker, Deployment)
            .join(Deployment, Deployment.worker_id == Worker.id)
            .where(
                Worker.seq >= 1000,
                Deployment.engagement_id == eng.id,
                Deployment.demobilised_on.is_(None),
            )
            .order_by(Worker.seq.desc())
        ):
            if wk.id in used or wk.id in self.ctx.bulk_used:
                continue
            if sid and sid not in (dep.site_ids or []):
                continue
            if wk.id_expiry_date.year < 2027:
                continue
            if "GEN" not in _valid_courses(self.db, wk.id):
                continue
            if zone and not self._eligible(wk.id, zone, until):
                continue
            out.append(wk.id)
            self.ctx.bulk_used.add(wk.id)
            if len(out) == n:
                break
        return out

    def _eligible(self, wid: uuid.UUID, zone: str, until: datetime | None) -> bool:
        from app.core.access_enums import EligibilityContext
        from app.core.clock import now
        from app.services.access import eligibility

        zid = self.ctx.zones[zone].id
        for t in (now(), until or now()):
            ev = eligibility.eligibility(self.db, wid, zid, t, EligibilityContext.ptw)
            if ev is None or not ev.eligible:
                return False
        return True

    def cosign(self, key: str) -> dict[str, Any]:
        return {"user_id": str(self.ctx.uid(key)), "password": self.password}

    # ---- permit helpers ------------------------------------------------------------------------

    def wap_crew(self, wap_no: str, n: int) -> list[uuid.UUID]:
        from app.models import Wap, WapCrew

        w = self.db.scalar(select(Wap).where(Wap.wap_no == wap_no))
        assert w is not None
        out: list[uuid.UUID] = []
        for wk in self.db.scalars(
            select(Worker)
            .join(WapCrew, WapCrew.worker_id == Worker.id)
            .where(WapCrew.wap_id == w.id, Worker.seq >= 1000)
            .order_by(Worker.seq)
        ):
            if wk.id in self.ctx.bulk_used:
                continue
            out.append(wk.id)
            self.ctx.bulk_used.add(wk.id)
            if len(out) == n:
                break
        return out

    def wap_id(self, wap_no: str) -> str:
        from app.models import Wap

        return str(self.db.scalar(select(Wap.id).where(Wap.wap_no == wap_no)))

    def add_equipment(self, permit: Permit, key: str, body: dict[str, Any]) -> uuid.UUID:
        from app.schemas.permits import PermitEquipmentInput
        from app.services.ptw import permits

        res = permits.add_equipment(
            self.db, self.p(key), permit.id, PermitEquipmentInput.model_validate(body)
        )
        return res.id

    def sections(self, permit: Permit, key: str, sections: list[dict[str, Any]]) -> None:
        from app.schemas.permits import SectionsInput
        from app.services.ptw import permits

        permits.put_sections(
            self.db, self.p(key), permit.id, SectionsInput.model_validate({"sections": sections})
        )

    def close(
        self, permit: Permit, receiver: str, issuer: str, t_req: datetime, t_close: datetime
    ) -> None:
        from app.schemas.permits import CloseInput, ClosureRequestInput
        from app.services.ptw import lifecycle

        set_now(t_req)
        self.checklist(permit, receiver, "closure")
        lifecycle.request_closure(
            self.db,
            self.p(receiver),
            permit.id,
            ClosureRequestInput(work_status="complete", crew_withdrawn=True),
        )
        set_now(t_close)
        lifecycle.close(self.db, self.p(issuer), permit.id, CloseInput(site_visit_confirmed=True))

    def base(
        self,
        project: str,
        site: str,
        zones: list[str],
        loc: str,
        x: str | None,
        y: str | None,
        level: str | None,
        elev: str | None,
        con: str,
        types: list[str],
        primary: str,
        title: str,
        vf: datetime,
        vt: datetime,
        windows: list[dict[str, Any]],
        receiver: str,
        area: str,
        issuer: str,
        hse: str | None,
        supervisor: str | None,
    ) -> dict[str, Any]:
        c = self.ctx
        b: dict[str, Any] = {
            "site_id": str(c.site(project, site).id),
            "zone_ids": [str(c.zones[z].id) for z in zones],
            "location_desc": loc,
            "engagement_id": str(c.eng(project, con).id),
            "work_types": types,
            "primary_type": primary,
            "title": title,
            "scope_en": title + " as per the method statement.",
            "valid_from_at": vf.isoformat(),
            "valid_to_at": vt.isoformat(),
            "windows": windows,
            "receiver_user_id": str(c.uid(receiver)),
            "area_authority_user_id": str(c.uid(area)),
            "issuer_user_id": str(c.uid(issuer)),
            "emergency_info": EMERGENCY,
        }
        if x is not None:
            b["grid_x_m"], b["grid_y_m"] = x, y
        if level is not None:
            b["level_code"], b["elevation_m"] = level, elev
        if hse:
            b["hse_reviewer_user_id"] = str(c.uid(hse))
        if supervisor:
            b["supervisor_worker_id"] = supervisor
        return b

    def create(self, key: str, project: str, no: str, body: dict[str, Any]) -> Permit:
        from app.schemas.permits import PermitCreate
        from app.services.ptw import permits

        res = permits.create(
            self.db, self.p(key), self.ctx.pid(project), PermitCreate.model_validate(body)
        )
        permit = self.db.get(Permit, res.id)
        assert permit is not None
        seq = int(no.rsplit("-", 1)[1])
        permit.seq = seq
        permit.permit_no = no
        self.db.flush()
        from app.models import Jsa

        for j in self.db.scalars(select(Jsa).where(Jsa.permit_id == permit.id)):
            j.jsa_no = f"JSA-{no.removeprefix('PTW-')}"
        self.db.flush()
        self.ctx.permits[no] = permit
        out: Permit = permit
        return out

    def jsa(
        self,
        permit: Permit,
        author: str,
        issuer: str,
        hse: str | None,
        extra: list[dict[str, Any]] | None = None,
    ) -> None:
        """Fill missing mandatory hazards, submit, accept (by band) and approve the instance."""
        from app.models import Jsa
        from app.schemas.jsa import (
            JsaTransition,
            JsaUpdate,
            ResidualAcceptanceInput,
        )
        from app.services.ptw import jsa

        j = self.db.scalar(select(Jsa).where(Jsa.permit_id == permit.id))
        assert j is not None
        steps = [dict(s) for s in (j.steps or [])]
        missing = jsa.missing_hazards(self.db, j)
        add = list(extra or [])
        for h in missing:
            if any(x["hazard_code"] == h.value for x in add):
                continue
            add.append(
                {
                    "hazard_code": h.value,
                    "description": f"{h.value.replace('_', ' ').capitalize()} (site specific)",
                    "initial_l": 3,
                    "initial_s": 3,
                    "controls": [
                        {"text": "Engineered barrier / guarding", "level": "engineering"},
                        {"text": "Briefing and supervision", "level": "administrative"},
                    ],
                    "residual_l": 1,
                    "residual_s": 3,
                }
            )
        if add:
            steps.append(
                {
                    "step_no": len(steps) + 1,
                    "description_en": "Site-specific hazards",
                    "hazards": add,
                }
            )
        clean = [
            {
                "step_no": s["step_no"],
                "description_en": s["description_en"],
                "description_ar": s.get("description_ar"),
                "hazards": [
                    {
                        k: h[k]
                        for k in (
                            "hazard_code",
                            "description",
                            "initial_l",
                            "initial_s",
                            "controls",
                            "residual_l",
                            "residual_s",
                        )
                    }
                    for h in s["hazards"]
                ],
            }
            for s in steps
        ]
        jsa.update(self.db, self.p(author), j.id, JsaUpdate.model_validate({"steps": clean}))
        jsa.transition(self.db, self.p(author), j.id, JsaTransition(to_status="submitted"))
        band = jsa.governing_band(j)
        assert band is not None
        if band.value == "low":
            jsa.accept(self.db, self.p(author), j.id, ResidualAcceptanceInput())
        elif band.value in ("medium", "high"):
            jsa.accept(
                self.db,
                self.p(issuer),
                j.id,
                ResidualAcceptanceInput(
                    alarp_justification=None
                    if band.value == "medium"
                    else "Edge protection, netting and SRL reduce the risk as low as reasonably practicable."
                ),
            )
            if band.value == "high" and hse:
                jsa.accept(
                    self.db,
                    self.p(hse),
                    j.id,
                    ResidualAcceptanceInput(
                        alarp_justification="Engineering controls on every High line; residual risk ALARP for the duration of the permit."
                    ),
                )
        jsa.transition(self.db, self.p(issuer), j.id, JsaTransition(to_status="approved"))

    def checklist(self, permit: Permit, key: str, kind: str = "pre_issue") -> None:
        from app.schemas.permits import ChecklistInput
        from app.services.ptw import evaluation, permits

        items = (
            evaluation.pre_issue_items(self.db, permit)
            if kind == "pre_issue"
            else evaluation.closure_items(self.db, permit)
        )
        answers = [{"code": c.value, "answer": "yes"} for c in items]
        if answers:
            permits.put_checklist(
                self.db,
                self.p(key),
                permit.id,
                ChecklistInput.model_validate({"kind": kind, "answers": answers}),
            )

    def ensure_docs(self, permit: Permit, key: str) -> None:
        from app.schemas.permits import PermitDocumentInput
        from app.services.ptw import evaluation, permits
        from app.services.ptw import facts as facts_mod

        f = facts_mod.compute(self.db, permit)
        tail = permit.permit_no.rsplit("-", 1)[1]
        for code in evaluation.missing_documents(self.db, permit, f):
            if code == "isolation_certificate":
                continue
            ref = {
                "method_statement": "MS",
                "risk_assessment": "RA",
                "lift_plan": "LP",
                "critical_lift_plan": "CLP",
                "rescue_plan": "RP",
                "excavation_plan": "EXP",
                "utility_drawing": "UD",
                "radiation_protection_plan": "RPP",
                "nrrc_licence": "NRRC",
            }.get(code, "DOC")
            permits.add_document(
                self.db,
                self.p(key),
                permit.id,
                PermitDocumentInput.model_validate(
                    {
                        "doc_type": code,
                        "ref": f"{ref}-TEST-{tail}",
                        "revision": "A",
                        "approved_by_text": "Contractor engineer (fake)",
                    }
                ),
            )

    def approve_now(
        self,
        permit: Permit,
        receiver: str,
        area: str,
        issuer: str,
        hse: str | None,
        t: datetime,
        wap_no: str | None = None,
    ) -> None:
        """Re-review (if a change sent the permit back to Requested) and approve at `t`."""
        from app.schemas.permits import (
            ApproveInput,
            AreaReviewInput,
            HseReviewInput,
        )
        from app.services.ptw import lifecycle

        set_now(t)
        self.db.refresh(permit)
        if permit.status.value == "requested":
            lifecycle.area_review(
                self.db,
                self.p(area),
                permit.id,
                AreaReviewInput(
                    area_conditions_known=True, simops_reviewed=True, wap_no_confirmed=wap_no
                ),
            )
        if hse and permit.high_risk and not (permit.hse_review or {}).get("decision"):
            lifecycle.hse_review(
                self.db, self.p(hse), permit.id, HseReviewInput(decision="accepted")
            )
        self.checklist(permit, receiver)
        lifecycle.approve(self.db, self.p(issuer), permit.id, ApproveInput())

    def to_approved(
        self,
        permit: Permit,
        receiver: str,
        area: str,
        issuer: str,
        hse: str | None,
        t_req: datetime,
        t_area: datetime,
        t_hse: datetime | None,
        t_appr: datetime,
        wap_no: str | None = None,
    ) -> None:
        from app.schemas.permits import (
            ApproveInput,
            AreaReviewInput,
            HseReviewInput,
            RequestInput,
        )
        from app.services.ptw import lifecycle

        set_now(t_req)
        self.ensure_docs(permit, receiver)
        lifecycle.request(self.db, self.p(receiver), permit.id, RequestInput())
        set_now(t_area)
        lifecycle.area_review(
            self.db,
            self.p(area),
            permit.id,
            AreaReviewInput(
                area_conditions_known=True, simops_reviewed=True, wap_no_confirmed=wap_no
            ),
        )
        if hse and permit.high_risk:
            assert t_hse is not None
            set_now(t_hse)
            lifecycle.hse_review(
                self.db, self.p(hse), permit.id, HseReviewInput(decision="accepted")
            )
        set_now(t_appr)
        self.checklist(permit, receiver)
        lifecycle.approve(self.db, self.p(issuer), permit.id, ApproveInput())

    def issue(
        self,
        permit: Permit,
        issuer: str,
        receiver: str,
        t: datetime,
        wind: dict[str, Any] | None = None,
    ) -> None:
        from app.schemas.permits import IssueInput
        from app.services.ptw import lifecycle

        set_now(t)
        body: dict[str, Any] = {
            "site_visit_confirmed": True,
            "receiver_cosign": self.cosign(receiver),
        }
        if wind:
            body["wind_reading"] = wind
        lifecycle.issue(self.db, self.p(issuer), permit.id, IssueInput.model_validate(body))

    def crew_present(self, permit: Permit) -> list[dict[str, Any]]:
        from app.core.ptw_enums import CrewLineStatus
        from app.models import PermitCrew

        ids = list(
            dict.fromkeys(
                self.db.scalars(
                    select(PermitCrew.worker_id).where(
                        PermitCrew.permit_id == permit.id,
                        PermitCrew.status == CrewLineStatus.listed,
                    )
                )
            )
        )
        return [{"worker_id": str(i), "briefed": True} for i in ids]

    def start(
        self,
        permit: Permit,
        receiver: str,
        t: datetime,
        ambient: str | None = None,
        wind: dict[str, Any] | None = None,
    ) -> None:
        from app.schemas.permits import StartInput
        from app.services.ptw import lifecycle

        set_now(t)
        body: dict[str, Any] = {"crew_present": self.crew_present(permit)}
        if ambient:
            body["ambient_temp_c"] = ambient
        if wind:
            body["wind_reading"] = wind
        lifecycle.start(self.db, self.p(receiver), permit.id, StartInput.model_validate(body))

    def end_shift(self, permit: Permit, receiver: str, t: datetime) -> None:
        from app.schemas.permits import EndShiftInput
        from app.services.ptw import lifecycle

        set_now(t)
        lifecycle.end_shift(self.db, self.p(receiver), permit.id, EndShiftInput())

    def revalidate(
        self,
        permit: Permit,
        issuer: str,
        receiver: str,
        t: datetime,
        ambient: str | None = None,
        wind: dict[str, Any] | None = None,
    ) -> None:
        from app.schemas.permits import RevalidateInput
        from app.services.ptw import lifecycle

        set_now(t)
        self.checklist(permit, receiver)
        body: dict[str, Any] = {
            "crew_present": self.crew_present(permit),
            "site_visit_confirmed": True,
            "receiver_cosign": self.cosign(receiver),
            "checklist_reconfirmed": True,
        }
        if ambient:
            body["ambient_temp_c"] = ambient
        if wind:
            body["wind_reading"] = wind
        lifecycle.revalidate(
            self.db, self.p(issuer), permit.id, RevalidateInput.model_validate(body)
        )

    def gas(
        self,
        permit: Permit,
        recorder: str,
        t: datetime,
        test_type: str,
        readings: list[dict[str, Any]],
        detector: str = "GD-ANIA-003",
        apt: str = "APT-ANIA-EXP-0011",
        temp: str | None = None,
    ) -> Any:
        from app.schemas.gas import GasTestCreate
        from app.services.ptw import gas

        set_now(t)
        body: dict[str, Any] = {
            "test_type": test_type,
            "tested_at": t.isoformat(),
            "tester_appointment_id": str(self.ctx.apts[apt].id),
            "detector_id": str(self.ctx.detectors[detector].id),
            "readings": readings,
            "tester_signature_png_base64": PNG,
        }
        if temp:
            body["internal_temp_c"] = temp
        return gas.record(self.db, self.p(recorder), permit.id, GasTestCreate.model_validate(body))


def rd(point: str, o2: str, lel: str, h2s: str, co: str) -> dict[str, Any]:
    return {"point": point, "o2_pct": o2, "lel_pct": lel, "h2s_ppm": h2s, "co_ppm": co}


# ---- ANIA-EXP --------------------------------------------------------------------------------------


def p0413(n: N) -> None:
    """CSE manhole MH-07 — Active since 07:55 with 2 entrants inside (A.7)."""
    from app.schemas.permits import EntryLogInput, PauseEndInput, PauseStartInput
    from app.services.ptw import fieldwork

    c = n.ctx
    set_now(at(2026, 10, 6, 6, 0))
    bulk = n.bulk_worker("ANIA-EXP", "RAWABI", 1, site="S-LAND", zone="Z-MSCP")
    body = {
        "site_id": str(c.site("ANIA-EXP", "S-LAND").id),
        "zone_ids": [str(c.zones["Z-MSCP"].id)],
        "location_desc": "Manhole MH-07, MSCP service road",
        "grid_x_m": "180.0",
        "grid_y_m": "60.0",
        "level_code": "MH07",
        "elevation_m": "-3.20",
        "engagement_id": str(c.eng("ANIA-EXP", "RAWABI").id),
        "work_types": [T.confined_space.value],
        "primary_type": T.confined_space.value,
        "title": "Manhole MH-07 inspection and pipe repair",
        "scope_en": "Inspect manhole MH-07 and repair the cracked inlet pipe section.",
        "valid_from_at": at(2026, 10, 6, 7, 0).isoformat(),
        "valid_to_at": at(2026, 10, 6, 19, 0).isoformat(),
        "windows": win("07:00", "19:00"),
        "receiver_user_id": str(c.uid("faris.anazi")),
        "area_authority_user_id": str(c.uid("fahad.mutairi")),
        "issuer_user_id": str(c.uid("khalid.otaibi")),
        "hse_reviewer_user_id": str(c.uid("noura.qahtani")),
        "supervisor_worker_id": str(n.w("WKR-000021")),
        "emergency_info": EMERGENCY,
        "crew": [
            {"worker_id": str(n.w("WKR-000021")), "crew_role": "supervisor"},
            {
                "worker_id": str(n.w("WKR-000021")),
                "crew_role": "rescue_lead",
                "appointment_id": str(c.apts["APT-ANIA-EXP-0012"].id),
            },
            {"worker_id": str(n.w("WKR-000017")), "crew_role": "standby_person"},
            {"worker_id": str(n.w("WKR-000016")), "crew_role": "entrant"},
            {"worker_id": str(bulk[0]), "crew_role": "entrant"},
            {
                "worker_id": str(n.w("WKR-000018")),
                "crew_role": "gas_tester",
                "appointment_id": str(c.apts["APT-ANIA-EXP-0011"].id),
            },
        ],
        "documents": [
            {
                "doc_type": "rescue_plan",
                "ref": "RP-MSCP-02",
                "revision": "B",
                "approved_by_text": "RAWABI HSE Manager (fake)",
            }
        ],
        "sections": [
            {
                "work_type": "confined_space",
                "space_id_desc": "Manhole MH-07 (sewer, 3.2 m deep)",
                "space_hazards": ["toxic", "oxygen_deficiency"],
                "ventilation": "forced_supply",
                "continuous_monitor_detector_id": str(c.detectors["GD-ANIA-003"].id),
                "rescue_method": "non_entry_tripod_winch",
                "rescue_response_minutes": 4,
                "rescue_equipment_checked": True,
                "communication_method": "voice_visual",
            }
        ],
        "jsa_template_id": str(c.templates["JSA-T-ANIA-EXP-0003"].id),
    }
    permit = n.create("faris.anazi", "ANIA-EXP", "PTW-ANIA-EXP-2026-0413", body)
    set_now(at(2026, 10, 6, 6, 5))
    n.jsa(permit, "faris.anazi", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "faris.anazi",
        "fahad.mutairi",
        "khalid.otaibi",
        "noura.qahtani",
        at(2026, 10, 6, 6, 10),
        at(2026, 10, 6, 6, 20),
        at(2026, 10, 6, 6, 30),
        at(2026, 10, 6, 6, 45),
    )
    n.gas(
        permit,
        "faris.anazi",
        at(2026, 10, 6, 7, 40),
        "pre_entry",
        [
            rd("top", "20.9", "0", "0", "3"),
            rd("middle", "20.8", "0", "0", "4"),
            rd("bottom", "20.6", "2", "0", "6"),
        ],
        temp="31.0",
    )
    n.issue(permit, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 7, 50))
    n.start(permit, "faris.anazi", at(2026, 10, 6, 7, 55), ambient="31.0")
    entrants = [n.w("WKR-000016"), bulk[0]]
    for wid in entrants:
        set_now(at(2026, 10, 6, 8, 0))
        fieldwork.record_entry(
            n.db,
            n.p("faris.anazi"),
            permit.id,
            EntryLogInput.model_validate(
                {"worker_id": str(wid), "direction": "in", "at": at(2026, 10, 6, 8, 0).isoformat()}
            ),
        )
    n.gas(
        permit,
        "faris.anazi",
        at(2026, 10, 6, 8, 38),
        "periodic",
        [rd("at_work_point", "20.8", "1", "0", "5")],
        temp="32.0",
    )
    for wid in entrants:
        set_now(at(2026, 10, 6, 9, 14))
        fieldwork.record_entry(
            n.db,
            n.p("faris.anazi"),
            permit.id,
            EntryLogInput.model_validate(
                {
                    "worker_id": str(wid),
                    "direction": "out",
                    "at": at(2026, 10, 6, 9, 14).isoformat(),
                }
            ),
        )
    set_now(at(2026, 10, 6, 9, 15))
    fieldwork.start_pause(n.db, n.p("faris.anazi"), permit.id, PauseStartInput(reason="break"))
    n.gas(
        permit,
        "faris.anazi",
        at(2026, 10, 6, 9, 48),
        "post_break",
        [
            rd("top", "20.9", "0", "0", "3"),
            rd("middle", "20.8", "0", "0", "4"),
            rd("bottom", "20.7", "1", "0", "5"),
        ],
        temp="32.5",
    )
    set_now(at(2026, 10, 6, 9, 50))
    fieldwork.end_pause(n.db, n.p("faris.anazi"), permit.id, PauseEndInput())
    for wid in entrants:
        set_now(at(2026, 10, 6, 9, 52))
        fieldwork.record_entry(
            n.db,
            n.p("faris.anazi"),
            permit.id,
            EntryLogInput.model_validate(
                {"worker_id": str(wid), "direction": "in", "at": at(2026, 10, 6, 9, 52).isoformat()}
            ),
        )


def tpl(n: N, no: str) -> str:
    return str(n.ctx.templates[no].id)


def p0412(n: N) -> None:
    """Hot work Pier B — Active since 07:10 (A.7, Y4, Y8)."""
    c = n.ctx
    set_now(at(2026, 10, 6, 5, 30))
    helper = n.bulk_worker("ANIA-EXP", "NAJD", 1, site="S-LAND", zone="Z-PIERB")[0]
    b = n.base(
        "ANIA-EXP",
        "S-LAND",
        ["Z-PIERB"],
        "Pier B steel connections, gridline B4",
        "120.0",
        "45.0",
        "L2",
        "12.00",
        "NAJD",
        [T.hot_work.value],
        T.hot_work.value,
        "Welding of steel connections",
        at(2026, 10, 6, 7),
        at(2026, 10, 6, 19),
        win("07:00", "19:00"),
        "ramesh.kumar",
        "fahad.mutairi",
        "khalid.otaibi",
        None,
        str(helper),
    )
    b["crew"] = [
        {"worker_id": str(helper), "crew_role": "supervisor"},
        {"worker_id": str(n.w("WKR-000014")), "crew_role": "hot_work_operative"},
        {"worker_id": str(n.w("WKR-000015")), "crew_role": "fire_watch"},
    ]
    b["sections"] = [
        {
            "work_type": "hot_work",
            "hot_work_kind": ["arc_welding"],
            "combustibles_cleared_radius_m": "11.0",
            "fire_extinguishers": [{"type": "dcp_abc_6kg", "count": 2, "distance_m": "5.0"}],
            "fire_blanket": True,
            "work_height_above_floor_m": "0.00",
            "cylinders": "none",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-ANIA-EXP-0002")
    permit = n.create("ramesh.kumar", "ANIA-EXP", "PTW-ANIA-EXP-2026-0412", b)
    n.jsa(permit, "ramesh.kumar", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "ramesh.kumar",
        "fahad.mutairi",
        "khalid.otaibi",
        None,
        at(2026, 10, 6, 5, 40),
        at(2026, 10, 6, 6, 0),
        None,
        at(2026, 10, 6, 6, 30),
    )
    n.issue(permit, "khalid.otaibi", "ramesh.kumar", at(2026, 10, 6, 7, 5))
    n.start(permit, "ramesh.kumar", at(2026, 10, 6, 7, 10), ambient="30.0")
    _ = c


def p0405(n: N) -> None:
    """Electrical MCC-3 with ISO-ANIA-EXP-2026-0061 and personal locks (A.7)."""
    from app.schemas.isolations import (
        IsolationCreate,
        IsolationTransition,
        PersonalLockApply,
        PersonalLockRemove,
        PointApplyInput,
        PointVerifyInput,
    )
    from app.services.ptw import isolations

    c = n.ctx
    set_now(at(2026, 10, 4, 13, 0))
    iso = isolations.create(
        n.db,
        n.p("nasser.shahrani"),
        c.pid("ANIA-EXP"),
        IsolationCreate.model_validate(
            {
                "equipment_desc": "MCC-3 (Pier B plant room)",
                "energy_types": ["electrical"],
                "hv": False,
                "isolation_authority_user_id": str(c.uid("nasser.shahrani")),
                "lockbox_id": str(c.locks["LB-ANIA-012"].id),
                "points": [
                    {
                        "energy_type": "electrical",
                        "device_tag": "Q12",
                        "location": "Main LV board, Q12 feeder breaker",
                        "method": "breaker_racked_out",
                    },
                    {
                        "energy_type": "electrical",
                        "device_tag": "MCC-3-INC",
                        "location": "MCC-3 incomer isolator",
                        "method": "isolator_open_locked",
                    },
                ],
            }
        ),
    )
    from app.models import IsolationCertificate

    cert = n.db.get(IsolationCertificate, iso.id)
    assert cert is not None
    cert.seq = 61
    cert.iso_no = "ISO-ANIA-EXP-2026-0061"
    n.db.flush()
    elec = n.bulk_worker(
        "ANIA-EXP", "RAWABI", 3, site="S-LAND", zone="Z-PIERB", until=at(2026, 10, 11, 17)
    )
    b = n.base(
        "ANIA-EXP",
        "S-LAND",
        ["Z-PIERB"],
        "Pier B plant room, MCC-3",
        "95.0",
        "20.0",
        "PR",
        "0.00",
        "RAWABI",
        [T.electrical_isolation.value],
        T.electrical_isolation.value,
        "MCC-3 cable termination",
        at(2026, 10, 5, 7),
        at(2026, 10, 11, 19),
        win("07:00", "17:00"),
        "faris.anazi",
        "fahad.mutairi",
        "khalid.otaibi",
        None,
        str(elec[0]),
    )
    b["crew"] = [
        {"worker_id": str(elec[0]), "crew_role": "supervisor"},
        *[{"worker_id": str(w), "crew_role": "electrician"} for w in elec],
    ]
    b["isolation_cert_ids"] = [str(cert.id)]
    b["sections"] = [
        {
            "work_type": "electrical_isolation",
            "system_voltage_v": 400,
            "work_condition": "electrically_safe",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-ANIA-EXP-0006")
    permit = n.create("faris.anazi", "ANIA-EXP", "PTW-ANIA-EXP-2026-0405", b)
    n.jsa(permit, "faris.anazi", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "faris.anazi",
        "fahad.mutairi",
        "khalid.otaibi",
        None,
        at(2026, 10, 4, 14, 10),
        at(2026, 10, 4, 15, 0),
        None,
        at(2026, 10, 4, 16, 0),
    )
    pts = isolations.points(n.db, cert)
    for pt, lock, tag, t in (
        (pts[0], "L-ANIA-0231", "DT-0231", at(2026, 10, 5, 7, 40)),
        (pts[1], "L-ANIA-0232", "DT-0232", at(2026, 10, 5, 7, 50)),
    ):
        set_now(t)
        isolations.apply_point(
            n.db,
            n.p("nasser.shahrani"),
            cert.id,
            pt.id,
            PointApplyInput.model_validate(
                {
                    "isolation_lock_id": str(c.locks[lock].id),
                    "tag_no": tag,
                    "applied_at": t.isoformat(),
                }
            ),
        )
    set_now(at(2026, 10, 5, 7, 55))
    isolations.transition(
        n.db, n.p("nasser.shahrani"), cert.id, IsolationTransition(to_status="isolated")
    )
    for pt in pts:
        set_now(at(2026, 10, 5, 8, 20))
        isolations.verify_point(
            n.db,
            n.p("faris.anazi"),
            cert.id,
            pt.id,
            PointVerifyInput.model_validate(
                {
                    "verified_at": at(2026, 10, 5, 8, 20).isoformat(),
                    "verification_method": "test_for_dead",
                }
            ),
        )
    isolations.transition(
        n.db, n.p("nasser.shahrani"), cert.id, IsolationTransition(to_status="verified")
    )
    n.sections(
        permit,
        "faris.anazi",
        [
            {
                "work_type": "electrical_isolation",
                "system_voltage_v": 400,
                "work_condition": "electrically_safe",
                "test_for_dead": {
                    "done_at": at(2026, 10, 5, 8, 20).isoformat(),
                    "by_user_id": str(c.uid("faris.anazi")),
                    "instrument_tag": "VT-TEST-01",
                    "proving_unit_used": True,
                    "live_dead_live": True,
                },
            }
        ],
    )
    n.approve_now(
        permit, "faris.anazi", "fahad.mutairi", "khalid.otaibi", None, at(2026, 10, 5, 8, 27)
    )
    n.issue(permit, "khalid.otaibi", "faris.anazi", at(2026, 10, 5, 8, 30))
    events = []
    for w, lk in zip(elec, ("P-ANIA-1101", "P-ANIA-1102", "P-ANIA-1103"), strict=True):
        set_now(at(2026, 10, 5, 8, 32))
        events.append(
            isolations.apply_personal(
                n.db,
                n.p("faris.anazi"),
                cert.id,
                PersonalLockApply.model_validate(
                    {
                        "lock_id": str(c.locks[lk].id),
                        "worker_id": str(w),
                        "applied_at": at(2026, 10, 5, 8, 32).isoformat(),
                        "permit_id": str(permit.id),
                    }
                ),
            )
        )
    n.start(permit, "faris.anazi", at(2026, 10, 5, 8, 35), ambient="29.0")
    for ev in events:
        set_now(at(2026, 10, 5, 16, 50))
        isolations.remove_personal(
            n.db,
            n.p("faris.anazi"),
            ev.id,
            PersonalLockRemove.model_validate({"removed_at": at(2026, 10, 5, 16, 50).isoformat()}),
        )
    n.end_shift(permit, "faris.anazi", at(2026, 10, 5, 16, 55))
    for w, lk in zip(elec, ("P-ANIA-1101", "P-ANIA-1102", "P-ANIA-1103"), strict=True):
        set_now(at(2026, 10, 6, 7, 2))
        isolations.apply_personal(
            n.db,
            n.p("faris.anazi"),
            cert.id,
            PersonalLockApply.model_validate(
                {
                    "lock_id": str(c.locks[lk].id),
                    "worker_id": str(w),
                    "applied_at": at(2026, 10, 6, 7, 2).isoformat(),
                    "permit_id": str(permit.id),
                }
            ),
        )
    n.revalidate(permit, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 7, 5), ambient="29.0")


def p0408(n: N) -> None:
    """Excavation + airside, Z-TWB — Suspended shift_end since 2026-10-06 04:52 (Y6 b)."""
    from app.schemas.permits import ExcavationInspectionInput
    from app.services.ptw import fieldwork

    c = n.ctx
    set_now(at(2026, 10, 4, 10, 0))
    bulk = n.wap_crew("WAP-ANIA-EXP-2026-0031", 3)
    tariq = str(n.w("WKR-000013"))
    b = n.base(
        "ANIA-EXP",
        "S-AIR",
        ["Z-TWB"],
        "Taxiway B shoulder, AGL cable duct",
        "410.0",
        "95.0",
        None,
        None,
        "GULFPAVE",
        [T.excavation.value, T.airside_works.value],
        T.excavation.value,
        "AGL cable duct, hand dig",
        at(2026, 10, 4, 23),
        at(2026, 10, 10, 5),
        win("23:00", "05:00"),
        "sanjay.verma",
        "omar.siddiqui",
        "khalid.otaibi",
        "noura.qahtani",
        tariq,
    )
    b["crew"] = [
        {"worker_id": tariq, "crew_role": "supervisor"},
        {
            "worker_id": tariq,
            "crew_role": "competent_person",
            "appointment_id": str(c.apts["APT-ANIA-EXP-0009"].id),
        },
        {"worker_id": tariq, "crew_role": "escort"},
        {"worker_id": str(n.w("WKR-000002")), "crew_role": "driver"},
        {"worker_id": str(n.w("WKR-000004")), "crew_role": "worker", "escort_worker_id": tariq},
        *[{"worker_id": str(w), "crew_role": "worker"} for w in bulk],
    ]
    b["linked_wap_ids"] = [n.wap_id("WAP-ANIA-EXP-2026-0031")]
    b["sections"] = [
        {
            "work_type": "excavation",
            "max_depth_m": "1.30",
            "method": "hand_dig",
            "soil_type": "type_c",
            "protective_system": "sloping",
            "slope_ratio_h_v": "1.50",
            "utility_clearance_ref": "AOP-UTIL-TEST-0419",
            "spoil_setback_m": "0.80",
            "egress": "ladder",
            "egress_travel_m": "5.0",
            "edge_barriers": True,
            "night_lighting": True,
        },
        {
            "work_type": "airside_works",
            "wap_id": n.wap_id("WAP-ANIA-EXP-2026-0031"),
            "fod_control_plan": True,
            "aircraft_proximity": "no_stand_in_zone",
        },
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-ANIA-EXP-0010")
    permit = n.create("sanjay.verma", "ANIA-EXP", "PTW-ANIA-EXP-2026-0408", b)
    n.jsa(permit, "sanjay.verma", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "sanjay.verma",
        "omar.siddiqui",
        "khalid.otaibi",
        "noura.qahtani",
        at(2026, 10, 4, 10, 10),
        at(2026, 10, 4, 11, 0),
        at(2026, 10, 4, 12, 0),
        at(2026, 10, 4, 14, 0),
        wap_no="WAP-ANIA-EXP-2026-0031",
    )

    def inspect(t: datetime) -> None:
        set_now(t)
        fieldwork.record_excavation_inspection(
            n.db,
            n.p("sanjay.verma"),
            permit.id,
            ExcavationInspectionInput.model_validate(
                {
                    "inspected_at": t.isoformat(),
                    "appointment_id": str(c.apts["APT-ANIA-EXP-0009"].id),
                    "result": "safe",
                }
            ),
        )

    inspect(at(2026, 10, 4, 22, 55))
    n.issue(permit, "khalid.otaibi", "sanjay.verma", at(2026, 10, 4, 23, 0))
    n.start(permit, "sanjay.verma", at(2026, 10, 4, 23, 5), ambient="29.0")
    n.end_shift(permit, "sanjay.verma", at(2026, 10, 5, 4, 50))
    inspect(at(2026, 10, 5, 23, 0))
    n.revalidate(permit, "khalid.otaibi", "sanjay.verma", at(2026, 10, 5, 23, 5), ambient="29.0")
    n.end_shift(permit, "sanjay.verma", at(2026, 10, 6, 4, 52))


def p0410(n: N) -> None:
    """Critical lift + airside, Z-APR-21 stand 22 — Approved 09:30 (A.7, Y7 b)."""
    c = n.ctx
    set_now(at(2026, 10, 5, 15, 0))
    riggers = n.wap_crew("WAP-ANIA-EXP-2026-0033", 2)
    mahmoud = str(n.w("WKR-000005"))
    from app.models import ObstacleClearance, Vehicle

    veh = n.db.scalar(select(Vehicle.id).where(Vehicle.vehicle_no == "VEH-0003"))
    obs = n.db.scalar(
        select(ObstacleClearance.id).where(ObstacleClearance.obs_no == "OBS-ANIA-EXP-2026-0004")
    )
    b = n.base(
        "ANIA-EXP",
        "S-AIR",
        ["Z-APR-21"],
        "Apron 2 stand 22, AGL transformer pad",
        "520.0",
        "140.0",
        None,
        None,
        "RAWABI",
        [T.lifting.value, T.airside_works.value],
        T.lifting.value,
        "AGL transformer set-down",
        at(2026, 10, 6, 13),
        at(2026, 10, 6, 16),
        win("13:00", "16:00"),
        "faris.anazi",
        "omar.siddiqui",
        "khalid.otaibi",
        "noura.qahtani",
        mahmoud,
    )
    b["crew"] = [
        {"worker_id": mahmoud, "crew_role": "supervisor"},
        {
            "worker_id": mahmoud,
            "crew_role": "lift_supervisor",
            "appointment_id": str(c.apts["APT-ANIA-EXP-0008"].id),
        },
        {"worker_id": str(n.w("WKR-000019")), "crew_role": "crane_operator"},
        *[{"worker_id": str(w), "crew_role": "rigger"} for w in riggers],
    ]
    b["linked_wap_ids"] = [n.wap_id("WAP-ANIA-EXP-2026-0033")]
    b["linked_obs_ids"] = [str(obs)]
    b["documents"] = [
        {
            "doc_type": "critical_lift_plan",
            "ref": "CLP-ANIA-0007",
            "revision": "A",
            "approved_by_text": "Saad Al-Dosari (APT-ANIA-EXP-0007)",
        }
    ]
    b["sections"] = [
        {
            "work_type": "airside_works",
            "wap_id": n.wap_id("WAP-ANIA-EXP-2026-0033"),
            "fod_control_plan": True,
            "aircraft_proximity": "stand_closed_notam",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-ANIA-EXP-0011")
    permit = n.create("faris.anazi", "ANIA-EXP", "PTW-ANIA-EXP-2026-0410", b)
    eq = n.add_equipment(
        permit, "faris.anazi", {"vehicle_id": str(veh), "use": "lifting_appliance"}
    )
    n.sections(
        permit,
        "faris.anazi",
        [
            {
                "work_type": "lifting",
                "appliance_equipment_ids": [str(eq)],
                "load_desc": "AGL transformer unit TX-22",
                "load_weight_t": "6.800",
                "rigging_weight_t": "0.350",
                "radius_m": "14.00",
                "rated_capacity_t": "12.400",
                "exclusion_radius_m": "6.0",
                "landing_grid_x_m": "520.0",
                "landing_grid_y_m": "140.0",
                "appliance_grid_x_m": "512.0",
                "appliance_grid_y_m": "134.0",
                "slew_radius_m": "14.0",
                "ground_bearing_checked": True,
            }
        ],
    )
    n.jsa(permit, "faris.anazi", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "faris.anazi",
        "omar.siddiqui",
        "khalid.otaibi",
        "noura.qahtani",
        at(2026, 10, 5, 15, 10),
        at(2026, 10, 5, 16, 0),
        at(2026, 10, 6, 8, 0),
        at(2026, 10, 6, 9, 30),
        wap_no="WAP-ANIA-EXP-2026-0033",
    )


def p0399(n: N) -> None:
    """Radiography Z-LAY1 — Closed 2026-10-05 05:10 (A.7, Y9)."""
    from app.schemas.permits import BarrierSurveyInput, SourceReturnInput
    from app.services.ptw import fieldwork

    set_now(at(2026, 10, 4, 9, 0))
    asst = n.bulk_worker("ANIA-EXP", "NAJD", 1, site="S-LAND", zone="Z-LAY1")[0]
    vinod = str(n.w("WKR-000020"))
    c = n.ctx
    b = n.base(
        "ANIA-EXP",
        "S-LAND",
        ["Z-LAY1"],
        "Laydown 1 pipe rack, weld joints W-14..W-22",
        "300.0",
        "200.0",
        None,
        None,
        "NAJD",
        [T.radiography.value],
        T.radiography.value,
        "Pipe-weld radiography",
        at(2026, 10, 4, 22),
        at(2026, 10, 5, 5),
        win("22:00", "05:00"),
        "ramesh.kumar",
        "fahad.mutairi",
        "khalid.otaibi",
        "noura.qahtani",
        vinod,
    )
    b["crew"] = [
        {"worker_id": vinod, "crew_role": "supervisor"},
        {"worker_id": vinod, "crew_role": "radiographer"},
        {
            "worker_id": vinod,
            "crew_role": "rpo",
            "appointment_id": str(c.apts["APT-ANIA-EXP-0010"].id),
        },
        {"worker_id": str(asst), "crew_role": "worker"},
    ]
    b["documents"] = [
        {
            "doc_type": "nrrc_licence",
            "ref": "NRRC-TEST-RL-0042",
            "revision": "1",
            "valid_until": "2027-03-31",
        }
    ]
    b["sections"] = [
        {
            "work_type": "radiography",
            "source_type": "ir_192",
            "activity_gbq": "1110.0",
            "collimator_transmission": "0.0625",
            "planned_barrier_m": "40.0",
            "nrrc_licence_no": "NRRC-TEST-RL-0042",
            "licence_valid_until": "2027-03-31",
            "dosimetry_confirmed": True,
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-ANIA-EXP-0008")
    permit = n.create("ramesh.kumar", "ANIA-EXP", "PTW-ANIA-EXP-2026-0399", b)
    n.jsa(permit, "ramesh.kumar", "khalid.otaibi", "noura.qahtani")
    n.to_approved(
        permit,
        "ramesh.kumar",
        "fahad.mutairi",
        "khalid.otaibi",
        "noura.qahtani",
        at(2026, 10, 4, 9, 10),
        at(2026, 10, 4, 10, 0),
        at(2026, 10, 4, 11, 0),
        at(2026, 10, 4, 12, 0),
    )
    set_now(at(2026, 10, 4, 21, 55))
    fieldwork.record_barrier_survey(
        n.db,
        n.p("ramesh.kumar"),
        permit.id,
        BarrierSurveyInput.model_validate(
            {
                "measured_at": at(2026, 10, 4, 21, 55).isoformat(),
                "max_usv_h": "5.8",
                "meter_tag": "SM-TEST-07",
            }
        ),
    )
    n.issue(permit, "khalid.otaibi", "ramesh.kumar", at(2026, 10, 4, 22, 0))
    n.start(permit, "ramesh.kumar", at(2026, 10, 4, 22, 5), ambient="28.0")
    set_now(at(2026, 10, 5, 4, 40))
    fieldwork.record_source_return(
        n.db,
        n.p("ramesh.kumar"),
        permit.id,
        SourceReturnInput.model_validate(
            {
                "at": at(2026, 10, 5, 4, 40).isoformat(),
                "survey_usv_h": "0.2",
                "background_usv_h": "0.15",
            }
        ),
    )
    n.close(permit, "ramesh.kumar", "khalid.otaibi", at(2026, 10, 5, 5, 0), at(2026, 10, 5, 5, 10))


# ---- RBT-52 ----------------------------------------------------------------------------------------


def p0279(n: N) -> None:
    """Electrical DB-L30-01 with ISO-RBT-52-2026-0033 — Closed 2026-10-02 16:30 (A.7)."""
    from app.schemas.isolations import (
        IsolationCreate,
        IsolationTransition,
        PointApplyInput,
        PointRemoveInput,
        PointVerifyInput,
    )
    from app.services.ptw import isolations

    c = n.ctx
    set_now(at(2026, 9, 28, 9, 0))
    iso = isolations.create(
        n.db,
        n.p("ibrahim.saleh"),
        c.pid("RBT-52"),
        IsolationCreate.model_validate(
            {
                "equipment_desc": "DB-L30-01 incomer (core L30)",
                "energy_types": ["electrical"],
                "isolation_authority_user_id": str(c.uid("ibrahim.saleh")),
                "lockbox_id": str(c.locks["LB-RBT-003"].id),
                "points": [
                    {
                        "energy_type": "electrical",
                        "device_tag": "DB-L30-01-INC",
                        "location": "Riser L30, DB-L30-01 incomer",
                        "method": "isolator_open_locked",
                    }
                ],
            }
        ),
    )
    from app.models import IsolationCertificate

    cert = n.db.get(IsolationCertificate, iso.id)
    assert cert is not None
    cert.seq = 33
    cert.iso_no = "ISO-RBT-52-2026-0033"
    n.db.flush()
    bulk = n.bulk_worker(
        "RBT-52", "QIMMA", 1, site="S-TWR", zone="Z-CORE", until=at(2026, 10, 2, 17)
    )
    ramon = str(n.w("WKR-000103"))
    b = n.base(
        "RBT-52",
        "S-TWR",
        ["Z-CORE"],
        "Core L30 riser, DB-L30-01",
        "30.0",
        "12.0",
        "L30",
        "120.00",
        "QIMMA",
        [T.electrical_isolation.value],
        T.electrical_isolation.value,
        "DB-L30-01 replacement",
        at(2026, 9, 29, 7),
        at(2026, 10, 2, 17),
        win("07:00", "17:00"),
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        None,
        ramon,
    )
    b["crew"] = [
        {"worker_id": ramon, "crew_role": "supervisor"},
        {"worker_id": ramon, "crew_role": "electrician"},
        {"worker_id": str(bulk[0]), "crew_role": "electrician"},
    ]
    b["isolation_cert_ids"] = [str(cert.id)]
    b["sections"] = [
        {
            "work_type": "electrical_isolation",
            "system_voltage_v": 400,
            "work_condition": "electrically_safe",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-RBT-52-0005")
    permit = n.create("joseph.mathew", "RBT-52", "PTW-RBT-52-2026-0279", b)
    n.jsa(permit, "joseph.mathew", "majed.shammari", "lina.haddad")
    n.to_approved(
        permit,
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        None,
        at(2026, 9, 28, 10, 0),
        at(2026, 9, 28, 11, 0),
        None,
        at(2026, 9, 28, 14, 0),
    )
    pt = isolations.points(n.db, cert)[0]
    set_now(at(2026, 9, 29, 6, 30))
    isolations.apply_point(
        n.db,
        n.p("ibrahim.saleh"),
        cert.id,
        pt.id,
        PointApplyInput.model_validate(
            {
                "isolation_lock_id": str(c.locks["L-RBT-0104"].id),
                "tag_no": "DT-RBT-0104",
                "applied_at": at(2026, 9, 29, 6, 30).isoformat(),
            }
        ),
    )
    isolations.transition(
        n.db, n.p("ibrahim.saleh"), cert.id, IsolationTransition(to_status="isolated")
    )
    set_now(at(2026, 9, 29, 6, 45))
    isolations.verify_point(
        n.db,
        n.p("joseph.mathew"),
        cert.id,
        pt.id,
        PointVerifyInput.model_validate(
            {
                "verified_at": at(2026, 9, 29, 6, 45).isoformat(),
                "verification_method": "test_for_dead",
            }
        ),
    )
    isolations.transition(
        n.db, n.p("ibrahim.saleh"), cert.id, IsolationTransition(to_status="verified")
    )
    n.sections(
        permit,
        "joseph.mathew",
        [
            {
                "work_type": "electrical_isolation",
                "system_voltage_v": 400,
                "work_condition": "electrically_safe",
                "test_for_dead": {
                    "done_at": at(2026, 9, 29, 6, 45).isoformat(),
                    "by_user_id": str(c.uid("joseph.mathew")),
                    "instrument_tag": "VT-TEST-02",
                    "proving_unit_used": True,
                    "live_dead_live": True,
                },
            }
        ],
    )
    n.approve_now(
        permit, "joseph.mathew", "ibrahim.saleh", "majed.shammari", None, at(2026, 9, 29, 6, 55)
    )
    n.issue(permit, "majed.shammari", "joseph.mathew", at(2026, 9, 29, 7, 0))
    from app.schemas.isolations import PersonalLockApply, PersonalLockRemove

    lock_of: dict[str, str] = {}

    def locks_on(t: datetime) -> list[Any]:
        evs = []
        for cp in n.crew_present(permit):
            set_now(t)
            ln = lock_of.setdefault(cp["worker_id"], f"P-RBT-{201 + len(lock_of):04d}")
            evs.append(
                isolations.apply_personal(
                    n.db,
                    n.p("joseph.mathew"),
                    cert.id,
                    PersonalLockApply.model_validate(
                        {
                            "lock_id": str(c.locks[ln].id),
                            "worker_id": cp["worker_id"],
                            "applied_at": t.isoformat(),
                            "permit_id": str(permit.id),
                        }
                    ),
                )
            )
        return evs

    def locks_off(evs: list[Any], t: datetime) -> None:
        for ev in evs:
            set_now(t)
            isolations.remove_personal(
                n.db,
                n.p("joseph.mathew"),
                ev.id,
                PersonalLockRemove.model_validate({"removed_at": t.isoformat()}),
            )

    evs = locks_on(at(2026, 9, 29, 7, 3))
    n.start(permit, "joseph.mathew", at(2026, 9, 29, 7, 5))
    locks_off(evs, at(2026, 9, 29, 16, 45))
    n.end_shift(permit, "joseph.mathew", at(2026, 9, 29, 16, 50))
    for y, m, d in ((2026, 9, 30), (2026, 10, 1), (2026, 10, 2)):
        evs = locks_on(at(y, m, d, 7, 3))
        n.revalidate(permit, "majed.shammari", "joseph.mathew", at(y, m, d, 7, 5))
        locks_off(evs, at(y, m, d, 16, 15 if d == 2 else 45))
        if d != 2:
            n.end_shift(permit, "joseph.mathew", at(y, m, d, 16, 50))
    n.close(
        permit, "joseph.mathew", "majed.shammari", at(2026, 10, 2, 16, 20), at(2026, 10, 2, 16, 30)
    )
    set_now(at(2026, 10, 2, 16, 34))
    isolations.transition(
        n.db, n.p("ibrahim.saleh"), cert.id, IsolationTransition(to_status="deisolation_requested")
    )
    set_now(at(2026, 10, 2, 16, 36))
    isolations.transition(
        n.db, n.p("majed.shammari"), cert.id, IsolationTransition(to_status="deisolated")
    )
    set_now(at(2026, 10, 2, 16, 38))
    set_now(at(2026, 10, 2, 16, 40))
    isolations.remove_point(
        n.db,
        n.p("ibrahim.saleh"),
        cert.id,
        pt.id,
        PointRemoveInput.model_validate({"removed_at": at(2026, 10, 2, 16, 40).isoformat()}),
    )
    if cert.status.value != "deisolated":
        set_now(at(2026, 10, 2, 16, 40))
        isolations.transition(
            n.db, n.p("majed.shammari"), cert.id, IsolationTransition(to_status="deisolated")
        )


def p0287(n: N) -> None:
    """WAH slab edge L38 — Active (shift of 2026-10-06 from 06:05) (A.7, Y1, Y10)."""
    c = n.ctx
    set_now(at(2026, 10, 4, 9, 0))
    bulk = n.bulk_worker(
        "RBT-52", "QIMMA", 3, site="S-TWR", zone="Z-CORE", until=at(2026, 10, 9, 17)
    )
    hamza = str(n.w("WKR-000105"))
    b = n.base(
        "RBT-52",
        "S-TWR",
        ["Z-CORE"],
        "Core L38 slab edge, east face",
        "40.0",
        "18.0",
        "L38",
        "152.00",
        "QIMMA",
        [T.work_at_height.value],
        T.work_at_height.value,
        "Slab-edge formwork L38",
        at(2026, 10, 5, 6),
        at(2026, 10, 9, 17),
        win("06:00", "17:00"),
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        "lina.haddad",
        hamza,
    )
    b["crew"] = [
        {"worker_id": hamza, "crew_role": "supervisor"},
        {
            "worker_id": hamza,
            "crew_role": "competent_person",
            "appointment_id": str(c.apts["APT-RBT-52-0005"].id),
        },
        {"worker_id": str(n.w("WKR-000101")), "crew_role": "worker"},
        *[{"worker_id": str(w), "crew_role": "worker"} for w in bulk],
    ]
    b["documents"] = [
        {
            "doc_type": "rescue_plan",
            "ref": "RP-RBT-L38",
            "revision": "C",
            "approved_by_text": "QIMMA HSE Manager (fake)",
        }
    ]
    b["sections"] = [
        {
            "work_type": "work_at_height",
            "max_fall_height_m": "4.00",
            "access_method": ["slab_edge"],
            "fall_protection": "arrest_srl",
            "anchor_desc": "Cast-in anchor CA-L38-03",
            "anchor_rating_kn": "22.2",
            "srl_required_clearance_m": "2.40",
            "available_clearance_m": "4.00",
            "drop_zone_controlled": True,
            "tool_tethering": True,
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-RBT-52-0003")
    permit = n.create("joseph.mathew", "RBT-52", "PTW-RBT-52-2026-0287", b)
    n.jsa(permit, "joseph.mathew", "majed.shammari", "lina.haddad")
    n.to_approved(
        permit,
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        "lina.haddad",
        at(2026, 10, 4, 9, 10),
        at(2026, 10, 4, 10, 0),
        at(2026, 10, 4, 11, 0),
        at(2026, 10, 4, 12, 0),
    )
    n.issue(permit, "majed.shammari", "joseph.mathew", at(2026, 10, 5, 6, 0))
    n.start(permit, "joseph.mathew", at(2026, 10, 5, 6, 5))
    n.end_shift(permit, "joseph.mathew", at(2026, 10, 5, 16, 55))


def p0287_day2(n: N) -> None:
    n.revalidate(
        n.ctx.permits["PTW-RBT-52-2026-0287"],
        "majed.shammari",
        "joseph.mathew",
        at(2026, 10, 6, 6, 5),
    )


def p0288(n: N) -> None:
    """Hot work L37 — Active since 07:05; SIM-RBT-52-2026-0019 coordinated 06:50 (A.7, Y8 c)."""
    set_now(at(2026, 10, 5, 13, 0))
    sup = n.bulk_worker("RBT-52", "QIMMA", 1, site="S-TWR", zone="Z-CORE")[0]
    b = n.base(
        "RBT-52",
        "S-TWR",
        ["Z-CORE"],
        "Core L37 welding bay, embed plates",
        "42.0",
        "20.0",
        "L37",
        "148.00",
        "QIMMA",
        [T.hot_work.value],
        T.hot_work.value,
        "Embed plate welding L37",
        at(2026, 10, 6, 7),
        at(2026, 10, 6, 16),
        win("07:00", "16:00"),
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        None,
        str(sup),
    )
    b["crew"] = [
        {"worker_id": str(sup), "crew_role": "supervisor"},
        {"worker_id": str(n.w("WKR-000106")), "crew_role": "hot_work_operative"},
        {"worker_id": str(n.w("WKR-000107")), "crew_role": "fire_watch"},
    ]
    b["sections"] = [
        {
            "work_type": "hot_work",
            "hot_work_kind": ["arc_welding"],
            "combustibles_cleared_radius_m": "11.0",
            "fire_extinguishers": [
                {"type": "co2_5kg", "count": 1, "distance_m": "4.0"},
                {"type": "dcp_abc_6kg", "count": 1, "distance_m": "4.0"},
            ],
            "fire_blanket": True,
            "cylinders": "none",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-RBT-52-0002")
    permit = n.create("joseph.mathew", "RBT-52", "PTW-RBT-52-2026-0288", b)
    n.jsa(permit, "joseph.mathew", "majed.shammari", "lina.haddad")
    n.to_approved(
        permit,
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        None,
        at(2026, 10, 5, 13, 10),
        at(2026, 10, 5, 14, 0),
        None,
        at(2026, 10, 5, 15, 0),
    )


def p0288_day(n: N) -> None:
    from app.models import SimopsConflict
    from app.schemas.simops import CoordinationCreate
    from app.services.ptw import simops

    permit = n.ctx.permits["PTW-RBT-52-2026-0288"]
    k = n.db.scalar(
        select(SimopsConflict).where(
            SimopsConflict.permit_a_id.in_([permit.id])
            | SimopsConflict.permit_b_id.in_([permit.id])
        )
    )
    if k is not None:
        set_now(at(2026, 10, 6, 6, 50))
        simops.create_coordination(
            n.db,
            n.p("majed.shammari"),
            k.id,
            CoordinationCreate.model_validate(
                {
                    "agreed_controls_en": "Debris netting at the L38 edge; no work above the welding bay 07:00-16:00 except behind the netting.",
                    "cosigners": [n.cosign("ibrahim.saleh")],
                }
            ),
        )
    n.issue(permit, "majed.shammari", "joseph.mathew", at(2026, 10, 6, 7, 0))
    n.start(permit, "joseph.mathew", at(2026, 10, 6, 7, 5))


def p0290(n: N) -> None:
    """Critical tower-crane lift — Approved 2026-10-06 09:00; Issue blocked by SIM-0021 (A.7, Y7 a, Y8 d)."""
    c = n.ctx
    set_now(at(2026, 10, 5, 10, 0))
    from app.models import ObstacleClearance

    obs = n.db.scalar(
        select(ObstacleClearance.id).where(ObstacleClearance.obs_no == "OBS-RBT-52-2026-0001")
    )
    hamza = str(n.w("WKR-000105"))
    b = n.base(
        "RBT-52",
        "S-TWR",
        ["Z-TC01", "Z-CORE"],
        "Tower crane TC-01, curtain-wall unit CW-38-07 to L38",
        "60.0",
        "30.0",
        None,
        None,
        "QIMMA",
        [T.lifting.value],
        T.lifting.value,
        "Curtain-wall unit lift",
        at(2026, 10, 7, 6, 30),
        at(2026, 10, 7, 10),
        win("06:30", "10:00"),
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        "lina.haddad",
        hamza,
    )
    b["crew"] = [
        {"worker_id": hamza, "crew_role": "supervisor"},
        {
            "worker_id": hamza,
            "crew_role": "lift_supervisor",
            "appointment_id": str(c.apts["APT-RBT-52-0004"].id),
        },
        {"worker_id": str(n.w("WKR-000102")), "crew_role": "crane_operator"},
        {"worker_id": str(n.w("WKR-000108")), "crew_role": "rigger"},
        {"worker_id": str(n.w("WKR-000108")), "crew_role": "signaller"},
    ]
    b["linked_obs_ids"] = [str(obs)]
    b["documents"] = [
        {
            "doc_type": "critical_lift_plan",
            "ref": "CLP-RBT-0012",
            "revision": "B",
            "approved_by_text": "Ibrahim Al-Saleh (APT-RBT-52-0003)",
        }
    ]
    b["jsa_template_id"] = tpl(n, "JSA-T-RBT-52-0006")
    permit = n.create("joseph.mathew", "RBT-52", "PTW-RBT-52-2026-0290", b)
    eq = n.add_equipment(
        permit,
        "joseph.mathew",
        {
            "equipment_tag": {
                "category": "tower_crane",
                "tag": "TC-01",
                "description": "Tower crane TC-01",
                "max_working_height_m": "236.00",
            },
            "use": "lifting_appliance",
        },
    )
    n.add_equipment(
        permit,
        "joseph.mathew",
        {
            "equipment_tag": {
                "category": "spreader_beam",
                "tag": "SB-RBT-04",
                "description": "Spreader beam 6 t",
            },
            "use": "lifting_accessory",
        },
    )
    n.sections(
        permit,
        "joseph.mathew",
        [
            {
                "work_type": "lifting",
                "appliance_equipment_ids": [str(eq)],
                "load_desc": "Curtain-wall unit CW-38-07",
                "load_weight_t": "4.200",
                "rigging_weight_t": "0.150",
                "radius_m": "42.00",
                "rated_capacity_t": "5.000",
                "wind_limit_ms": "13.0",
                "exclusion_radius_m": "5.0",
                "landing_grid_x_m": "45.0",
                "landing_grid_y_m": "22.0",
                "slew_radius_m": "60.0",
                "appliance_grid_x_m": "60.0",
                "appliance_grid_y_m": "30.0",
                "ground_bearing_checked": True,
            }
        ],
    )
    n.jsa(permit, "joseph.mathew", "majed.shammari", "lina.haddad")
    n.to_approved(
        permit,
        "joseph.mathew",
        "ibrahim.saleh",
        "majed.shammari",
        "lina.haddad",
        at(2026, 10, 5, 10, 10),
        at(2026, 10, 5, 14, 0),
        at(2026, 10, 6, 8, 0),
        at(2026, 10, 6, 9, 0),
    )


def audits_a8(n: N) -> None:
    """A.8 field audits of 0413 (90.9 %, CA for A14) and 0412 (100 %) — Y14."""
    from app.core.hse_enums import CaPriority, CaSourceType, ControlLevel
    from app.core.ptw_enums import PtwAuditType
    from app.models import CorrectiveAction, PtwAudit
    from app.schemas.actions import CaCreate
    from app.schemas.ptw_audits import PtwAuditCompleteInput, PtwAuditCreate
    from app.services import corrective_actions
    from app.services.ptw import audits

    c = n.ctx
    pid = c.projects["ANIA-EXP"].id

    def one(
        key: str, no: str, t_aud: datetime, t: datetime, audit_no: str, nc: dict[str, str]
    ) -> PtwAudit:
        permit = n.db.scalar(select(Permit).where(Permit.permit_no == no))
        set_now(t)
        codes = audits.applicable_items(n.db, PtwAuditType.field, permit, t_aud)
        items = [
            {"code": cd, "answer": "non_compliant" if cd in nc else "compliant", "note": nc.get(cd)}
            for cd in codes
        ]
        r = audits.create(
            n.db,
            n.p(key),
            pid,
            PtwAuditCreate.model_validate(
                {
                    "audit_type": "field",
                    "permit_id": str(permit.id),
                    "audited_at": t_aud.isoformat(),
                    "items": items,
                }
            ),
        )
        a: PtwAudit | None = n.db.get(PtwAudit, r.id)
        assert a is not None
        a.audit_no = audit_no
        a.seq = int(audit_no.rsplit("-", 1)[1])
        n.db.flush()
        return a

    a1 = one(
        "nasser.shahrani",
        "PTW-ANIA-EXP-2026-0413",
        at(2026, 10, 6, 8, 50),
        at(2026, 10, 6, 8, 55),
        "PTA-ANIA-EXP-2026-00187",
        {"A14": "Rescue tripod winch inspection tag illegible."},
    )
    ca = corrective_actions.create(
        n.db,
        n.p("nasser.shahrani"),
        pid,
        CaCreate.model_validate(
            {
                "source_type": CaSourceType.ptw_audit.value,
                "source_id": str(a1.id),
                "title": "A14: replace the illegible inspection tag on the MH-07 rescue tripod winch",
                "description": "Re-inspect the tripod winch and fit a legible inspection tag (A14).",
                "control_level": ControlLevel.administrative.value,
                "priority": CaPriority.low.value,
                "owner_id": str(c.uid("faris.anazi")),
                "verifier_id": str(c.uid("noura.qahtani")),
                "due_date": "2026-10-09",
            }
        ),
    )
    # CA-ANIA-EXP-2026-0311 (A.8) is taken by the Phase 1 seed (5-digit refs): keep the next number.
    assert n.db.get(CorrectiveAction, ca.id) is not None
    set_now(at(2026, 10, 6, 9, 0))
    audits.complete(n.db, n.p("nasser.shahrani"), a1.id, PtwAuditCompleteInput())
    a2 = one(
        "noura.qahtani",
        "PTW-ANIA-EXP-2026-0412",
        at(2026, 10, 6, 9, 20),
        at(2026, 10, 6, 9, 25),
        "PTA-ANIA-EXP-2026-00188",
        {},
    )
    set_now(at(2026, 10, 6, 9, 30))
    audits.complete(n.db, n.p("noura.qahtani"), a2.id, PtwAuditCompleteInput())


def _renumber_conflicts(n: N) -> None:
    """Named RBT-52 conflicts: 0287/0288 → SIM-0019, 0287/0290 → SIM-0021, any other after."""
    from app.models import SimopsConflict

    p87 = n.ctx.permits["PTW-RBT-52-2026-0287"].id
    want = {
        n.ctx.permits["PTW-RBT-52-2026-0288"].id: 19,
        n.ctx.permits["PTW-RBT-52-2026-0290"].id: 21,
    }
    rows = sorted(
        n.db.scalars(
            select(SimopsConflict).where(
                SimopsConflict.project_id == n.ctx.pid("RBT-52"),
                SimopsConflict.seed_fake.is_(False),
            )
        ),
        key=lambda r: (r.detected_at, r.seq),
    )
    final: dict[uuid.UUID, int] = {}
    spare = 22
    for k in rows:
        pair = {k.permit_a_id, k.permit_b_id}
        hit = next((v for pid, v in want.items() if pair == {p87, pid}), None)
        if hit is None:
            hit, spare = spare, spare + 1
        final[k.id] = hit
    for i, k in enumerate(rows):
        k.seq = 100000 + i
        k.conflict_no = f"SIM-RBT-52-2026-T{i:04d}"
    n.db.flush()
    for k in rows:
        k.seq = final[k.id]
        k.conflict_no = f"SIM-RBT-52-2026-{k.seq:04d}"
    n.db.flush()


def _refresh_named(n: N) -> None:
    """Blockers / warnings as at the seed clock (after renumbering), PT-16."""
    from app.services.ptw import evaluation

    for no in sorted(n.ctx.permits):
        permit = n.ctx.permits[no]
        n.db.refresh(permit)
        evaluation.refresh(n.db, permit, run_simops=False, auto_suspend=False)


def run(ctx: Ctx, password: str = "Seed-Passw0rd!2026") -> None:
    n = N(ctx, password)
    for fn in (
        p0279,
        p0399,
        p0408,
        p0287,
        p0405,
        p0290,
        p0288,
        p0287_day2,
        p0288_day,
        p0412,
        p0413,
        audits_a8,
        p0410,
        _renumber_conflicts,
    ):
        fn(n)
        ctx.db.flush()
    set_now(at(2026, 10, 6, 10, 0))
    _refresh_named(n)
    _ = Decimal
