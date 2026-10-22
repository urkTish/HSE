"""Trial A: 6g external report-pack emails go out with their files attached (D-280)."""

from __future__ import annotations

import email
import email.policy
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import EmailStatus
from app.core.scorecard_enums import RpDeliveryStatus, RpLanguage, RpMemberKind, RpType
from app.models import Attachment, EmailMessage, RpDelivery
from app.schemas.scorecard import RpDistributionUpdate, RpMemberInput, ScSettingsUpdate
from app.services import attachments, mailer
from app.services.scorecard import config, distribution
from tests.sc_helpers import P, notified, pack, project
from tests.smtp_fake import smtp_server

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")


@pytest.fixture(autouse=True)
def _empty_outbox(db: Session) -> None:
    """Seeds may leave queued rows (demo invites); each test starts from an empty outbox."""
    db.execute(delete(EmailMessage))
    db.commit()


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    s = get_settings()
    with smtp_server() as (port, inbox):
        monkeypatch.setattr(s, "smtp_host", "127.0.0.1")
        monkeypatch.setattr(s, "smtp_port", port)
        monkeypatch.setattr(s, "smtp_from", "hse@client.sa")
        monkeypatch.setattr(s, "smtp_security", "none")
        yield inbox


def _distribute(db: Session, *members: tuple[str, RpLanguage]) -> list[RpDelivery]:
    pid = project(db, "ANIA-EXP").id
    f = P(db, "faisal.harbi")
    config.update_settings(
        db,
        f,
        pid,
        ScSettingsUpdate(external_distribution_enabled=True, external_domains=["pmc.sa"]),
    )
    distribution.put_list(
        db,
        f,
        pid,
        RpType.MCR,
        RpDistributionUpdate(
            members=[
                RpMemberInput(
                    kind=RpMemberKind.external,
                    email=addr,
                    display_name_en="PMC",
                    language=lang,
                    acknowledge_disclosure=True,
                )
                for addr, lang in members
            ]
        ),
    )
    r1 = pack(db, "MCR-ANIA-EXP-2026-08", 1)
    distribution.distribute(db, r1)
    db.commit()
    addrs = [a for a, _ in members]
    return list(db.scalars(select(RpDelivery).where(RpDelivery.email.in_(addrs))))


def test_external_pack_email_carries_the_files(db: Session, smtp: Any) -> None:
    rows = _distribute(db, ("pm@pmc.sa", RpLanguage.en), ("dm@pmc.sa", RpLanguage.ar))
    by = {r.email: r for r in rows}
    assert {r.status for r in rows} == {RpDeliveryStatus.queued}
    out = db.scalars(select(EmailMessage).where(EmailMessage.template == "report_pack")).all()
    assert len(out) == 2 and all(m.attachment_ids and m.delivery_id for m in out)
    ar_row = next(m for m in out if m.to_email == "dm@pmc.sa")
    assert ar_row.subject.startswith("صدرت MCR-ANIA-EXP-2026-08")

    assert mailer.send_due(db)["sent"] == 2
    for r in rows:
        db.refresh(r)
    assert by["pm@pmc.sa"].status == by["dm@pmc.sa"].status == RpDeliveryStatus.sent

    msgs = {
        rcpts[0]: email.message_from_bytes(raw, policy=email.policy.default)
        for _, rcpts, raw in smtp.messages
    }
    en = msgs["pm@pmc.sa"]
    files = {p.get_filename(): p.get_payload(decode=True) for p in en.iter_attachments()}
    assert set(files) == set(by["pm@pmc.sa"].attachments)
    assert any(n.endswith(".pdf") for n in files) and any(n.endswith(".xlsx") for n in files)
    for m in out:
        if m.to_email != "pm@pmc.sa":
            continue
        for aid in m.attachment_ids:
            a = db.get(Attachment, aid)
            assert a is not None and files[a.file_name] == attachments.read_content(a)
    ar_files = [p.get_filename() for p in msgs["dm@pmc.sa"].iter_attachments()]
    assert any(n.endswith("-ar.pdf") for n in ar_files)
    assert not any(n.endswith("-en.pdf") for n in ar_files)


def test_refused_pack_email_marks_delivery_failed(db: Session, smtp: Any) -> None:
    smtp.refuse["gone@pmc.sa"] = "550 5.1.1 unknown user"
    (row,) = _distribute(db, ("gone@pmc.sa", RpLanguage.en))
    assert mailer.send_due(db)["failed"] == 1
    db.refresh(row)
    assert row.status == RpDeliveryStatus.failed and (row.error or "").startswith("550")
    msg = db.scalars(select(EmailMessage).where(EmailMessage.delivery_id == row.id)).one()
    assert msg.status == EmailStatus.failed
    titles = notified(db, "delivery_bounced").get("faisal.harbi") or []
    assert any("could not be sent" in t for t in titles)
