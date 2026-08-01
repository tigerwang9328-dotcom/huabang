from app.services.finance_v2.finance_observability import FINANCE_METRIC_CATALOG


def test_finance_metric_catalog_covers_every_v2_operational_gate_with_safe_alert_metadata():
    expected_metric_keys = {
        "posting_attempt_failed",
        "voucher_unbalanced_blocked",
        "history_import_conflicted",
        "source_inbox_backlog",
        "exception_queue_backlog",
        "lock_wait",
        "deadlock",
        "period_close_failed",
        "export_failure",
        "api_5xx_rate",
        "balance_difference_alert",
    }

    assert set(FINANCE_METRIC_CATALOG) == expected_metric_keys
    for metric_key, policy in FINANCE_METRIC_CATALOG.items():
        assert policy.metric_key == metric_key
        assert policy.threshold is not None
        assert policy.owner == "finance_operations"
        assert policy.notification_route == "finance-v2-oncall"
        assert policy.notification_configured is False
        assert policy.close_condition
        assert policy.labels == ()


def test_unimplemented_metric_policies_are_explicitly_unavailable_instead_of_reporting_zero():
    for metric_key in (
        "source_inbox_backlog",
        "exception_queue_backlog",
        "lock_wait",
        "deadlock",
        "export_failure",
        "api_5xx_rate",
        "balance_difference_alert",
    ):
        assert FINANCE_METRIC_CATALOG[metric_key].availability == "unavailable"
        assert FINANCE_METRIC_CATALOG[metric_key].unavailable_reason
