"""Deleted-items register for administrator deletes (D-271).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-18 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('deleted_records',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('entity_type', sa.String(length=60), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('row_counts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['deleted_by_user_id'], ['users.id'], name=op.f('fk_deleted_records_deleted_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deleted_records'))
    )
    op.create_index('ix_deleted_records_at', 'deleted_records', ['deleted_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_deleted_records_at', table_name='deleted_records')
    op.drop_table('deleted_records')
