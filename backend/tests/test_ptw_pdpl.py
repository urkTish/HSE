"""3-ptw §9 AC98-AC100 (PDPL and i18n)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ptw_jobs
from app.core.access_enums import HookKind, HookProviderStatus
from app.core.clock import set_now
from app.core.enums import ExportDataset
from app.core.ptw_enums import (
    ClosureItem,
    PermitBlocker,
    PermitWarningCode,
    PreIssueItem,
    StatusReason,
)
from app.models import GasTest
from app.services.access import hooks
from app.services.ptw import reference, views
from tests.conftest import Api
from tests.ptw_helpers import SEED_AT, permit, world

P413 = "PTW-ANIA-EXP-2026-0413"


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def test_AC98_gas_signature_signed_url(n: Any, api: Api) -> None:
    t = n.db.scalar(
        select(GasTest).where(
            GasTest.permit_id == permit(n.db, P413).id,
            GasTest.tester_signature_attachment_id.is_not(None),
        )
    )
    assert t is not None
    n.db.commit()
    url = f"/api/v1/attachments/{t.tester_signature_attachment_id}/signed-url"
    res = api.as_("faisal.harbi").post(url)
    if res.status_code == 405:
        res = api.as_("faisal.harbi").get(url)
    assert res.status_code == 200, res.text
    exp = datetime.fromisoformat(res.json()["expires_at"].replace("Z", "+00:00"))
    assert exp - datetime.now(UTC) <= timedelta(minutes=5, seconds=5)
    for who in ("sarah.mitchell", "ramesh.kumar"):
        r = api.as_(who).post(url) if res.request.method == "POST" else api.as_(who).get(url)
        assert r.status_code in (403, 404), (who, r.status_code)
    assert not [d for d in ExportDataset if "signature" in d.value]
    pid = n.ctx.pid("ANIA-EXP")
    full = api.as_("faisal.harbi").get("/api/v1/exports/gas_tests", params={"project_id": str(pid)})
    assert full.status_code == 200, full.text
    head = full.content.decode("utf-8-sig").splitlines()[0].split(",")
    assert t.test_no in full.text and "tester_appointment_no" in head
    assert not [h for h in head if "signature" in h or "attachment" in h or "reading" in h]
    view = api.as_("sarah.mitchell").get("/api/v1/exports/locks", params={"project_id": str(pid)})
    assert view.status_code == 200, view.text
    vhead = view.content.decode("utf-8-sig").splitlines()[0].split(",")
    assert "holder_name" not in vhead and "holder_worker_no" not in vhead
    assert "WKR-" not in view.text
    assert (
        api.as_("ramesh.kumar")
        .get("/api/v1/exports/gas_tests", params={"project_id": str(pid)})
        .status_code
        == 403
    )


class Unfit:
    def check(self, subject_type, subject_id, kind, code, at):  # type: ignore[no-untyped-def]
        return hooks.HookCheck(HookProviderStatus.not_met, reason_code="UNFIT_TEST")


def test_AC99_medical_fitness_redaction(n: Any) -> None:
    hooks.register_provider(HookKind.medical_fitness, Unfit())
    try:
        ptw_jobs.ptw_minute(n.db, SEED_AT + timedelta(minutes=1))
        p = permit(n.db, P413)
        kamal = n.w("WKR-000016")

        def items(who: str) -> list[Any]:
            r = views.permit_read(n.db, n.p(who), p)
            line = next(
                c
                for c in r.crew
                if c.worker is not None and c.worker.id == kamal and c.crew_role.value == "entrant"
            )
            return [
                i
                for i in line.eligibility
                if i.redacted or (i.hook_kind and i.hook_kind.value == "medical_fitness")
            ]

        faris = items("faris.anazi")
        assert faris and all(
            i.redacted
            and i.code is None
            and i.hook_kind is None
            and i.message_en == "Not eligible — HSE check"
            for i in faris
        )
        noura = items("noura.qahtani")
        assert noura and all(
            i.hook_kind.value == "medical_fitness"
            and i.code == "CSE-ENTRY-FIT"
            and not i.reason_code
            for i in noura
        ), noura
    finally:
        hooks.unregister_provider(HookKind.medical_fitness)


def test_AC100_arabic_reference_texts() -> None:
    def ar(pair: Any) -> str:
        return pair[1] if isinstance(pair, tuple) else pair

    for code in PermitBlocker:
        assert ar(reference.BLOCKER_TEXT[code]).strip(), code
    for w in PermitWarningCode:
        assert ar(reference.WARNING_TEXT[w]).strip(), w
    for r in StatusReason:
        assert ar(reference.REASON_TEXT[r]).strip(), r
    for c in PreIssueItem:
        assert reference.PRE_ISSUE[c][1].strip(), c
    for x in ClosureItem:
        assert reference.CLOSURE[x][1].strip(), x
    assert {f"A{i:02d}" for i in range(21)} <= set(reference.AUDIT_ITEMS)
    for code, (_en, ar_text, _sev) in reference.AUDIT_ITEMS.items():
        assert ar_text.strip(), code
    for t, info in reference.TYPES.items():
        assert info.label_ar.strip(), t


def test_ptw_exports_all_datasets(n: Any, api: Api, db: Session) -> None:
    from app.models import AuditEntry
    from app.services.ptw import exports as ptw_exports

    n.db.commit()
    pid = str(n.ctx.pid("ANIA-EXP"))
    for d in sorted(ptw_exports.DATASETS, key=lambda x: x.value):
        for who in ("faisal.harbi", "sarah.mitchell"):
            res = api.as_(who).get(f"/api/v1/exports/{d.value}", params={"project_id": pid})
            assert res.status_code == 200, (d, who, res.text)
            assert len(res.content.decode("utf-8-sig").splitlines()) > 1, (d, who)
        xl = api.as_("faisal.harbi").get(
            f"/api/v1/exports/{d.value}", params={"project_id": pid, "format": "xlsx"}
        )
        assert xl.status_code == 200 and xl.content[:2] == b"PK", d
    db.expire_all()
    last = db.scalars(
        select(AuditEntry).where(AuditEntry.action == "export").order_by(AuditEntry.seq.desc())
    ).first()
    assert last is not None and last.details["dataset"] == "simops_conflicts"
    assert api.as_("faisal.harbi").get("/api/v1/exports/permits").status_code == 422
