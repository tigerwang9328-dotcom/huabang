from pathlib import Path

from app.services.sales_metric_service import summarize_payment_rows


REPO = Path(__file__).resolve().parents[2]


def test_fixed_payment_samples_cover_online_recharge_and_refund():
    july_12 = summarize_payment_rows(
        [("000", 1553), ("001", 160), ("004", 7290), ("005", 334), ("011", 9), ("666", 8460), ("971", 754)],
        recharge_amount=8500,
    )
    july_6 = summarize_payment_rows(
        [("000", 3715), ("003", 240), ("004", 2159), ("666", 7116), ("666", -54), ("971", 199)],
        recharge_amount=2000,
    )

    assert july_12["sales_amount"] == 18066
    assert july_12["online_sales_amount"] == 9
    assert july_12["actual_pay_amount"] == 19276
    assert july_6["sales_amount"] == 13429
    assert july_6["refund_amount"] == 54
    assert july_6["actual_pay_amount"] == 12976


def test_phase_one_acceptance_record_covers_every_release_gate():
    acceptance = REPO / "docs" / "acceptance" / "boss-command-center-phase1.md"
    content = acceptance.read_text(encoding="utf-8")

    for business_date in ("2026-07-11", "2026-07-12", "2026-07-13"):
        assert business_date in content
    for gate in (
        "销售/实收固定样本一致",
        "库存合计一致",
        "VIP明细等于总额",
        "日报幂等",
        "来源时间可见",
        "待接入不冒充零值",
    ):
        assert gate in content


def test_phase_one_routes_remain_available():
    router = (REPO / "frontend" / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    for route in (
        "/app/dashboard",
        "/app/report",
        "/app/store",
        "/app/product",
        "/app/product/size-wall",
        "/app/inventory",
        "/app/member",
    ):
        assert route in router
