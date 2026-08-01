from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_exposes_five_historical_finance_views():
    router = (ROOT / "frontend/src/router/index.ts").read_text(encoding="utf-8")
    for route in (
        "fin/history/account-sets",
        "fin/history/statements",
        "fin/history/account-balances",
        "fin/history/vouchers",
        "fin/history/data-quality",
    ):
        assert route in router


def test_historical_finance_client_is_read_only():
    client = (ROOT / "frontend/src/api/kingdeeFinance.ts").read_text(encoding="utf-8")
    assert "request.get" in client
    assert "request.post" not in client
    assert "request.put" not in client
    assert "request.delete" not in client


def test_history_page_explains_non_ready_status_without_zero_fallback():
    page = (ROOT / "frontend/src/views/finance/HistoricalFinance.vue").read_text(encoding="utf-8")
    assert "pending_mapping" in page
    assert "pending_data" in page
    assert "read_only" in page
