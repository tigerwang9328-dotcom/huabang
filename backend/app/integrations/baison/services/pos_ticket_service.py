"""百胜 POS 小票流水同步服务 - pos.qtlsd.list_get.

用途：接入真实小票/订单流水，补齐经营概览中的订单数、客单价、件单数，
并替代 pos.storefx.sale_goods_get 销售排行在日销核心指标中的错误口径。
"""
import datetime as dt
import hashlib
import json
import logging
import time
from collections import defaultdict
from typing import Optional

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.store_whitelist import (
    ACTUAL_PAY_CODES,
    allowed_store_sql_in,
)
from app.integrations.baison.client import BaisonClient

logger = logging.getLogger("baison.pos_ticket")

TICKET_METHOD = "pos.qtlsd.list_get"
DEPOSIT_METHOD = "crm.vip.get_deposit_list"
SALES_PAY_CODES = ACTUAL_PAY_CODES
BASE_RECEIPT_PAY_CODES = frozenset({"000", "011", "666", "971"})
RECHARGE_PAY_CODES = frozenset()


class PosTicketService:
    """小票流水同步：ODS 保留原始小票，DWD 存小票级聚合。"""

    def __init__(self):
        self.client = BaisonClient()
        self.batch_no = dt.datetime.now().strftime("PT%Y%m%d%H%M%S")

    def _hash(self, raw: dict) -> str:
        s = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.md5(s.encode()).hexdigest()

    def _parse_biz_date(self, rec: dict, fallback: dt.date) -> dt.date:
        raw = rec.get("yyrq") or rec.get("rq") or rec.get("zdrq")
        if raw:
            for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return dt.datetime.strptime(str(raw), fmt).date()
                except ValueError:
                    pass
        return fallback

    @staticmethod
    def _f(value) -> float:
        try:
            if value in (None, ""):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    async def ensure_tables(self) -> None:
        """创建小票 ODS/DWD 表。生产迁移遗漏时也能自愈。"""
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS ods.ods_baison_pos_ticket_api (
                    id BIGSERIAL PRIMARY KEY,
                    batch_no VARCHAR(64) NOT NULL,
                    source_system VARCHAR(32) DEFAULT 'baison',
                    api_method VARCHAR(64) DEFAULT 'pos.qtlsd.list_get',
                    ticket_no VARCHAR(80) NOT NULL,
                    store_code VARCHAR(64),
                    biz_date DATE,
                    raw_data JSONB NOT NULL,
                    source_hash VARCHAR(64),
                    biz_start_time TIMESTAMP,
                    biz_end_time TIMESTAMP,
                    page_no INTEGER DEFAULT 1,
                    synced_at TIMESTAMP DEFAULT now(),
                    created_at TIMESTAMP DEFAULT now(),
                    updated_at TIMESTAMP DEFAULT now()
                )
            """))
            await db.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ods_baison_pos_ticket_api_ticket
                ON ods.ods_baison_pos_ticket_api(ticket_no, source_system)
            """))
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS dwd.dwd_pos_ticket (
                    id BIGSERIAL PRIMARY KEY,
                    source_system VARCHAR(32) DEFAULT 'baison',
                    biz_date DATE NOT NULL,
                    ticket_no VARCHAR(80) NOT NULL,
                    store_code VARCHAR(64),
                    store_name VARCHAR(256),
                    customer_code VARCHAR(80),
                    vip_code VARCHAR(80),
                    sales_qty NUMERIC(16,4),
                    sales_amount NUMERIC(16,2),
                    standard_amount NUMERIC(16,2),
                    gross_profit_source_amount NUMERIC(16,2),
                    discount_rate NUMERIC(10,4),
                    detail_count INTEGER,
                    is_void BOOLEAN DEFAULT false,
                    is_pending BOOLEAN DEFAULT false,
                    batch_no VARCHAR(64),
                    raw_ref_id BIGINT,
                    raw_data JSONB,
                    synced_at TIMESTAMP DEFAULT now(),
                    created_at TIMESTAMP DEFAULT now(),
                    updated_at TIMESTAMP DEFAULT now()
                )
            """))
            await db.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_dwd_pos_ticket_ticket
                ON dwd.dwd_pos_ticket(ticket_no, source_system)
            """))
            await db.execute(text("CREATE INDEX IF NOT EXISTS idx_dwd_pos_ticket_biz_date ON dwd.dwd_pos_ticket(biz_date)"))
            await db.execute(text("CREATE INDEX IF NOT EXISTS idx_dwd_pos_ticket_store_date ON dwd.dwd_pos_ticket(store_code, biz_date)"))
            # 兼容旧表:补充 actual_pay_amount 列(门店销售实收口径)
            await db.execute(text(
                "ALTER TABLE dwd.dwd_pos_ticket ADD COLUMN IF NOT EXISTS actual_pay_amount NUMERIC(16,2) DEFAULT 0"
            ))
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS dwd.dwd_store_recharge_daily (
                    biz_date DATE NOT NULL,
                    store_code VARCHAR(64) NOT NULL,
                    recharge_amount NUMERIC(16, 2) NOT NULL DEFAULT 0,
                    source VARCHAR(64) NOT NULL DEFAULT 'baison_deposit',
                    note TEXT,
                    created_at TIMESTAMP DEFAULT now(),
                    updated_at TIMESTAMP DEFAULT now(),
                    PRIMARY KEY (biz_date, store_code, source)
                )
            """))
            await db.commit()

    async def sync_range(self, start_time: str, end_time: str, max_pages: int = 0, page_size: int = 100) -> dict:
        """按时间范围同步小票列表。start/end 格式：YYYY-mm-dd HH:MM:SS。"""
        await self.ensure_tables()
        start_dt = dt.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = dt.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        fallback_date = end_dt.date()
        page = 1
        total_ods = 0
        total_dwd = 0
        total_result: Optional[int] = None
        page_total = 1

        while True:
            params = {
                "pageNo": str(page),
                "pageSize": str(page_size),
                "startModified": start_time,
                "endModified": end_time,
                "zf": "0",
                "gd": "0",
            }
            try:
                resp = self.client.request(TICKET_METHOD, params, timeout=30)
            except Exception as exc:
                logger.error("ticket api error page=%s err=%s", page, exc)
                break

            if not resp.data or str(resp.data.get("code")) != "1":
                logger.error("ticket api failed page=%s raw=%s", page, resp.raw_response[:500])
                break

            inner = resp.data.get("data") or "{}"
            if isinstance(inner, str):
                inner = json.loads(inner)
            page_info = inner.get("page") or {}
            rows = inner.get("orderListGet") or []
            page_total = int(page_info.get("pageTotal") or 1)
            total_result = int(page_info.get("totalResult") or len(rows))

            if not rows:
                break

            ods_count, dwd_count = await self._save_batch(rows, start_dt, end_dt, fallback_date, page)
            total_ods += ods_count
            total_dwd += dwd_count

            if page >= page_total:
                break
            if max_pages > 0 and page >= max_pages:
                break
            page += 1
            time.sleep(0.15)

        summary = await self.rebuild_dws_summary(start_time, end_time)
        return {
            "ok": True,
            "method": TICKET_METHOD,
            "batch_no": self.batch_no,
            "pages": page,
            "page_total": page_total,
            "total_result": total_result,
            "ods": total_ods,
            "dwd": total_dwd,
            "summary": summary,
        }

    async def _save_batch(self, rows: list[dict], start_dt: dt.datetime, end_dt: dt.datetime, fallback_date: dt.date, page_no: int) -> tuple[int, int]:
        async with AsyncSessionLocal() as db:
            ods_count = 0
            dwd_count = 0
            for rec in rows:
                ticket_no = str(rec.get("djbh") or rec.get("lsdh") or "").strip()
                if not ticket_no:
                    continue
                store_code = str(rec.get("zddm") or "").strip()
                biz_date = self._parse_biz_date(rec, fallback_date)
                source_hash = self._hash(rec)
                raw_json = json.dumps(rec, ensure_ascii=False, default=str)

                inserted = await db.execute(text("""
                    INSERT INTO ods.ods_baison_pos_ticket_api
                    (batch_no, source_system, api_method, ticket_no, store_code, biz_date, raw_data,
                     source_hash, biz_start_time, biz_end_time, page_no, synced_at, created_at, updated_at)
                    VALUES (:batch_no, 'baison', :api_method, :ticket_no, :store_code, :biz_date,
                            CAST(:raw_data AS jsonb), :source_hash, :start_dt, :end_dt, :page_no, now(), now(), now())
                    ON CONFLICT (ticket_no, source_system)
                    DO UPDATE SET raw_data = EXCLUDED.raw_data,
                                  source_hash = EXCLUDED.source_hash,
                                  batch_no = EXCLUDED.batch_no,
                                  store_code = EXCLUDED.store_code,
                                  biz_date = EXCLUDED.biz_date,
                                  biz_start_time = EXCLUDED.biz_start_time,
                                  biz_end_time = EXCLUDED.biz_end_time,
                                  page_no = EXCLUDED.page_no,
                                  synced_at = now(),
                                  updated_at = now()
                    RETURNING id
                """), {
                    "batch_no": self.batch_no,
                    "api_method": TICKET_METHOD,
                    "ticket_no": ticket_no,
                    "store_code": store_code,
                    "biz_date": biz_date,
                    "raw_data": raw_json,
                    "source_hash": source_hash,
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "page_no": page_no,
                })
                raw_id = inserted.scalar()
                ods_count += 1

                djs_mx = rec.get("qtlsdjs_mx") or []
                if isinstance(djs_mx, str):
                    try:
                        djs_mx = json.loads(djs_mx)
                    except (json.JSONDecodeError, TypeError):
                        djs_mx = []
                sales_qty = self._f(rec.get("sl"))
                raw_sales_amount = self._f(rec.get("sfje") if rec.get("sfje") not in (None, "") else rec.get("je"))
                sales_amount = sum(
                    amount
                    for p in djs_mx
                    if str(p.get("jsdm") or "") in SALES_PAY_CODES
                    for amount in [self._f(p.get("je"))]
                    if amount > 0
                ) if djs_mx else raw_sales_amount
                standard_amount = self._f(rec.get("bzje"))
                gross_profit_source_amount = self._f(rec.get("mlje"))
                details = rec.get("orderDetailGets") or []
                discount_rate = round(sales_amount / standard_amount, 4) if standard_amount > 0 else None
                is_void = str(rec.get("zf") or "0") == "1"
                is_pending = str(rec.get("gd") or "0") == "1"

                # 实收金额口径:收钱吧POS/扫码/胜券扫 + 现金 + 线上支付 + 充值金额 - 退款金额。
                actual_pay_amount = 0.0
                for p in djs_mx:
                    code = str(p.get("jsdm") or "")
                    amount = self._f(p.get("je"))
                    if code in BASE_RECEIPT_PAY_CODES and amount > 0:
                        actual_pay_amount += amount
                    elif code in RECHARGE_PAY_CODES and amount > 0:
                        actual_pay_amount += amount
                    elif code in ACTUAL_PAY_CODES and amount < 0:
                        actual_pay_amount += amount

                await db.execute(text("""
                    INSERT INTO dwd.dwd_pos_ticket
                    (source_system, biz_date, ticket_no, store_code, store_name, customer_code, vip_code,
                     sales_qty, sales_amount, standard_amount, gross_profit_source_amount, discount_rate,
                     detail_count, is_void, is_pending, batch_no, raw_ref_id, raw_data, actual_pay_amount,
                     synced_at, created_at, updated_at)
                    VALUES ('baison', :biz_date, :ticket_no, :store_code, :store_name, :customer_code, :vip_code,
                            :sales_qty, :sales_amount, :standard_amount, :gross_profit_source_amount, :discount_rate,
                            :detail_count, :is_void, :is_pending, :batch_no, :raw_ref_id, CAST(:raw_data AS jsonb),
                            :actual_pay_amount, now(), now(), now())
                    ON CONFLICT (ticket_no, source_system)
                    DO UPDATE SET biz_date = EXCLUDED.biz_date,
                                  store_code = EXCLUDED.store_code,
                                  store_name = EXCLUDED.store_name,
                                  customer_code = EXCLUDED.customer_code,
                                  vip_code = EXCLUDED.vip_code,
                                  sales_qty = EXCLUDED.sales_qty,
                                  sales_amount = EXCLUDED.sales_amount,
                                  standard_amount = EXCLUDED.standard_amount,
                                  gross_profit_source_amount = EXCLUDED.gross_profit_source_amount,
                                  discount_rate = EXCLUDED.discount_rate,
                                  detail_count = EXCLUDED.detail_count,
                                  is_void = EXCLUDED.is_void,
                                  is_pending = EXCLUDED.is_pending,
                                  batch_no = EXCLUDED.batch_no,
                                  raw_ref_id = EXCLUDED.raw_ref_id,
                                  raw_data = EXCLUDED.raw_data,
                                  actual_pay_amount = EXCLUDED.actual_pay_amount,
                                  synced_at = now(),
                                  updated_at = now()
                """), {
                    "biz_date": biz_date,
                    "ticket_no": ticket_no,
                    "store_code": store_code,
                    "store_name": rec.get("zdmc"),
                    "customer_code": rec.get("gkdm"),
                    "vip_code": rec.get("vpdm"),
                    "sales_qty": sales_qty,
                    "sales_amount": sales_amount,
                    "standard_amount": standard_amount,
                    "gross_profit_source_amount": gross_profit_source_amount,
                    "discount_rate": discount_rate,
                    "detail_count": len(details),
                    "is_void": is_void,
                    "is_pending": is_pending,
                    "batch_no": self.batch_no,
                    "raw_ref_id": raw_id,
                    "raw_data": raw_json,
                    "actual_pay_amount": actual_pay_amount,
                })
                dwd_count += 1

            await db.commit()
            return ods_count, dwd_count

    async def rebuild_dws_summary(self, start_time: str, end_time: str) -> dict:
        start_date = dt.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").date()
        end_date = dt.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").date()
        params = {"sd": start_date, "ed": end_date}
        # 华邦业务口径:销售/收款仅统计白名单门店,仓库不进入销售口径。
        store_in = allowed_store_sql_in()
        recharge_by_date, recharge_by_store_date = self._fetch_recharge_amounts(start_time, end_time)
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"""
                INSERT INTO dws.dws_company_daily AS t
                (stat_date, total_sales_amount, offline_sales_amount, online_sales_amount,
                 total_order_count, total_item_count, net_sales_amount, avg_order_value,
                 items_per_order, avg_discount_rate, active_store_count, etl_at, created_at)
                SELECT biz_date,
                       COALESCE(SUM(sales_amount), 0),
                       COALESCE(SUM(sales_amount), 0),
                       0,
                       COUNT(*)::int,
                       COALESCE(SUM(sales_qty), 0)::int,
                       COALESCE(SUM(sales_amount), 0),
                       CASE WHEN COUNT(*) > 0 THEN ROUND((SUM(sales_amount) / COUNT(*))::numeric, 2) ELSE NULL END,
                       CASE WHEN COUNT(*) > 0 THEN ROUND((SUM(sales_qty) / COUNT(*))::numeric, 2) ELSE NULL END,
                       CASE WHEN SUM(standard_amount) > 0 THEN ROUND((SUM(sales_amount) / SUM(standard_amount))::numeric, 4) ELSE NULL END,
                       COUNT(DISTINCT store_code)::int,
                       now(), now()
                FROM dwd.dwd_pos_ticket
                WHERE biz_date >= :sd AND biz_date <= :ed
                  AND COALESCE(is_void, false) = false
                  AND COALESCE(is_pending, false) = false
                  AND store_code IN {store_in}
                GROUP BY biz_date
                ON CONFLICT (stat_date)
                DO UPDATE SET total_sales_amount = EXCLUDED.total_sales_amount,
                              offline_sales_amount = EXCLUDED.offline_sales_amount,
                              online_sales_amount = EXCLUDED.online_sales_amount,
                              total_order_count = EXCLUDED.total_order_count,
                              total_item_count = EXCLUDED.total_item_count,
                              net_sales_amount = EXCLUDED.net_sales_amount,
                              avg_order_value = EXCLUDED.avg_order_value,
                              items_per_order = EXCLUDED.items_per_order,
                              avg_discount_rate = EXCLUDED.avg_discount_rate,
                              active_store_count = EXCLUDED.active_store_count,
                              etl_at = now()
            """), params)
            await db.execute(text(f"""
                INSERT INTO dws.dws_store_daily AS t
                (stat_date, store_code, channel, order_count, item_count, net_item_count,
                 tag_amount, sales_amount, net_sales_amount, avg_order_value, items_per_order,
                 avg_discount_rate, etl_at, created_at)
                SELECT biz_date, store_code, 'offline',
                       COUNT(*)::int,
                       COALESCE(SUM(sales_qty), 0)::int,
                       COALESCE(SUM(sales_qty), 0)::int,
                       COALESCE(SUM(standard_amount), 0),
                       COALESCE(SUM(sales_amount), 0),
                       COALESCE(SUM(sales_amount), 0),
                       CASE WHEN COUNT(*) > 0 THEN ROUND((SUM(sales_amount) / COUNT(*))::numeric, 2) ELSE NULL END,
                       CASE WHEN COUNT(*) > 0 THEN ROUND((SUM(sales_qty) / COUNT(*))::numeric, 2) ELSE NULL END,
                       CASE WHEN SUM(standard_amount) > 0 THEN ROUND((SUM(sales_amount) / SUM(standard_amount))::numeric, 4) ELSE NULL END,
                       now(), now()
                FROM dwd.dwd_pos_ticket
                WHERE biz_date >= :sd AND biz_date <= :ed
                  AND COALESCE(is_void, false) = false
                  AND COALESCE(is_pending, false) = false
                  AND store_code IN {store_in}
                GROUP BY biz_date, store_code
                ON CONFLICT (stat_date, store_code, channel)
                DO UPDATE SET order_count = EXCLUDED.order_count,
                              item_count = EXCLUDED.item_count,
                              net_item_count = EXCLUDED.net_item_count,
                              tag_amount = EXCLUDED.tag_amount,
                              sales_amount = EXCLUDED.sales_amount,
                              net_sales_amount = EXCLUDED.net_sales_amount,
                              avg_order_value = EXCLUDED.avg_order_value,
                              items_per_order = EXCLUDED.items_per_order,
                              avg_discount_rate = EXCLUDED.avg_discount_rate,
                              etl_at = now()
            """), params)
            await db.execute(text("""
                DELETE FROM dwd.dwd_store_recharge_daily
                WHERE biz_date >= :sd AND biz_date <= :ed
                  AND source = 'baison_deposit'
            """), params)
            for (biz_date, store_code), amount in recharge_by_store_date.items():
                await db.execute(text("""
                    INSERT INTO dwd.dwd_store_recharge_daily AS t
                    (biz_date, store_code, recharge_amount, source, note, created_at, updated_at)
                    VALUES (:biz_date, :store_code, :amount, 'baison_deposit', 'crm.vip.get_deposit_list change_type=0', now(), now())
                    ON CONFLICT (biz_date, store_code, source)
                    DO UPDATE SET recharge_amount = EXCLUDED.recharge_amount,
                                  note = EXCLUDED.note,
                                  updated_at = now()
                """), {
                    "biz_date": biz_date,
                    "store_code": store_code,
                    "amount": amount,
                })
            for biz_date, amount in recharge_by_date.items():
                await db.execute(text("""
                    UPDATE dws.dws_company_daily
                    SET total_sales_amount = COALESCE(total_sales_amount, 0) + :amount,
                        offline_sales_amount = COALESCE(offline_sales_amount, 0) + :amount,
                        net_sales_amount = COALESCE(net_sales_amount, 0) + :amount,
                        avg_order_value = CASE
                            WHEN COALESCE(total_order_count, 0) > 0
                            THEN ROUND(((COALESCE(total_sales_amount, 0) + :amount) / total_order_count)::numeric, 2)
                            ELSE NULL END,
                        etl_at = now()
                    WHERE stat_date = :biz_date
                """), {"biz_date": biz_date, "amount": amount})
            for (biz_date, store_code), amount in recharge_by_store_date.items():
                await db.execute(text("""
                    UPDATE dws.dws_store_daily
                    SET sales_amount = COALESCE(sales_amount, 0) + :amount,
                        net_sales_amount = COALESCE(net_sales_amount, 0) + :amount,
                        avg_order_value = CASE
                            WHEN COALESCE(order_count, 0) > 0
                            THEN ROUND(((COALESCE(sales_amount, 0) + :amount) / order_count)::numeric, 2)
                            ELSE NULL END,
                        etl_at = now()
                    WHERE stat_date = :biz_date
                      AND store_code = :store_code
                      AND channel = 'offline'
                """), {
                    "biz_date": biz_date,
                    "store_code": store_code,
                    "amount": amount,
                })
            await db.commit()
            result = await db.execute(text(f"""
                SELECT COALESCE(SUM(sales_amount),0) AS total_sales,
                       COALESCE(SUM(sales_qty),0) AS total_qty,
                       COUNT(*) AS total_orders,
                       COUNT(DISTINCT store_code) AS store_count
                FROM dwd.dwd_pos_ticket
                WHERE biz_date >= :sd AND biz_date <= :ed
                  AND COALESCE(is_void, false) = false
                  AND COALESCE(is_pending, false) = false
                  AND store_code IN {store_in}
            """), params)
            row = result.mappings().one()
            recharge_total = sum(recharge_by_date.values())
            return {
                "total_sales": float(row["total_sales"] or 0) + recharge_total,
                "recharge_amount": recharge_total,
                "total_qty": float(row["total_qty"] or 0),
                "total_orders": int(row["total_orders"] or 0),
                "store_count": int(row["store_count"] or 0),
            }

    def _fetch_recharge_amounts(
        self,
        start_time: str,
        end_time: str,
    ) -> tuple[dict[dt.date, float], dict[tuple[dt.date, str], float]]:
        """拉取当日充值(change_type=0),供实收/经营口径额外计入。"""
        allowed_stores = {
            item.strip("'")
            for item in allowed_store_sql_in().strip("()").split(",")
            if item.strip("'")
        }
        by_date: defaultdict[dt.date, float] = defaultdict(float)
        by_store_date: defaultdict[tuple[dt.date, str], float] = defaultdict(float)
        page = 1
        page_size = 100
        fetched = 0
        total: int | None = None

        while True:
            params = {
                "pageNum": str(page),
                "num": str(page_size),
                "start_time": start_time,
                "end_time": end_time,
            }
            try:
                resp = self.client.request(DEPOSIT_METHOD, params, timeout=30)
            except Exception as exc:
                logger.error("deposit api error page=%s err=%s", page, exc)
                break
            if not resp.data or str(resp.data.get("code")) != "1":
                logger.error("deposit api failed page=%s raw=%s", page, resp.raw_response[:500])
                break
            inner = resp.data.get("data") or "{}"
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except (json.JSONDecodeError, TypeError):
                    logger.error("deposit api bad json page=%s raw=%s", page, resp.raw_response[:500])
                    break
            rows = inner.get("data") if isinstance(inner, dict) else []
            rows = rows or []
            if not rows:
                break
            if total is None:
                total = int(self._f(rows[0].get("tCount")))
            for rec in rows:
                store_code = str(rec.get("shop_code") or "").strip()
                if store_code not in allowed_stores:
                    continue
                if str(rec.get("change_type") or "") != "0":
                    continue
                amount = self._f(rec.get("ZJE") or rec.get("money_change"))
                if amount <= 0:
                    continue
                biz_date = self._parse_deposit_date(rec)
                by_date[biz_date] += amount
                by_store_date[(biz_date, store_code)] += amount

            fetched += len(rows)
            if total is not None and fetched >= total:
                break
            page += 1
            if page > 1000:
                logger.error("deposit api stopped: too many pages fetched=%s", fetched)
                break
            time.sleep(0.15)
        return dict(by_date), dict(by_store_date)

    def _parse_deposit_date(self, rec: dict) -> dt.date:
        raw = rec.get("init_time") or rec.get("is_add_time")
        if raw:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d"):
                try:
                    return dt.datetime.strptime(str(raw), fmt).date()
                except ValueError:
                    pass
        return dt.date.today()
