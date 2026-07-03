#!/bin/bash
# Daily Baison master-data sync: shops, warehouses, products, and SKUs.
set -euo pipefail

BACKEND_DIR="/srv/huabang-ai-center/backend"
LOG_DIR="/srv/huabang-ai-center/logs"
LOG_FILE="$LOG_DIR/sync_master_daily.log"

mkdir -p "$LOG_DIR"
cd "$BACKEND_DIR"

echo "==========================================" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] start baison master sync" | tee -a "$LOG_FILE"

set +e
PYTHONIOENCODING=utf-8 ./.venv/bin/python - <<'PY_EOF' >> "$LOG_FILE" 2>&1
import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.integrations.baison.services.product_service import import_all_goods
from app.integrations.baison.services.shop_service import import_all_shops
from app.integrations.baison.services.sku_service import import_all_skus
from app.integrations.baison.services.warehouse_service import import_all_warehouses


async def run_step(name, fn, *args, **kwargs):
    async with AsyncSessionLocal() as db:
        result = await fn(db, *args, **kwargs)
        if result.get("ok"):
            await db.commit()
        else:
            try:
                await db.commit()
            except Exception:
                await db.rollback()
        print(json.dumps({"step": name, **result}, ensure_ascii=False, default=str))
        if not result.get("ok"):
            raise RuntimeError(f"{name} failed: {result.get('error') or result.get('message')}")
        return result


async def main():
    results = []
    results.append(await run_step("shop", import_all_shops, page_size=100))
    results.append(await run_step("warehouse", import_all_warehouses, page_size=100))
    results.append(await run_step("product", import_all_goods, page_size=100))
    results.append(await run_step("sku", import_all_skus, page_size=100))
    print(json.dumps({"ok": True, "steps": len(results)}, ensure_ascii=False))


asyncio.run(main())
PY_EOF
RC=$?
set -e

if [ $RC -eq 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] master sync success rc=$RC" | tee -a "$LOG_FILE"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] master sync failed rc=$RC" | tee -a "$LOG_FILE"
  exit $RC
fi
