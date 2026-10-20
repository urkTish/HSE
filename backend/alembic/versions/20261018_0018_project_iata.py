"""Projects: optional IATA airport code replaces the mandatory ICAO code (D-266).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-18 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ICAO (4 letters) cannot be converted to IATA (3 letters): existing values are dropped.
    op.add_column('projects', sa.Column('airport_iata', sa.String(length=3), nullable=True))
    op.drop_column('projects', 'airport_icao')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('projects', sa.Column('airport_icao', sa.String(length=4), nullable=True))
    op.drop_column('projects', 'airport_iata')
