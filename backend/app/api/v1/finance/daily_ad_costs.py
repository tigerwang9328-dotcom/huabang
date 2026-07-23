"""
每日广告费和赔付维护 API - /api/v1/finance/daily-ad-costs/*
"""
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User

router = APIRouter(prefix="/finance/daily-ad-costs")


_COLLECTED_AD_COST_SOURCES = [
    {
        "platform": "千川",
        "account_table": "sales_qianchuan_accounts",
        "cost_table": "sales_qianchuan_ad_costs",
        "account_key": "aavid",
        "account_label": "aavid",
    },
    {
        "platform": "快手",
        "account_table": "sales_kuaishou_accounts",
        "cost_table": "sales_kuaishou_ad_costs",
        "account_key": "account_key",
        "account_label": "account_key",
    },
    {
        "platform": "拼多多",
        "account_table": "sales_pinduoduo_accounts",
        "cost_table": "sales_pinduoduo_ad_costs",
        "account_key": "account_key",
        "account_label": "account_key",
    },
    {
        "platform": "视频号",
        "account_table": "sales_wechat_channel_accounts",
        "cost_table": "sales_wechat_channel_ad_costs",
        "account_key": "account_key",
        "account_label": "account_key",
    },
]


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    row = await db.execute(text("SELECT to_regclass(:table_name) AS table_name"), {"table_name": table_name})
    return row.scalar_one_or_none() is not None


async def _sync_collected_ad_costs_to_finance(db: AsyncSession, biz_date: date) -> int:
    """把所选日期已绑定店铺账户的最新采集广告费自动写入财务广告费。"""
    total = 0
    if (
        await _table_exists(db, "sales_qianchuan_account_store_bindings")
        and await _table_exists(db, "sales_qianchuan_ad_costs")
    ):
        result = await db.execute(text("""
            WITH binding_counts AS (
                SELECT aavid, COUNT(*) AS cnt
                FROM sales_qianchuan_account_store_bindings
                WHERE enabled = TRUE
                GROUP BY aavid
            ), qianchuan_costs AS (
                SELECT c.aavid, c.account_name, c.biz_date, c.ad_cost, c.captured_at
                FROM sales_qianchuan_ad_costs c
                JOIN binding_counts bc ON bc.aavid = c.aavid AND bc.cnt > 1
                WHERE c.biz_date = :dt
            ), pay_sales AS (
                SELECT
                    d.store_id,
                    d.order_date::date AS biz_date,
                    COALESCE(SUM(d.pay_amount), 0) AS sale_amount
                FROM dwd_sales_orders d
                LEFT JOIN ods_jst_orders_raw o ON o.order_no = d.order_no
                WHERE d.order_date::date = :dt
                  AND d.order_status <> 'Split'
                  AND (o.raw_json::jsonb->>'type') = '普通订单'
                GROUP BY d.store_id, d.order_date::date
            ), base AS (
                SELECT
                    c.biz_date,
                    c.aavid,
                    c.account_name,
                    c.ad_cost,
                    b.store_id,
                    COALESCE(ps.sale_amount, 0) AS sale_amount,
                    SUM(COALESCE(ps.sale_amount, 0)) OVER (PARTITION BY c.aavid, c.biz_date) AS total_sale,
                    ROW_NUMBER() OVER (PARTITION BY c.aavid, c.biz_date ORDER BY b.store_id) AS rn,
                    COUNT(*) OVER (PARTITION BY c.aavid, c.biz_date) AS cnt
                FROM qianchuan_costs c
                JOIN sales_qianchuan_account_store_bindings b ON b.aavid = c.aavid AND b.enabled = TRUE
                JOIN biz_stores s ON s.id = b.store_id AND s.is_active = TRUE
                LEFT JOIN pay_sales ps ON ps.store_id = b.store_id AND ps.biz_date = c.biz_date
            ), allocated AS (
                SELECT
                    biz_date,
                    store_id,
                    aavid,
                    account_name,
                    CASE
                        WHEN cnt = 1 THEN ad_cost
                        WHEN total_sale > 0 AND rn < cnt THEN ROUND(ad_cost * sale_amount / NULLIF(total_sale, 0), 2)
                        WHEN total_sale > 0 THEN ad_cost - COALESCE(SUM(CASE WHEN rn < cnt THEN ROUND(ad_cost * sale_amount / NULLIF(total_sale, 0), 2) END) OVER (PARTITION BY aavid, biz_date), 0)
                        ELSE COALESCE(ROUND(ad_cost / NULLIF(cnt, 0), 2), 0)
                    END AS ad_cost
                FROM base
            )
            INSERT INTO finance_store_daily_ad_costs
                (biz_date, store_id, ad_cost, remark, updated_by)
            SELECT
                biz_date,
                store_id,
                GREATEST(ad_cost, 0),
                '千川最新采集按绑定店铺分摊 account=' || COALESCE(NULLIF(account_name, ''), aavid) || ' aavid=' || aavid,
                NULL
            FROM allocated
            ON CONFLICT (biz_date, store_id) DO UPDATE SET
                ad_cost    = EXCLUDED.ad_cost,
                remark     = EXCLUDED.remark,
                updated_at = NOW()
        """), {"dt": biz_date})
        total += result.rowcount or 0

    for source in _COLLECTED_AD_COST_SOURCES:
        account_table = source["account_table"]
        cost_table = source["cost_table"]
        if not await _table_exists(db, account_table) or not await _table_exists(db, cost_table):
            continue

        account_key = source["account_key"]
        account_label = source["account_label"]
        platform = source["platform"]
        result = await db.execute(text(f"""
            WITH latest AS (
                SELECT DISTINCT ON (a.store_id)
                    c.biz_date,
                    a.store_id,
                    c.ad_cost,
                    COALESCE(NULLIF(c.account_name, ''), NULLIF(a.account_name, ''), c.{account_key}) AS account_name,
                    c.{account_key} AS account_key,
                    c.captured_at
                FROM {cost_table} c
                JOIN {account_table} a ON a.{account_key} = c.{account_key}
                JOIN biz_stores s ON s.id = a.store_id
                WHERE c.biz_date = :dt
                  AND a.enabled = TRUE
                  AND a.store_id IS NOT NULL
                  AND s.is_active = TRUE
                ORDER BY a.store_id, c.captured_at DESC NULLS LAST, c.updated_at DESC NULLS LAST, c.id DESC
            )
            INSERT INTO finance_store_daily_ad_costs
                (biz_date, store_id, ad_cost, remark, updated_by)
            SELECT
                biz_date,
                store_id,
                ad_cost,
                :platform || '最新采集自动写入 account=' || account_name || ' ' || :account_label || '=' || account_key,
                NULL
            FROM latest
            ON CONFLICT (biz_date, store_id) DO UPDATE SET
                ad_cost    = EXCLUDED.ad_cost,
                remark     = EXCLUDED.remark,
                updated_at = NOW()
        """), {"dt": biz_date, "platform": platform, "account_label": account_label})
        total += result.rowcount or 0
    if total:
        await db.commit()
    return total


@router.get("")
async def list_daily_ad_costs(
    biz_date: date = Query(description="YYYY-MM-DD"),
    platform: str = Query(default=""),
    keyword: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """获取某天所有活跃店铺广告费和赔付维护列表（含当天销售数据）"""
    where_parts = ["s.is_active = true"]
    params: dict = {"dt": biz_date}

    if platform:
        where_parts.append("bp.name ILIKE :platform")
        params["platform"] = f"%{platform}%"
    if keyword:
        where_parts.append("s.store_name ILIKE :keyword")
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(where_parts)

    await _sync_collected_ad_costs_to_finance(db, biz_date)

    rows = await db.execute(text(f"""
        WITH pay_sales AS (
            SELECT
                d.store_id,
                COALESCE(SUM(d.pay_amount), 0) AS sale_amount
            FROM dwd_sales_orders d
            LEFT JOIN ods_jst_orders_raw o ON o.order_no = d.order_no
            WHERE d.order_date::date = :dt
              AND d.order_status <> 'Split'
              AND (o.raw_json::jsonb->>'type') = '普通订单'
            GROUP BY d.store_id
        )
        SELECT
            s.id                                             AS store_id,
            s.store_name,
            COALESCE(bp.name, '')                            AS platform,
            COALESCE(ps.sale_amount, 0)                      AS sale_amount,
            COALESCE(dm.order_count, 0)                      AS order_count,
            COALESCE(dm.shipped_qty, dm.paid_qty, 0)         AS shipped_qty,
            COALESCE(ac.ad_cost, 0)                          AS ad_cost,
            COALESCE(ac.compensation_amount, 0)              AS compensation_amount,
            CASE WHEN ac.id IS NOT NULL THEN true
                 ELSE false END                              AS has_manual_record,
            COALESCE(ac.remark, '')                          AS remark,
            ac.updated_at,
            u.username                                       AS updated_by_name
        FROM biz_stores s
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        LEFT JOIN dm_store_daily dm
               ON dm.store_id = s.id AND dm.biz_date = :dt
        LEFT JOIN pay_sales ps ON ps.store_id = s.id
        LEFT JOIN finance_store_daily_ad_costs ac
               ON ac.store_id = s.id AND ac.biz_date = :dt
        LEFT JOIN sys_users u ON u.id = ac.updated_by
        WHERE {where_sql}
        ORDER BY COALESCE(ps.sale_amount, 0) DESC, s.store_name
    """), params)

    result = []
    for row in rows.mappings():
        d = dict(row)
        sale = float(d["sale_amount"])
        ad   = float(d["ad_cost"])
        comp = float(d["compensation_amount"])
        d["sale_amount"]  = sale
        d["order_count"]  = int(d["order_count"])
        d["shipped_qty"]  = int(d["shipped_qty"])
        d["ad_cost"]      = ad
        d["compensation_amount"] = comp
        d["roi"]          = round(sale / ad, 4) if ad > 0 else None
        d["biz_date"]     = str(biz_date)
        result.append(d)
    return result


@router.get("/platforms")
async def list_platforms(
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """返回所有活跃店铺的平台列表（用于筛选下拉）"""
    rows = await db.execute(text("""
        SELECT DISTINCT COALESCE(bp.name, '') AS platform
        FROM biz_stores s
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        WHERE s.is_active = true
          AND bp.name IS NOT NULL
        ORDER BY platform
    """))
    return [row.platform for row in rows.fetchall()]


@router.post("/batch-save")
async def batch_save_daily_ad_costs(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """批量 UPSERT 某天各店铺广告费和赔付（不影响其他日期）"""
    raw_date = body.get("biz_date")
    items    = body.get("items", [])

    if not raw_date:
        raise HTTPException(status_code=422, detail="biz_date 必填")
    try:
        biz_date: date = date.fromisoformat(str(raw_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="biz_date 格式错误，须为 YYYY-MM-DD")
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="items 须为数组")

    success = 0
    errors: list = []

    for item in items:
        store_id = item.get("store_id")
        if not store_id:
            continue
        try:
            if item.get("clear_record"):
                await db.execute(text("""
                    DELETE FROM finance_store_daily_ad_costs
                    WHERE biz_date = :dt AND store_id = :sid
                """), {"dt": biz_date, "sid": int(store_id)})
                success += 1
                continue

            ad_cost = float(item.get("ad_cost") or 0)
            if ad_cost < 0:
                errors.append({"store_id": store_id, "error": "广告费不能为负数"})
                continue
            compensation_amount = float(item.get("compensation_amount") or 0)
            if compensation_amount < 0:
                errors.append({"store_id": store_id, "error": "发货赔付、其他赔付不能为负数"})
                continue
            remark = item.get("remark") or None
            await db.execute(text("""
                INSERT INTO finance_store_daily_ad_costs
                    (biz_date, store_id, ad_cost, compensation_amount, remark, updated_by)
                VALUES (:dt, :sid, :ad, :compensation, :remark, :uid)
                ON CONFLICT (biz_date, store_id) DO UPDATE SET
                    ad_cost             = EXCLUDED.ad_cost,
                    compensation_amount = EXCLUDED.compensation_amount,
                    remark              = EXCLUDED.remark,
                    updated_by          = EXCLUDED.updated_by,
                    updated_at          = NOW()
            """), {
                "dt": biz_date, "sid": int(store_id),
                "ad": ad_cost, "compensation": compensation_amount, "remark": remark,
                "uid": current_user.id,
            })
            success += 1
        except Exception as e:
            errors.append({"store_id": store_id, "error": str(e)})

    await db.commit()
    return {"ok": len(errors) == 0, "success": success, "errors": errors}
