#!/bin/bash
# Daily Baison inventory sync for Huabang whitelisted stores/warehouses.
set -euo pipefail

BACKEND_DIR="/srv/huabang-ai-center/backend"
LOG_DIR="/srv/huabang-ai-center/logs"
LOG_FILE="$LOG_DIR/sync_inventory_daily.log"
STAT_DATE=$(TZ='Asia/Shanghai' date '+%Y-%m-%d')

mkdir -p "$LOG_DIR"
cd "$BACKEND_DIR"

echo "==========================================" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] start baison inventory sync stat_date=$STAT_DATE" | tee -a "$LOG_FILE"

set +e
HUABANG_INVENTORY_STAT_DATE="$STAT_DATE" PYTHONIOENCODING=utf-8 ./.venv/bin/python - <<'PY_EOF' >> "$LOG_FILE" 2>&1
import asyncio
import json
import os
from datetime import date

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.integrations.baison.services.inventory_service import import_all_inventory


STAT_DATE = date.fromisoformat(os.environ["HUABANG_INVENTORY_STAT_DATE"])


async def main():
    async with AsyncSessionLocal() as db:
        result = await import_all_inventory(db, page_size=100)
        print(json.dumps(result, ensure_ascii=False, default=str))
        if not result.get("ok"):
            raise SystemExit(1)

        batch_no = result["batch_no"]
        allowed = sorted({code.upper() for code in ALLOWED_INVENTORY_CODES})

        cleanup = await db.execute(
            text("""
                WITH deleted_non_whitelist AS (
                    DELETE FROM dwd.dwd_inventory_balance
                    WHERE UPPER(warehouse_code::text) <> ALL(:allowed)
                    RETURNING 1
                ), deleted_stale AS (
                    DELETE FROM dwd.dwd_inventory_balance
                    WHERE UPPER(warehouse_code::text) = ANY(:allowed)
                      AND batch_no <> :batch_no
                    RETURNING 1
                )
                SELECT
                    (SELECT COUNT(*) FROM deleted_non_whitelist) AS deleted_non_whitelist,
                    (SELECT COUNT(*) FROM deleted_stale) AS deleted_stale
            """),
            {"allowed": allowed, "batch_no": batch_no},
        )
        cleanup_row = cleanup.mappings().one()

        await db.execute(
            text("""
                INSERT INTO dws.dws_inventory_daily AS t
                (stat_date, store_code, total_quantity, total_cost_amount,
                 negative_sku_count, sku_count, is_cost_complete, etl_at, created_at)
                SELECT CAST(:stat_date AS date),
                       b.warehouse_code,
                       COALESCE(SUM(GREATEST(b.qty, 0)), 0)::int,
                       COALESCE(SUM(GREATEST(b.qty, 0) * price.standard_purchase_price)
                           FILTER (WHERE price.standard_purchase_price IS NOT NULL), 0),
                       COUNT(*) FILTER (WHERE b.qty < 0)::int,
                       COUNT(DISTINCT COALESCE(NULLIF(b.sku_code, ''), b.product_code, b.barcode))::int,
                       COALESCE(
                           BOOL_AND(price.standard_purchase_price IS NOT NULL)
                               FILTER (WHERE b.qty > 0),
                           true
                       ),
                       now(), now()
                FROM dwd.v_apparel_inventory_balance b
                LEFT JOIN dim.v_baison_sku_standard_purchase_price price
                  ON price.product_code = b.product_code
                 AND TRIM(LEADING '-' FROM price.color_code) =
                     TRIM(LEADING '-' FROM COALESCE(BTRIM(b.color_code::text), ''))
                 AND price.size_code = COALESCE(BTRIM(b.size_code::text), '')
                WHERE UPPER(b.warehouse_code::text) = ANY(:allowed)
                GROUP BY b.warehouse_code
                ON CONFLICT (stat_date, store_code)
                DO UPDATE SET total_quantity = EXCLUDED.total_quantity,
                              total_cost_amount = EXCLUDED.total_cost_amount,
                              negative_sku_count = EXCLUDED.negative_sku_count,
                              sku_count = EXCLUDED.sku_count,
                              is_cost_complete = EXCLUDED.is_cost_complete,
                              etl_at = now()
            """),
            {"allowed": allowed, "stat_date": STAT_DATE},
        )
        await db.commit()

        verify = await db.execute(
            text("""
                SELECT COUNT(*) AS rows,
                       COUNT(DISTINCT warehouse_code) AS warehouses,
                       COALESCE(SUM(qty), 0) AS total_qty,
                       MAX(synced_at) AS max_synced_at
                FROM dwd.dwd_inventory_balance
            """)
        )
        verify_row = verify.mappings().one()
        print(json.dumps({
            "cleanup": dict(cleanup_row),
            "snapshot": {k: str(v) for k, v in dict(verify_row).items()},
        }, ensure_ascii=False, default=str))


asyncio.run(main())
PY_EOF
RC=$?
set -e

if [ $RC -eq 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] inventory sync success rc=$RC" | tee -a "$LOG_FILE"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] inventory sync failed rc=$RC" | tee -a "$LOG_FILE"
  exit $RC
fi
