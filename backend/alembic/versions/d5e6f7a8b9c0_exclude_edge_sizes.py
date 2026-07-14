"""exclude non-actionable edge sizes from size wall

Revision ID: d5e6f7a8b9c0
Revises: e5f6a7b8c9d0
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    raw = bind.execute(sa.text("select param_value from sys.sys_param where param_key='size_wall_rules'")).scalar() or "{}"
    rules = json.loads(raw)
    rules["excluded_size_codes"] = ["F", "46Y", "58Y"]
    bind.execute(
        sa.text("update sys.sys_param set param_value=:rules,description='断码尺码墙服装与全尺码规则（排除F/46Y/58Y）' where param_key='size_wall_rules'"),
        {"rules": json.dumps(rules, ensure_ascii=False)},
    )


def downgrade():
    bind = op.get_bind()
    raw = bind.execute(sa.text("select param_value from sys.sys_param where param_key='size_wall_rules'")).scalar() or "{}"
    rules = json.loads(raw)
    rules["excluded_size_codes"] = ["F"]
    bind.execute(sa.text("update sys.sys_param set param_value=:rules where param_key='size_wall_rules'"), {"rules": json.dumps(rules, ensure_ascii=False)})
