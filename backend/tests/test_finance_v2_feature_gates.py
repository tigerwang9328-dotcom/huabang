import pytest

from app.services.finance_v2.feature_gate_domain import FeatureGateError, GateScope, assert_command_enabled


def test_any_disabled_parent_scope_blocks_a_write_command():
    gates = [
        GateScope("global", "*", "draft_enabled", True),
        GateScope("environment", "prod", "draft_enabled", True),
        GateScope("book", "book-1", "draft_enabled", False),
        GateScope("role", "finance_manager", "draft_enabled", True),
    ]

    with pytest.raises(FeatureGateError, match="book:book-1"):
        assert_command_enabled(gates, command="draft", environment="prod", book="book-1", role="finance_manager")


def test_emergency_stop_overrides_every_enabled_scope_but_not_read_only_queries():
    gates = [
        GateScope("global", "*", "emergency_stop", True),
        GateScope("global", "*", "post_enabled", True),
    ]

    with pytest.raises(FeatureGateError, match="emergency stop"):
        assert_command_enabled(gates, command="post", environment="prod", book="book-1", role="finance_manager")
    assert_command_enabled(gates, command="read", environment="prod", book="book-1", role="finance_manager")


def test_period_close_requires_its_own_explicit_write_gate():
    gates = [GateScope("global", "*", "period_close_enabled", True)]

    assert_command_enabled(gates, command="period_close", environment="prod", book="book-1", role="finance_manager")
