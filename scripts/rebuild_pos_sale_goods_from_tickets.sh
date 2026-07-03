#!/bin/bash
# Rebuild product-level POS sale goods from verified ticket details.
# Default window: last 7 Beijing-calendar days, including today.
set -euo pipefail

BACKEND_DIR="/srv/huabang-ai-center/backend"
LOG_DIR="/srv/huabang-ai-center/logs"
LOG_FILE="$LOG_DIR/rebuild_pos_sale_goods_daily.log"

mkdir -p "$LOG_DIR"
cd "$BACKEND_DIR"

START_DATE="${1:-$(TZ='Asia/Shanghai' date -d '6 days ago' '+%Y-%m-%d')}"
END_DATE="${2:-$(TZ='Asia/Shanghai' date '+%Y-%m-%d')}"

DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2-)
DB_PASS=$(grep '^DB_PASSWORD=' .env | cut -d= -f2-)

echo "==========================================" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] rebuild dwd_pos_sale_goods/dws_product_daily ${START_DATE} ~ ${END_DATE}" | tee -a "$LOG_FILE"

PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d huabang_ai -v start_date="$START_DATE" -v end_date="$END_DATE" -P pager=off <<'SQL' >> "$LOG_FILE" 2>&1
\set ON_ERROR_STOP on

BEGIN;

DELETE FROM dws.dws_product_daily
WHERE stat_date >= :'start_date'::date
  AND stat_date <= :'end_date'::date;

DELETE FROM dwd.dwd_pos_sale_goods
WHERE biz_date >= :'start_date'::date
  AND biz_date <= :'end_date'::date;

INSERT INTO dwd.dwd_pos_sale_goods
(source_system, biz_date, store_code, product_code, sku_code, product_name, goods_id,
 category_code, category_name, brand_code, brand_name, outer_product_code,
 sales_qty, sales_amount, standard_amount, discount_rate, tag_price,
 stock_qty_snapshot, batch_no, raw_ref_id, synced_at, created_at, updated_at)
WITH whitelist(code) AS (
  VALUES ('134681'),('285204'),('285702'),('185805'),('185808'),('285101'),('285102'),('GZ001'),('GZ002'),('GYNG')
), detail AS (
  SELECT
    t.id AS ticket_id,
    t.biz_date,
    t.store_code,
    d.value AS item
  FROM dwd.dwd_pos_ticket t
  JOIN whitelist w ON w.code = t.store_code
  CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.raw_data->'orderDetailGets', '[]'::jsonb)) d(value)
  WHERE t.biz_date >= :'start_date'::date
    AND t.biz_date <= :'end_date'::date
    AND COALESCE(t.is_void, false) = false
    AND COALESCE(t.is_pending, false) = false
), normalized AS (
  SELECT
    biz_date,
    store_code,
    NULLIF(item->>'spdm','') AS product_code,
    concat_ws('|', NULLIF(item->>'spdm',''), NULLIF(item->>'gg1dm',''), NULLIF(item->>'gg2dm','')) AS sku_code,
    max(NULLIF(item->>'spmc','')) AS product_name,
    sum(COALESCE(NULLIF(item->>'sl','')::numeric, 0)) AS sales_qty,
    sum(COALESCE(NULLIF(item->>'je','')::numeric, 0)) AS sales_amount,
    sum(COALESCE(NULLIF(item->>'bzje','')::numeric, 0)) AS standard_amount,
    max(NULLIF(item->>'ckj','')::numeric) AS tag_price,
    min(ticket_id) AS raw_ref_id
  FROM detail
  WHERE NULLIF(item->>'spdm','') IS NOT NULL
  GROUP BY biz_date, store_code, NULLIF(item->>'spdm',''), concat_ws('|', NULLIF(item->>'spdm',''), NULLIF(item->>'gg1dm',''), NULLIF(item->>'gg2dm',''))
)
SELECT
  'baison_ticket_detail', biz_date, store_code, product_code, sku_code, product_name, NULL,
  NULL, NULL, NULL, NULL, NULL,
  sales_qty, sales_amount, standard_amount,
  CASE WHEN standard_amount > 0 THEN ROUND(sales_amount / standard_amount, 4) ELSE NULL END,
  tag_price, NULL, 'REBUILD_TICKET_DAILY', raw_ref_id, now(), now(), now()
FROM normalized;

INSERT INTO dws.dws_product_daily
(stat_date, product_code, store_code, sales_quantity, return_quantity, net_quantity,
 sales_amount, return_amount, net_sales_amount, cost_amount, gross_profit, gross_margin,
 avg_discount_rate, is_cost_complete, etl_at, created_at)
SELECT
  biz_date,
  product_code,
  store_code,
  COALESCE(SUM(sales_qty),0)::integer,
  0,
  COALESCE(SUM(sales_qty),0)::integer,
  COALESCE(SUM(sales_amount),0),
  0,
  COALESCE(SUM(sales_amount),0),
  0,
  0,
  NULL,
  CASE WHEN SUM(standard_amount) > 0 THEN ROUND(SUM(sales_amount) / SUM(standard_amount), 4) ELSE NULL END,
  false,
  now(), now()
FROM dwd.dwd_pos_sale_goods
WHERE biz_date >= :'start_date'::date
  AND biz_date <= :'end_date'::date
GROUP BY biz_date, product_code, store_code
ON CONFLICT (stat_date, product_code, store_code)
DO UPDATE SET sales_quantity = EXCLUDED.sales_quantity,
              return_quantity = EXCLUDED.return_quantity,
              net_quantity = EXCLUDED.net_quantity,
              sales_amount = EXCLUDED.sales_amount,
              return_amount = EXCLUDED.return_amount,
              net_sales_amount = EXCLUDED.net_sales_amount,
              cost_amount = EXCLUDED.cost_amount,
              gross_profit = EXCLUDED.gross_profit,
              gross_margin = EXCLUDED.gross_margin,
              avg_discount_rate = EXCLUDED.avg_discount_rate,
              is_cost_complete = EXCLUDED.is_cost_complete,
              etl_at = now();

COMMIT;

WITH whitelist(code) AS (
  VALUES ('134681'),('285204'),('285702'),('185805'),('185808'),('285101'),('285102'),('GZ001'),('GZ002'),('GYNG')
)
SELECT 'dwd_non_whitelist' AS check_name, count(*) AS cnt
FROM dwd.dwd_pos_sale_goods t
WHERE t.biz_date >= :'start_date'::date
  AND t.biz_date <= :'end_date'::date
  AND NOT EXISTS (SELECT 1 FROM whitelist w WHERE w.code=t.store_code)
UNION ALL
SELECT 'dws_product_non_whitelist', count(*)
FROM dws.dws_product_daily t
WHERE t.stat_date >= :'start_date'::date
  AND t.stat_date <= :'end_date'::date
  AND NOT EXISTS (SELECT 1 FROM whitelist w WHERE w.code=t.store_code);

SELECT biz_date, sum(sales_amount) AS amount, sum(sales_qty) AS qty, count(*) AS rows
FROM dwd.dwd_pos_sale_goods
WHERE biz_date >= :'start_date'::date
  AND biz_date <= :'end_date'::date
GROUP BY biz_date
ORDER BY biz_date DESC;
SQL

echo "[$(date '+%Y-%m-%d %H:%M:%S')] rebuild success" | tee -a "$LOG_FILE"
