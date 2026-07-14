import inspect

from app.services import business_overview_service
from app.services.business_overview_service import _build_platform_sales, _build_refund_metrics


def test_build_platform_sales_keeps_zero_online_channel():
    channels = _build_platform_sales(13722, 0)

    assert channels == [
        {"name": "线下门店", "amount": 13722.0, "pct": 100.0},
        {"name": "线上渠道", "amount": 0.0, "pct": 0.0},
    ]


def test_build_platform_sales_returns_empty_without_sales():
    assert _build_platform_sales(0, 0) == []


def test_build_refund_metrics_marks_zero_ready_after_complete_ticket_sync():
    metrics = _build_refund_metrics(total_sales=13519, refund_amount=0, sync_complete=True)

    assert metrics["yesterday_refund_amount"]["value"] == 0.0
    assert metrics["yesterday_refund_amount"]["status"] == "ready"
    assert metrics["yesterday_refund_rate"]["value"] == 0.0
    assert metrics["yesterday_refund_rate"]["status"] == "ready"


def test_build_refund_metrics_keeps_unknown_refunds_pending_without_complete_sync():
    metrics = _build_refund_metrics(total_sales=13519, refund_amount=0, sync_complete=False)

    assert metrics["yesterday_refund_amount"]["value"] is None
    assert metrics["yesterday_refund_amount"]["status"] in {"pending_data", "stale"}
    assert metrics["yesterday_refund_rate"]["value"] is None
    assert metrics["yesterday_refund_rate"]["status"] in {"pending_data", "stale"}


def test_build_refund_metrics_keeps_return_only_rate_undefined():
    metrics = _build_refund_metrics(total_sales=0, refund_amount=54, sync_complete=True)

    assert metrics["yesterday_refund_amount"]["value"] == 54.0
    assert metrics["yesterday_refund_amount"]["status"] == "ready"
    assert metrics["yesterday_refund_rate"]["value"] is None
    assert metrics["yesterday_refund_rate"]["status"] == "pending_data"


def test_overview_payment_query_projects_refund_amount_from_ticket_cte():
    source = inspect.getsource(business_overview_service.get_overview)

    assert "ticket.refund_amount" in source
