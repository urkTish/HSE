"""Trial readiness, package B: installed licence keys (D-289).

Revision ID: b_0024_licence
Revises: 0023
Create Date: 2026-10-22 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b_0024_licence'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'licence_keys',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('licence_id', sa.String(length=80), nullable=False),
        sa.Column('customer', sa.String(length=200), nullable=False),
        sa.Column('bundle', sa.String(length=20), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=False),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('installed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['installed_by_user_id'],
            ['users.id'],
            name=op.f('fk_licence_keys_installed_by_user_id_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_licence_keys')),
    )
    op.create_index('ix_licence_keys_installed_at', 'licence_keys', ['installed_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_licence_keys_installed_at', table_name='licence_keys')
    op.drop_table('licence_keys')
