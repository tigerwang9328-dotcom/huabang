"""add size wall candidate snapshots

Revision ID: b2c3d4e5f6a7
Revises: f1b2c3d4e5f6
"""
from alembic import op
from sqlalchemy import text


revision = "b2c3d4e5f6a7"
down_revision = "f1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        create table if not exists dm.dm_size_wall_candidate_daily(
          analysis_date date not null,
          store_code varchar(32) not null,
          store_name varchar(255),
          location_type varchar(16) not null,
          product_code varchar(64) not null,
          product_name varchar(255),
          color_code varchar(64) not null default '',
          color_name varchar(128),
          size_code varchar(32) not null,
          size_name varchar(64),
          product_year integer not null,
          category_name varchar(128),
          tag_price numeric(18,2) not null default 0,
          price_band varchar(32) not null,
          inventory_qty numeric(18,4) not null default 0,
          inventory_amount numeric(18,2) not null default 0,
          sales_qty_30d numeric(18,4) not null default 0,
          sales_amount_30d numeric(18,2) not null default 0,
          listed_size_count integer not null default 0,
          remaining_size_count integer not null default 0,
          listed_color_count integer not null default 0,
          remaining_color_count integer not null default 0,
          distribution_count integer not null default 0,
          company_wall_qty numeric(18,4) not null default 0,
          score integer not null,
          score_reasons jsonb not null default '[]'::jsonb,
          suggested_action varchar(32) not null,
          size_status varchar(16) not null,
          sales_coverage_start date not null,
          sales_coverage_end date not null,
          sales_coverage_days integer not null,
          generated_at timestamptz not null default now(),
          primary key(analysis_date,store_code,product_code,color_code,size_code)
        )
    """)
    op.execute("create index if not exists ix_size_wall_date_score on dm.dm_size_wall_candidate_daily(analysis_date,score desc)")
    op.execute("create index if not exists ix_size_wall_date_store_size on dm.dm_size_wall_candidate_daily(analysis_date,store_code,size_code)")
    op.execute("create index if not exists ix_size_wall_filters on dm.dm_size_wall_candidate_daily(analysis_date,product_year,category_name,price_band,suggested_action)")
    op.get_bind().execute(text("""
        insert into sys.sys_param(param_key,param_value,description,is_system)
        values('size_wall_rules',:rules,
               '断码尺码墙默认规则',true)
        on conflict(param_key) do nothing
    """), {"rules": '{"sizes":["48Y","50Y","52Y","54Y"],"candidate_score":60,"low_max":4,"high_min":21}'})


def downgrade():
    op.execute("delete from sys.sys_param where param_key='size_wall_rules'")
    op.execute("drop table if exists dm.dm_size_wall_candidate_daily")
