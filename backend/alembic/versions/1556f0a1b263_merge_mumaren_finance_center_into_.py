"""merge mumaren finance center into release head

Revision ID: 1556f0a1b263
Revises: 3a2d7e951b2c, a19c7e3d5b41
Create Date: 2026-07-31 10:41:13.888025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1556f0a1b263'
down_revision: Union[str, None] = ('3a2d7e951b2c', 'a19c7e3d5b41')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
