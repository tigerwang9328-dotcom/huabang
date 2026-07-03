"""百胜门店商品销售同步服务 - pos.storefx.sale_goods_get"""
import json
import hashlib
import logging
import time
import datetime as dt
from typing import Optional

from app.integrations.baison.client import BaisonClient
from app.core.database import AsyncSessionLocal
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, allowed_inventory_sql_in
from sqlalchemy import text

logger = logging.getLogger("baison.pos_sale")


class PosSaleGoodsService:
    """门店商品销售排行/汇总同步"""

    def __init__(self):
        self.client = BaisonClient()
        self.batch_no = dt.datetime.now().strftime("PSG%Y%m%d%H%M%S")

    def _hash(self, raw: dict) -> str:
        s = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(s.encode()).hexdigest()

    async def sync_one_store(
        self, zddm: str, start_date: str, end_date: str, max_pages: int = 0
    ) -> dict:
        """同步单个门店全部销售数据"""
        zddm = str(zddm).strip()
        if zddm not in ALLOWED_INVENTORY_CODES:
            logger.warning("Skip non-whitelisted sale goods store=%s", zddm)
            return {"store": zddm, "ods": 0, "dwd": 0, "pages": 0, "skipped": True}

        total_ods = 0
        total_dwd = 0
        page = 1
        page_size = 20

        while True:
            params = {
                "pageNo": str(page),
                "pageSize": str(page_size),
                "startModified": start_date,
                "endModified": end_date,
                "zddm": zddm,
                "goods_sn": "",
                "is_sku": "0",
            }
            try:
                resp = self.client.request("pos.storefx.sale_goods_get", params)
            except Exception as e:
                logger.error(f"API error store={zddm} page={page}: {e}")
                break

            if resp.data is None:
                logger.warning(f"Empty response store={zddm} page={page}")
                break

            outer_code = str(resp.data.get("code", ""))
            outer_flag = str(resp.data.get("flag", ""))
            if outer_code != "1" or outer_flag != "success":
                logger.error(
                    f"Outer fail store={zddm} page={page} code={outer_code} flag={outer_flag}"
                )
                break

            inner_str = resp.data.get("data", "{}")
            if isinstance(inner_str, str):
                try:
                    inner = json.loads(inner_str)
                except json.JSONDecodeError:
                    logger.error(f"Inner JSON parse fail store={zddm} page={page}")
                    break
            else:
                inner = inner_str

            inner_status = str(inner.get("status", ""))
            inner_flag = str(inner.get("flag", ""))
            if inner_status != "1" or inner_flag != "SUCCESS":
                logger.error(
                    f"Inner fail store={zddm} page={page} status={inner_status}"
                )
                break

            page_data = inner.get("data", {})
            page_info = page_data.get("page", {})
            result = page_data.get("result", [])
            page_total = int(page_info.get("pageTotal", 0))

            if not result:
                break

            ods_count, dwd_count = await self._save_batch(
                zddm, result, start_date, end_date, page
            )
            total_ods += ods_count
            total_dwd += dwd_count

            page += 1
            if max_pages > 0 and page > max_pages:
                logger.info(f"Reached max_pages={max_pages} for store={zddm}")
                break
            if page > page_total:
                break
            time.sleep(0.2)  # rate limit

        return {
            "store": zddm,
            "ods": total_ods,
            "dwd": total_dwd,
            "pages": page - 1,
        }

    async def sync_multiple_stores(
        self, stores: list, start_date: str, end_date: str, max_pages: int = 0
    ) -> dict:
        results = []
        requested = [str(zddm).strip() for zddm in stores]
        skipped = [zddm for zddm in requested if zddm not in ALLOWED_INVENTORY_CODES]
        if skipped:
            logger.warning("Skip non-whitelisted sale goods stores=%s", skipped)

        for zddm in requested:
            if zddm not in ALLOWED_INVENTORY_CODES:
                results.append({"store": zddm, "ods": 0, "dwd": 0, "pages": 0, "skipped": True})
                continue
            r = await self.sync_one_store(zddm, start_date, end_date, max_pages)
            results.append(r)
            logger.info(f"Store {zddm} done: {r}")
        total_ods = sum(r["ods"] for r in results)
        total_dwd = sum(r["dwd"] for r in results)
        return {"stores": len(requested), "skipped": len(skipped), "ods": total_ods, "dwd": total_dwd, "details": results}


    async def _save_batch(
        self, zddm: str, records: list, start_date: str, end_date: str, page_no: int
    ):
        """批量写入 ODS + DWD"""
        zddm = str(zddm).strip()
        if zddm not in ALLOWED_INVENTORY_CODES:
            logger.warning("Reject non-whitelisted sale goods batch store=%s", zddm)
            return 0, 0

        bs_dt = dt.datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        be_dt = dt.datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        biz_d = be_dt.date()
        async with AsyncSessionLocal() as db:
            ods_count = 0
            dwd_count = 0
            for rec in records:
                source_hash = self._hash(rec)
                # ODS insert
                await db.execute(
                    text(
                        """INSERT INTO ods.ods_baison_pos_sale_goods_api
                        (batch_no, store_code, product_code, sku_code, raw_data, source_hash,
                         biz_start_time, biz_end_time, page_no, synced_at, created_at, updated_at)
                        VALUES (:bn, :sc, :pc, :sk, CAST(:rd AS jsonb), :sh, :bs, :be, :pn, now(), now(), now())"""
                    ),
                    {
                        "bn": self.batch_no, "sc": zddm,
                        "pc": str(rec.get("goods_sn", "")),
                        "sk": str(rec.get("sku", "")),
                        "rd": json.dumps(rec, ensure_ascii=False),
                        "sh": source_hash,
                        "bs": bs_dt, "be": be_dt, "pn": page_no,
                    },
                )
                ods_count += 1

                # DWD insert
                sl = float(rec.get("SL") or 0)
                je = float(rec.get("JE") or 0)
                bzje = float(rec.get("BZJE") or 0)
                ckj = float(rec.get("CKJ") or 0)
                kc = float(rec.get("kc_sl")) if rec.get("kc_sl") is not None else None
                disc = round(je / bzje, 4) if bzje > 0 else None

                await db.execute(
                    text(
                        """INSERT INTO dwd.dwd_pos_sale_goods
                        (biz_date, store_code, product_code, sku_code, product_name, goods_id,
                         category_code, category_name, brand_code, brand_name, outer_product_code,
                         sales_qty, sales_amount, standard_amount, discount_rate, tag_price,
                         stock_qty_snapshot, batch_no, synced_at, created_at, updated_at)
                        VALUES (:bd, :sc, :pc, :sk, :pn, :gi, :cc, :cn, :bc, :bn, :opc,
                                :sq, :sa, :st, :dr, :tp, :ks, :bno, now(), now(), now())
                        ON CONFLICT (biz_date, store_code, COALESCE(product_code, ''), COALESCE(sku_code, ''))
                        DO UPDATE SET sales_qty = EXCLUDED.sales_qty,
                           sales_amount = EXCLUDED.sales_amount,
                           standard_amount = EXCLUDED.standard_amount,
                           discount_rate = EXCLUDED.discount_rate,
                           stock_qty_snapshot = EXCLUDED.stock_qty_snapshot,
                           batch_no = EXCLUDED.batch_no, updated_at = now()"""
                    ),
                    {
                        "bd": biz_d, "sc": zddm,
                        "pc": str(rec.get("goods_sn", "")),
                        "sk": str(rec.get("sku", "")),
                        "pn": str(rec.get("goods_name", "")),
                        "gi": str(rec.get("goods_id", "")),
                        "cc": str(rec.get("cat_code", "")),
                        "cn": str(rec.get("cat_name", "")),
                        "bc": str(rec.get("brand_code", "")),
                        "bn": str(rec.get("brand_name", "")),
                        "opc": str(rec.get("outer_goods_sn", "")),
                        "sq": sl, "sa": je, "st": bzje, "dr": disc,
                        "tp": ckj, "ks": kc, "bno": self.batch_no,
                    },
                )
                dwd_count += 1

            await db.commit()
            return ods_count, dwd_count

    async def rebuild_dws_summary(self, start_date: str, end_date: str) -> dict:
            """重建 DWS/DM 层汇总（匹配当前 dws 表结构）。"""
            params = {"sd": dt.date.fromisoformat(start_date[:10]), "ed": dt.date.fromisoformat(end_date[:10])}
            # 华邦业务口径:销售明细仅统计 10 个白名单门店/仓,见 app.core.store_whitelist
            store_in = allowed_inventory_sql_in()
            async with AsyncSessionLocal() as db:
                # 公司日汇总 -> dws_company_daily
                await db.execute(
                    text(f"""
                        INSERT INTO dws.dws_company_daily AS t
                        (stat_date, total_sales_amount, total_item_count, total_order_count,
                         net_sales_amount, offline_sales_amount, online_sales_amount,
                         avg_discount_rate, etl_at, created_at)
                        SELECT biz_date,
                               COALESCE(SUM(sales_amount), 0),
                               COALESCE(SUM(sales_qty), 0),
                               NULL,
                               COALESCE(SUM(sales_amount), 0),
                               COALESCE(SUM(sales_amount), 0),
                               0,
                               CASE WHEN SUM(standard_amount) > 0
                                    THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                                    ELSE NULL END,
                               now(), now()
                        FROM dwd.dwd_pos_sale_goods
                        WHERE biz_date >= :sd AND biz_date <= :ed
                          AND store_code IN {store_in}
                        GROUP BY biz_date
                        ON CONFLICT (stat_date)
                        DO UPDATE SET total_sales_amount = EXCLUDED.total_sales_amount,
                           total_item_count = EXCLUDED.total_item_count,
                           net_sales_amount = EXCLUDED.net_sales_amount,
                           offline_sales_amount = EXCLUDED.offline_sales_amount,
                           online_sales_amount = EXCLUDED.online_sales_amount,
                           avg_discount_rate = EXCLUDED.avg_discount_rate,
                           etl_at = now()"""),
                    params,
                )

                # 门店日汇总 -> dws_store_daily，百胜 POS 口径暂归 offline
                await db.execute(
                    text(f"""
                        INSERT INTO dws.dws_store_daily AS t
                        (stat_date, store_code, channel, item_count, net_item_count,
                         sales_amount, net_sales_amount, order_count,
                         avg_order_value, items_per_order, avg_discount_rate, etl_at, created_at)
                        SELECT biz_date, store_code, 'offline',
                               COALESCE(SUM(sales_qty), 0),
                               COALESCE(SUM(sales_qty), 0),
                               COALESCE(SUM(sales_amount), 0),
                               COALESCE(SUM(sales_amount), 0),
                               NULL,
                               NULL, NULL,
                               CASE WHEN SUM(standard_amount) > 0
                                    THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                                    ELSE NULL END,
                               now(), now()
                        FROM dwd.dwd_pos_sale_goods
                        WHERE biz_date >= :sd AND biz_date <= :ed
                          AND store_code IN {store_in}
                        GROUP BY biz_date, store_code
                        ON CONFLICT (stat_date, store_code, channel)
                        DO UPDATE SET item_count = EXCLUDED.item_count,
                           net_item_count = EXCLUDED.net_item_count,
                           sales_amount = EXCLUDED.sales_amount,
                           net_sales_amount = EXCLUDED.net_sales_amount,
                           avg_discount_rate = EXCLUDED.avg_discount_rate,
                           etl_at = now()"""),
                    params,
                )

                # 商品日汇总 -> dws_product_daily，按门店+商品汇总
                await db.execute(
                    text(f"""
                        INSERT INTO dws.dws_product_daily AS t
                        (stat_date, product_code, store_code, sales_quantity, net_quantity,
                         sales_amount, net_sales_amount, avg_discount_rate, etl_at, created_at)
                        SELECT biz_date, product_code, store_code,
                               COALESCE(SUM(sales_qty), 0),
                               COALESCE(SUM(sales_qty), 0),
                               COALESCE(SUM(sales_amount), 0),
                               COALESCE(SUM(sales_amount), 0),
                               CASE WHEN SUM(standard_amount) > 0
                                    THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                                    ELSE NULL END,
                               now(), now()
                        FROM dwd.dwd_pos_sale_goods
                        WHERE biz_date >= :sd AND biz_date <= :ed
                          AND store_code IN {store_in}
                        GROUP BY biz_date, product_code, store_code
                        ON CONFLICT (stat_date, product_code, store_code)
                        DO UPDATE SET sales_quantity = EXCLUDED.sales_quantity,
                           net_quantity = EXCLUDED.net_quantity,
                           sales_amount = EXCLUDED.sales_amount,
                           net_sales_amount = EXCLUDED.net_sales_amount,
                           avg_discount_rate = EXCLUDED.avg_discount_rate,
                           etl_at = now()"""),
                    params,
                )

                await db.commit()

                result = await db.execute(
                    text(f"""
                        SELECT
                            (SELECT COALESCE(SUM(sales_amount),0) FROM dwd.dwd_pos_sale_goods WHERE biz_date >= :sd AND biz_date <= :ed AND store_code IN {store_in}) as total_sales,
                            (SELECT COALESCE(SUM(sales_qty),0) FROM dwd.dwd_pos_sale_goods WHERE biz_date >= :sd AND biz_date <= :ed AND store_code IN {store_in}) as total_qty,
                            (SELECT COUNT(DISTINCT store_code) FROM dwd.dwd_pos_sale_goods WHERE biz_date >= :sd AND biz_date <= :ed AND store_code IN {store_in}) as store_cnt,
                            (SELECT COUNT(DISTINCT product_code) FROM dwd.dwd_pos_sale_goods WHERE biz_date >= :sd AND biz_date <= :ed AND store_code IN {store_in}) as product_cnt,
                            (SELECT COUNT(*) FROM dws.dws_company_daily WHERE stat_date >= :sd AND stat_date <= :ed AND total_sales_amount IS NOT NULL) as company_rows"""),
                    params,
                )
                row = result.fetchone()
                return {
                    "total_sales": float(row[0]),
                    "total_qty": float(row[1]),
                    "store_count": int(row[2]),
                    "product_count": int(row[3]),
                    "company_daily_rows": int(row[4]),
                }
