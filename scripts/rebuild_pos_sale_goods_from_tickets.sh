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

DB_HOST=$(grep '^DB_HOST=' .env | cut -d= -f2-)
DB_PORT=$(grep '^DB_PORT=' .env | cut -d= -f2-)
DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2-)
DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2-)
DB_PASS=$(grep '^DB_PASSWORD=' .env | cut -d= -f2-)
DB_HOST=${DB_HOST:-localhost}; DB_PORT=${DB_PORT:-5432}; DB_NAME=${DB_NAME:-huabang_ai}
PGPASSFILE=$(mktemp)
trap 'rm -f "$PGPASSFILE"' EXIT
chmod 600 "$PGPASSFILE"
printf '%s:%s:%s:%s:%s\n' "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASS" > "$PGPASSFILE"
export PGPASSFILE
unset DB_PASS

echo "==========================================" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] rebuild dwd_pos_sale_goods/dws_product_daily ${START_DATE} ~ ${END_DATE}" | tee -a "$LOG_FILE"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v start_date="$START_DATE" -v end_date="$END_DATE" -P pager=off <<'SQL' >> "$LOG_FILE" 2>&1
\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE dwd.dwd_pos_sale_goods
  ADD COLUMN IF NOT EXISTS cost_price numeric(18,4),
  ADD COLUMN IF NOT EXISTS cost_amount numeric(18,2),
  ADD COLUMN IF NOT EXISTS gross_profit numeric(18,2),
  ADD COLUMN IF NOT EXISTS gross_margin numeric(12,6),
  ADD COLUMN IF NOT EXISTS cost_source varchar(32),
  ADD COLUMN IF NOT EXISTS is_cost_missing boolean NOT NULL DEFAULT true;

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
 cost_price, cost_amount, gross_profit, gross_margin, cost_source, is_cost_missing,
 stock_qty_snapshot, batch_no, raw_ref_id, synced_at, created_at, updated_at)
WITH whitelist(code) AS (
  VALUES ('134681'),('285204'),('285702'),('185805'),('185808'),('285101'),('285102')
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
), costed AS (
  SELECT
    n.*,
    CASE
      WHEN product.supplier_code = 'GY1229'
       AND price.standard_purchase_price = 1
       AND n.sales_qty <> 0
        THEN n.sales_amount * 0.60 / n.sales_qty
      ELSE price.standard_purchase_price
    END AS unit_cost,
    CASE
      WHEN product.supplier_code = 'GY1229'
       AND price.standard_purchase_price = 1
        THEN 'supplier_ratio_60pct'
      WHEN price.standard_purchase_price IS NOT NULL
        THEN 'baison_standard_purchase_price'
      ELSE 'missing'
    END AS cost_source,
    price.standard_purchase_price IS NULL AS is_cost_missing
  FROM normalized n
  LEFT JOIN LATERAL (
    SELECT p.supplier_code
    FROM dim.dim_product p
    WHERE p.product_code = n.product_code
      AND p.source_system = 'baison'
    ORDER BY p.synced_at DESC NULLS LAST, p.id DESC
    LIMIT 1
  ) product ON true
  LEFT JOIN LATERAL (
    SELECT sp.standard_purchase_price
    FROM dim.v_baison_sku_standard_purchase_price sp
    WHERE sp.product_code = n.product_code
      AND sp.color_code = COALESCE(BTRIM(split_part(n.sku_code, '|', 2)), '')
      AND sp.size_code = COALESCE(BTRIM(split_part(n.sku_code, '|', 3)), '')
    ORDER BY sp.synced_at DESC NULLS LAST
    LIMIT 1
  ) price ON true
)
SELECT
  'baison_ticket_detail', biz_date, store_code, product_code, sku_code, product_name, NULL,
  NULL, NULL, NULL, NULL, NULL,
  sales_qty, sales_amount, standard_amount,
  CASE WHEN standard_amount > 0 THEN ROUND(sales_amount / standard_amount, 4) ELSE NULL END,
  tag_price,
  unit_cost,
  CASE WHEN unit_cost IS NOT NULL THEN ROUND(sales_qty * unit_cost, 2) END,
  CASE WHEN unit_cost IS NOT NULL THEN ROUND(sales_amount - sales_qty * unit_cost, 2) END,
  CASE WHEN unit_cost IS NOT NULL AND sales_amount <> 0
       THEN ROUND((sales_amount - sales_qty * unit_cost) / sales_amount, 6) END,
  cost_source,
  is_cost_missing,
  NULL, 'REBUILD_TICKET_DAILY', raw_ref_id, now(), now(), now()
FROM costed;

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
  COALESCE(SUM(cost_amount),0),
  COALESCE(SUM(gross_profit),0),
  CASE WHEN SUM(sales_amount) <> 0
       THEN ROUND(SUM(gross_profit) / SUM(sales_amount), 6) END,
  CASE WHEN SUM(standard_amount) > 0 THEN ROUND(SUM(sales_amount) / SUM(standard_amount), 4) ELSE NULL END,
  BOOL_AND(NOT is_cost_missing),
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

WITH store_cost AS (
  SELECT stat_date, store_code,
         SUM(cost_amount) AS cost_amount,
         SUM(gross_profit) AS gross_profit,
         CASE WHEN SUM(sales_amount) <> 0
              THEN SUM(gross_profit) / SUM(sales_amount) END AS gross_margin,
         BOOL_AND(is_cost_complete) AS is_cost_complete
  FROM dws.dws_product_daily
  WHERE stat_date >= :'start_date'::date
    AND stat_date <= :'end_date'::date
  GROUP BY stat_date, store_code
)
UPDATE dws.dws_store_daily d
SET cost_amount = c.cost_amount,
    gross_profit = c.gross_profit,
    gross_margin = c.gross_margin,
    is_cost_complete = c.is_cost_complete,
    etl_at = now()
FROM store_cost c
WHERE d.stat_date = c.stat_date
  AND d.store_code = c.store_code
  AND d.channel = 'offline';

WITH company_cost AS (
  SELECT stat_date,
         SUM(cost_amount) AS cost_amount,
         SUM(gross_profit) AS gross_profit,
         CASE WHEN SUM(sales_amount) <> 0
              THEN SUM(gross_profit) / SUM(sales_amount) END AS gross_margin,
         BOOL_AND(is_cost_complete) AS is_cost_complete
  FROM dws.dws_product_daily
  WHERE stat_date >= :'start_date'::date
    AND stat_date <= :'end_date'::date
  GROUP BY stat_date
)
UPDATE dws.dws_company_daily d
SET total_cost_amount = c.cost_amount,
    gross_profit = c.gross_profit,
    gross_margin = c.gross_margin,
    is_cost_complete = c.is_cost_complete,
    etl_at = now()
FROM company_cost c
WHERE d.stat_date = c.stat_date;

COMMIT;

WITH whitelist(code) AS (
  VALUES ('134681'),('285204'),('285702'),('185805'),('185808'),('285101'),('285102')
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

SELECT biz_date, sum(sales_amount) AS amount, sum(sales_qty) AS qty,
       sum(cost_amount) AS cost_amount, sum(gross_profit) AS gross_profit,
       count(*) FILTER (WHERE is_cost_missing) AS estimated_or_missing_rows,
       count(*) AS rows
FROM dwd.dwd_pos_sale_goods
WHERE biz_date >= :'start_date'::date
  AND biz_date <= :'end_date'::date
GROUP BY biz_date
ORDER BY biz_date DESC;
SQL

echo "[$(date '+%Y-%m-%d %H:%M:%S')] rebuild success" | tee -a "$LOG_FILE"
