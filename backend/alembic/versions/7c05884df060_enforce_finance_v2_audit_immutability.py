"""enforce finance v2 audit immutability

Revision ID: 7c05884df060
Revises: 4f7ee5989a97
Create Date: 2026-07-29 12:13:40.421496

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c05884df060'
down_revision: Union[str, None] = '4f7ee5989a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fin_current.reject_operation_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'operation_event records are append-only';
        END;
        $$;
        CREATE TRIGGER tr_fin_current_operation_event_immutable
        BEFORE UPDATE OR DELETE ON fin_current.operation_event
        FOR EACH ROW EXECUTE FUNCTION fin_current.reject_operation_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_fin_current_operation_event_immutable ON fin_current.operation_event")
    op.execute("DROP FUNCTION IF EXISTS fin_current.reject_operation_event_mutation()")
