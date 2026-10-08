"""3-ptw §9 AC88-AC90 (PTW audits), Y14."""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.ptw_enums import PermitStatus, PtwAuditType, StatusReason
from app.models import PtwAudit
from app.schemas.actions import CaCreate
from app.schemas.ptw_audits import PtwAuditCompleteInput, PtwAuditCreate
from app.services import corrective_actions
from app.services.ptw import audits
from tests.ptw_helpers import SEED_AT, at, expect, permit, world


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def _items(db: Session, no: str, nc: dict[str, str | None]) -> list[dict[str, Any]]:
    p = permit(db, no)
    codes = audits.applicable_items(db, PtwAuditType.field, p, at(2026, 10, 6, 8, 50))
    out = []
    for c in codes:
        row: dict[str, Any] = {"code": c, "answer": "non_compliant" if c in nc else "compliant"}
        if nc.get(c):
            row["severity"] = nc[c]
        out.append(row)
    return out


def _audit(n: Any, who: str, no: str, nc: dict[str, str | None]) -> Any:
    p = permit(n.db, no)
    body = {
        "audit_type": "field",
        "permit_id": str(p.id),
        "audited_at": at(2026, 10, 6, 8, 50).isoformat(),
        "items": _items(n.db, no, nc),
    }
    return audits.create(n.db, n.p(who), n.ctx.pid("ANIA-EXP"), PtwAuditCreate.model_validate(body))


def test_AC88_Y14_score_and_critical_suspension(n: Any) -> None:
    seeded = n.db.scalar(select(PtwAudit).where(PtwAudit.audit_no == "PTA-ANIA-EXP-2026-00187"))
    assert seeded is not None
    assert (seeded.applicable_count, seeded.compliant_count, seeded.score_pct) == (
        11,
        10,
        Decimal("90.9"),
    )
    codes = sorted(
        audits.applicable_items(
            n.db, PtwAuditType.field, permit(n.db, "PTW-ANIA-EXP-2026-0413"), at(2026, 10, 6, 8, 50)
        )
    )
    assert codes == sorted(
        ["A01", "A02", "A03", "A04", "A05", "A14", "A15", "A16", "A20", "A06", "A10"]
    )
    minor = _audit(n, "nasser.shahrani", "PTW-ANIA-EXP-2026-0413", {"A14": None})
    assert minor.score_pct == "90.9" or Decimal(str(minor.score_pct)) == Decimal("90.9")
    crit = _audit(n, "nasser.shahrani", "PTW-ANIA-EXP-2026-0413", {"A14": None, "A10": "critical"})
    assert Decimal(str(crit.score_pct)) == Decimal("81.8")
    p = permit(n.db, "PTW-ANIA-EXP-2026-0413")
    n.db.refresh(p)
    assert p.status == PermitStatus.suspended and p.status_reason == StatusReason.audit_critical
    err = expect(
        "CA_REQUIRED",
        lambda: audits.complete(n.db, n.p("nasser.shahrani"), crit.id, PtwAuditCompleteInput()),
    )
    assert (err.meta or {}).get("items") == ["A10"]
    _ca(n, crit.id, "A10: standby person absent at MH-07", "critical")
    done = audits.complete(n.db, n.p("nasser.shahrani"), crit.id, PtwAuditCompleteInput())
    assert done.status.value == "completed"


def _ca(n: Any, audit_id: Any, title: str, priority: str, project: str = "ANIA-EXP") -> Any:
    body = {
        "source_type": "ptw_audit", "source_id": str(audit_id), "title": title,
        "description": "Correct the finding and re-brief the crew.", "control_level": "administrative",
        "priority": priority, "owner_id": str(n.ctx.uid("ahmed.zahrani")), "verifier_id": str(n.ctx.uid("faisal.harbi")),
    }  # fmt: skip
    return corrective_actions.create(
        n.db, n.p("noura.qahtani"), n.ctx.pid(project), CaCreate.model_validate(body)
    )


def test_AC89_hse_reviewer_cannot_audit_own_permit(n: Any) -> None:
    expect("SOD_CONFLICT", lambda: _audit(n, "noura.qahtani", "PTW-ANIA-EXP-2026-0413", {}), 422)
    expect("SOD_CONFLICT", lambda: _audit(n, "khalid.otaibi", "PTW-ANIA-EXP-2026-0413", {}), 422)


def test_AC90_unpermitted_work_audit(n: Any, api: Any, ids: Any) -> None:
    pid = n.ctx.pid("ANIA-EXP")
    base = {
        "audit_type": "unpermitted_work",
        "site_id": str(n.ctx.site("ANIA-EXP", "S-LAND").id),
        "zone_id": str(n.ctx.zones["Z-PIERB"].id),
        "engagement_id": str(n.ctx.eng("ANIA-EXP", "NAJD").id),
        "audited_at": at(2026, 10, 6, 9, 40).isoformat(),
        "unpermitted_work_desc": "Grinding at Pier B without a hot-work permit.",
    }
    expect(
        "VALIDATION_ERROR",
        lambda: audits.create(n.db, n.p("noura.qahtani"), pid, PtwAuditCreate.model_validate(base)),
    )

    def k64() -> int:
        res = api.as_("faisal.harbi").get(
            "/api/v1/kpi/metrics/K-64",
            params={
                "project_id": ids.project("ANIA-EXP"),
                "period": "month",
                "anchor": "2026-10-01",
                "as_of": "2026-10-31",
            },
        )
        assert res.status_code == 200, res.text
        return int(res.json()["kpi"]["value"])

    before = k64()
    a = audits.create(
        n.db,
        n.p("noura.qahtani"),
        pid,
        PtwAuditCreate.model_validate(
            {**base, "stop_work_issued_at": at(2026, 10, 6, 9, 35).isoformat()}
        ),
    )
    assert [i.code.value for i in a.items if i.answer is not None] == ["A00"]
    err = expect(
        "CA_REQUIRED",
        lambda: audits.complete(n.db, n.p("noura.qahtani"), a.id, PtwAuditCompleteInput()),
    )
    assert (err.meta or {}).get("items") == ["A00"]
    _ca(n, a.id, "A00: toolbox talk on permits", "low")  # a low-priority CA does not satisfy AU-4
    expect(
        "CA_REQUIRED",
        lambda: audits.complete(n.db, n.p("noura.qahtani"), a.id, PtwAuditCompleteInput()),
    )
    ca = _ca(n, a.id, "A00: stop unpermitted grinding and raise a permit", "critical")
    assert ca.source.type.value == "ptw_audit"
    audits.complete(n.db, n.p("noura.qahtani"), a.id, PtwAuditCompleteInput())
    n.db.commit()
    assert k64() == before + 1
