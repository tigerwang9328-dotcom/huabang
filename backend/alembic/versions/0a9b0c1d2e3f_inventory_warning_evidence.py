"""Add configured evidence to inventory warnings.

Revision ID: 0a9b0c1d2e3f
Revises: 0a8b9c0d1e2f
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0a9b0c1d2e3f"
down_revision = "0a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dm_inventory_warning", sa.Column("rule_id", sa.String(16)), schema="dm")
    op.add_column(
        "dm_inventory_warning",
        sa.Column("thresholds", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        schema="dm",
    )
    op.add_column(
        "dm_inventory_warning",
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        schema="dm",
    )
    op.add_column("dm_inventory_warning", sa.Column("source_name", sa.String(64)), schema="dm")
    op.execute("""
        INSERT INTO app.app_business_rule_config(rule_id, rule_name, thresholds) VALUES
        ('R016','季节库存预警',jsonb_build_object('min_inventory',10,'max_product_year_age',1)),
        ('R017','单款断码预警',jsonb_build_object('max_available_sizes',1,'min_inventory',3)),
        ('R018','低动销高库存',jsonb_build_object('min_inventory',30,'sales_days',30)),
        ('R019','有销量低库存',jsonb_build_object('max_sellable_days',7)),
        ('R020','门店库存不均衡与调拨',jsonb_build_object('high_inventory',12,'low_inventory',1)),
        ('R021','清仓返仓建议',jsonb_build_object('min_age_days',180,'risk_amount',30000))
        ON CONFLICT (rule_id) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM app.app_business_rule_config WHERE rule_id BETWEEN 'R016' AND 'R021'")
    op.drop_column("dm_inventory_warning", "source_name", schema="dm")
    op.drop_column("dm_inventory_warning", "evidence", schema="dm")
    op.drop_column("dm_inventory_warning", "thresholds", schema="dm")
    op.drop_column("dm_inventory_warning", "rule_id", schema="dm")
