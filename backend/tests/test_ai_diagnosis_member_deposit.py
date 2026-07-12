import asyncio
from datetime import date

from app.services.ai_diagnosis_service import AIDiagnosisService


class MemberDepositDiagnosisService(AIDiagnosisService):
    def __init__(self):
        super().__init__(None)

    async def _latest_date(self):
        return date(2026, 7, 11)

    async def _one(self, sql, params=None):
        if "dm_member_visit_list" in sql:
            return {"visit_stat_date": date(2026, 7, 11), "visit_count": 10, "pending_count": 8, "converted_count": 2, "conversion_amount": 500}
        if "dwd.dwd_pos_ticket" in sql:
            return {"total_orders": 20, "member_orders": 12, "active_members": 10, "total_sales": 10000, "member_sales": 7000}
        if "dim.dim_member" in sql:
            return {"total_members": 1000, "active_30d": 200, "sleep_90d": 300}
        if "dws.dws_member_deposit_daily" in sql:
            return {
                "deposit_stat_date": date(2026, 7, 11), "recharge_count": 4,
                "recharge_member_count": 3, "recharge_amount": 6000,
                "avg_recharge_amount": 1500, "consume_amount": 2200,
                "repeat_recharge_member_count": 2, "recharge_member_count_30d": 5,
                "large_recharge_count": 1,
            }
        return {}


def test_member_diagnosis_exposes_stored_value_metrics():
    result = asyncio.run(MemberDepositDiagnosisService().members())

    summary = result["summary"]
    assert summary["total_member_count"] == 1000
    assert summary["active_member_count_30d"] == 200
    assert summary["sleeping_member_count_90d"] == 300
    assert summary["deposit_stat_date"] == "2026-07-11"
    assert summary["recharge_amount"] == 6000
    assert summary["recharge_member_count"] == 3
    assert summary["avg_recharge_amount"] == 1500
    assert summary["stored_value_consume_amount"] == 2200
    assert summary["repeat_recharge_member_count"] == 2
    assert summary["repeat_recharge_rate"] == 0.4
    assert "dwd_baison_member_deposit_log" in result["data_quality"]["source_tables"]
