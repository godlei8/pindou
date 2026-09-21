"""pattern fidelity

Revision ID: 8c3f1d2a6e40
Revises: 5a1e0c2d9b77
Create Date: 2026-09-21 17:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '8c3f1d2a6e40'
down_revision: Union[str, Sequence[str], None] = '5a1e0c2d9b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('patterns', sa.Column('fidelity', postgresql.JSONB(astext_type=sa.Text()),
                                        nullable=True))


def downgrade() -> None:
    op.drop_column('patterns', 'fidelity')
