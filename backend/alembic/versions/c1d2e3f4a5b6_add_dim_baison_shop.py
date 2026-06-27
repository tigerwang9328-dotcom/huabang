"""add dim_baison_shop table (百胜E3 店铺档案 API 落库)

Revision ID: c1d2e3f4a5b6
Revises: 1b10a07bbe68
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1d2e3f4a5b6"
down_revision = "1b10a07bbe68"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS dim")
    op.create_table(
        "dim_baison_shop",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(64), comment="sd_id 门店ID"),
        sa.Column("shop_code", sa.String(64), nullable=False, comment="sd_code 门店代码，唯一键"),
        sa.Column("shop_name", sa.String(256), comment="sd_name 门店名称"),
        sa.Column("shop_type", sa.String(32), comment="sdxz 门店性质"),
        sa.Column("online_type", sa.String(32), comment="online_name 线上/线下"),
        sa.Column("channel_code", sa.String(32), comment="qddm 渠道代码"),
        sa.Column("channel_name", sa.String(64), comment="qdmc 渠道名称"),
        sa.Column("category_code", sa.String(32), comment="lbdm 类别代码"),
        sa.Column("category_name", sa.String(64), comment="lbmc 类别名称"),
        sa.Column("area_code", sa.String(32), comment="qydm 区域代码"),
        sa.Column("area_name", sa.String(64), comment="qymc 区域名称"),
        sa.Column("province", sa.String(64)),
        sa.Column("city", sa.String(64)),
        sa.Column("county", sa.String(64)),
        sa.Column("address", sa.String(256), comment="dz 地址"),
        sa.Column("price_shop_code", sa.String(32), comment="zjf 执价店"),
        sa.Column("discount_rate", sa.Numeric(10, 4), comment="zk 折扣"),
        sa.Column("employee_code", sa.String(32), comment="ygdm 员工代码"),
        sa.Column("last_changed", sa.String(32), comment="lastchanged 百胜原值"),
        sa.Column("is_enabled", sa.String(8), comment="is_qy 是否启用 1/0"),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), comment="百胜原始整行"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("synced_at", sa.DateTime(timezone=True), comment="本次同步时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_code", name="uq_dim_baison_shop_shop_code"),
        schema="dim",
    )


def downgrade():
    op.drop_table("dim_baison_shop", schema="dim")
