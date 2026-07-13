"""expand size wall to all clothing sizes

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


CLOTHING_CATEGORIES = [
    "保暖内衣", "内裤", "卫衣", "套装", "尼克服", "棉服", "毛衣", "派克服", "皮衣",
    "短T", "短衬", "羊毛大衣", "羽绒服", "背心", "茄克", "衬衫(停用)", "裘皮外套",
    "裙子", "裤子", "西服", "针织衫", "长T（停用）", "长衬", "长袖T恤", "风衣", "马甲",
]


def upgrade():
    op.add_column("dm_size_wall_candidate_daily", sa.Column("normalized_size_code", sa.String(32), nullable=False, server_default=""), schema="dm")
    op.add_column("dm_size_wall_candidate_daily", sa.Column("size_group", sa.String(24), nullable=False, server_default="other"), schema="dm")
    op.add_column("dm_size_wall_candidate_daily", sa.Column("size_sort", sa.Integer(), nullable=False, server_default="9999"), schema="dm")
    op.create_index("ix_size_wall_date_group_size", "dm_size_wall_candidate_daily", ["analysis_date", "size_group", "normalized_size_code"], schema="dm")
    rules = {
        "included_categories": CLOTHING_CATEGORIES,
        "excluded_size_codes": ["F"],
        "size_aliases": {"XXL": "2XL", "XXXL": "3XL"},
        "size_groups": ["numeric_top", "letter", "pants", "collar", "other"],
        "candidate_score": 60,
        "low_max": 4,
        "high_min": 21,
    }
    op.execute(sa.text("update sys.sys_param set param_value=:rules,description='断码尺码墙服装与全尺码规则' where param_key='size_wall_rules'").bindparams(rules=json.dumps(rules, ensure_ascii=False)))


def downgrade():
    op.drop_index("ix_size_wall_date_group_size", table_name="dm_size_wall_candidate_daily", schema="dm")
    op.drop_column("dm_size_wall_candidate_daily", "size_sort", schema="dm")
    op.drop_column("dm_size_wall_candidate_daily", "size_group", schema="dm")
    op.drop_column("dm_size_wall_candidate_daily", "normalized_size_code", schema="dm")
