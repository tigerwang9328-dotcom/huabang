import asyncio
from datetime import date

from app.services.ai_diagnosis_service import AIDiagnosisService


class ProductDiagnosisService(AIDiagnosisService):
    def __init__(self):
        super().__init__(None)
        self.sql = ""
        self.summary_sql = ""

    async def _latest_date(self):
        return date(2026, 7, 12)

    async def _rows(self, sql, params=None):
        self.sql = sql
        return [{
            "product_code": "STYLE001",
            "product_name": "测试商品",
            "qty7": 0,
            "qty30": 0,
            "inventory_qty": 30,
            "inventory_amount": 3000,
            "age_days": 193,
            "zero_sku": 0,
            "gm": 0.5,
            "first_inbound_date": date(2026, 1, 1),
            "last_inbound_date": date(2026, 7, 5),
            "total_inbound_quantity": 100,
            "inbound_quantity_30d": 12,
            "last_purchase_price": 80,
            "receipt_count": 5,
        }]

    async def _one(self, sql, params=None):
        self.summary_sql = sql
        return {
            "net_sales": 13722,
            "order_count": 31,
            "gross_margin": 0.7477,
            "product_count": 760,
            "active_product_count": 65,
            "sales_qty_7d": 262,
            "sales_qty_30d": 847,
            "inbound_qty_30d": 472,
            "inbound_product_count": 120,
            "aged_inventory_product_count": 18,
            "stockout_product_count": 7,
            "hot_low_stock_count": 4,
            "slow_product_count": 3,
            "health_score": 82,
        }


def test_product_diagnosis_exposes_baison_inbound_lifecycle_metrics():
    service = ProductDiagnosisService()

    result = asyncio.run(service.products())

    summary = result["summary"]
    assert "dws_product_inbound_summary" in service.sql
    assert "dwd.dwd_inventory_balance" in service.sql
    assert "greatest" in service.sql.lower()
    assert summary["net_sales"] == 13722
    assert summary["order_count"] == 31
    assert summary["gross_margin"] == 0.7477
    assert summary["product_count"] == 760
    assert summary["health_score"] == 82
    assert summary["inbound_qty_30d"] == 472
    assert summary["inbound_product_count"] == 120
    assert summary["aged_inventory_product_count"] == 18
    diagnosis = result["diagnoses"][0]
    assert "首次入库" in diagnosis["evidence"][0]
    assert "最近采购价" in diagnosis["evidence"][-1]
    assert "dws_product_inbound_summary" in diagnosis["data_source"]
    assert "dwd_inventory_balance" in diagnosis["data_source"]
