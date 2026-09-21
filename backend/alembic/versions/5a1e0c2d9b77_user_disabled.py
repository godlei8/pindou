"""user is_disabled

Revision ID: 5a1e0c2d9b77
Revises: 0d652353ee51
Create Date: 2026-09-21 20:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5a1e0c2d9b77'
down_revision: Union[str, Sequence[str], None] = '0d652353ee51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_disabled', sa.Boolean(), server_default='false',
                                     nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_disabled')
