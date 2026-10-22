"""Trial A: SMTP sender state on the email outbox (status, retries, attachments, delivery link).

Revision ID: a_0024_email_sender
Revises: 0023
Create Date: 2026-10-22 09:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a_0024_email_sender"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "email_outbox",
        sa.Column(
            "status",
            sa.Enum("queued", "sent", "failed", name="emailstatus", native_enum=False, length=40),
            nullable=False,
            server_default="queued",
        ),
    )
    op.add_column(
        "email_outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("email_outbox", sa.Column("last_error", sa.String(length=500), nullable=True))
    op.add_column(
        "email_outbox",
        sa.Column(
            "attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("email_outbox", sa.Column("delivery_id", sa.Uuid(), nullable=True))
    # Rows already marked sent keep that state; everything else waits for the sender (which
    # marks rows older than EMAIL_MAX_AGE_HOURS failed instead of sending stale links).
    op.execute("UPDATE email_outbox SET status = 'sent' WHERE sent_at IS NOT NULL")
    op.create_index(
        "ix_email_outbox_status_next", "email_outbox", ["status", "next_attempt_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_email_outbox_status_next", table_name="email_outbox")
    op.drop_column("email_outbox", "delivery_id")
    op.drop_column("email_outbox", "attachment_ids")
    op.drop_column("email_outbox", "last_error")
    op.drop_column("email_outbox", "next_attempt_at")
    op.drop_column("email_outbox", "attempts")
    op.drop_column("email_outbox", "status")
