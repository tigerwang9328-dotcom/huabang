"""merge v4.0 douyin color and finance heads

Revision ID: 217152ee1a62
Revises: 1556f0a1b263, b1c2d3e4f5a6
Create Date: 2026-07-31 12:24:05.880436

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '217152ee1a62'
down_revision: Union[str, None] = ('1556f0a1b263', 'b1c2d3e4f5a6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
