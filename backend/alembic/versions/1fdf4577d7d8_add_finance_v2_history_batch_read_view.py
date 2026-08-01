"""add finance v2 history batch read view

Revision ID: 1fdf4577d7d8
Revises: 9c121d3145d9
Create Date: 2026-07-29 18:18:40.353049

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1fdf4577d7d8'
down_revision: Union[str, None] = '9c121d3145d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW fin_read.history_import_batch AS
        SELECT
            id,
            batch_code,
            source_system,
            source_database,
            status,
            expected_counts,
            actual_counts,
            created_at,
            published_at
        FROM fin_history.import_batch;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS fin_read.history_import_batch")
