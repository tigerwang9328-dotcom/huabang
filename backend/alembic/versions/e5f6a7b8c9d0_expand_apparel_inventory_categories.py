"""expand apparel inventory categories

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from alembic import op


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


BASE_CATEGORIES = [
    "裤子", "短T", "茄克", "羽绒服", "毛衣", "长袖T恤", "长衬", "卫衣", "短衬", "针织衫",
    "皮衣", "棉服", "西服", "风衣", "马甲", "羊毛大衣", "尼克服", "背心", "派克服", "裘皮外套",
]
EXPANDED_CATEGORIES = BASE_CATEGORIES + [
    "套装", "裙子", "夹克", "衬衫", "衬衫(停用)", "长T", "长T（停用）", "外套", "毛衫",
]
APPAREL_NAME_PATTERN = (
    "(裤|T恤|长T|短袖|衬衫|羽绒服|夹克|茄克|卫衣|毛衣|毛衫|针织|"
    "大衣|风衣|皮衣|棉服|马甲|背心|西服|套装|裙子|外套|派克服|尼克服)"
)


def _category_sql(categories):
    return ",".join(f"'{category}'" for category in categories)


def _replace_views(categories):
    category_sql = _category_sql(categories)
    op.execute(
        f"""
        CREATE OR REPLACE VIEW dwd.v_apparel_inventory_balance AS
        SELECT i.*
        FROM dwd.dwd_inventory_balance i
        LEFT JOIN dim.dim_product p ON p.product_code = i.product_code
        WHERE COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                  IN ({category_sql})
           OR (
                COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                    IN ('未定义', '未分类')
                AND COALESCE(NULLIF(p.product_name, ''), NULLIF(i.goods_name, ''), '')
                    ~ '{APPAREL_NAME_PATTERN}'
           )
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE VIEW dwd.v_apparel_inventory_snapshot AS
        SELECT i.*
        FROM dwd.dwd_inventory_snapshot i
        LEFT JOIN dim.dim_product p ON p.product_code = i.product_code
        WHERE COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                  IN ({category_sql})
           OR (
                COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                    IN ('未定义', '未分类')
                AND COALESCE(NULLIF(p.product_name, ''), '') ~ '{APPAREL_NAME_PATTERN}'
           )
        """
    )


def upgrade():
    _replace_views(EXPANDED_CATEGORIES)


def downgrade():
    _replace_views(BASE_CATEGORIES)
