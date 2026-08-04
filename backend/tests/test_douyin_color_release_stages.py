"""TDD tests for the A/B/C/D release stage switch (Task 14).

These tests pin the pure-function contract of the release-stage service before
any database wiring exists. They must run without a database connection.
"""

import pytest


def test_stage_order_exposes_canonical_forward_ordering():
    from app.services.douyin_color_release_service import STAGE_ORDER

    assert STAGE_ORDER == {"A": 0, "B": 1, "C": 2, "D": 3}


def test_can_advance_stage_allows_forward_progress():
    from app.services.douyin_color_release_service import can_advance_stage

    assert can_advance_stage(current_stage="A", target_stage="B") is True
    assert can_advance_stage(current_stage="B", target_stage="C") is True
    assert can_advance_stage(current_stage="C", target_stage="D") is True
    # multi-step forward is NOT allowed; only adjacent stages are valid
    assert can_advance_stage(current_stage="A", target_stage="D") is False
    assert can_advance_stage(current_stage="A", target_stage="C") is False


def test_can_advance_stage_rejects_backward_or_same_stage():
    from app.services.douyin_color_release_service import can_advance_stage

    assert can_advance_stage(current_stage="B", target_stage="A") is False
    assert can_advance_stage(current_stage="C", target_stage="B") is False
    assert can_advance_stage(current_stage="D", target_stage="A") is False
    assert can_advance_stage(current_stage="D", target_stage="C") is False
    # same stage is not an advance
    assert can_advance_stage(current_stage="B", target_stage="B") is False


def test_can_advance_stage_rejects_unknown_stage_values():
    from app.services.douyin_color_release_service import can_advance_stage

    for bad in ("", "a", "E", "AB", None, "1", 0):
        assert can_advance_stage(current_stage="A", target_stage=bad) is False
        assert can_advance_stage(current_stage=bad, target_stage="B") is False


def test_advance_stage_returns_updated_config_with_target_stage():
    from app.services.douyin_color_release_service import advance_stage

    config = {
        "account_id": 7,
        "current_stage": "A",
        "bounce_report_enabled": False,
        "bounce_semantics_status": "pending",
    }
    updated = advance_stage(config=config, target_stage="B")

    assert updated["current_stage"] == "B"
    # other fields preserved
    assert updated["account_id"] == 7
    assert updated["bounce_report_enabled"] is False
    assert updated["bounce_semantics_status"] == "pending"
    # input is not mutated
    assert config["current_stage"] == "A"


def test_advance_stage_rejects_invalid_transition():
    from app.services.douyin_color_release_service import advance_stage

    config = {
        "current_stage": "C",
        "bounce_report_enabled": False,
        "bounce_semantics_status": "pending",
    }
    with pytest.raises(ValueError, match="invalid_stage_transition"):
        advance_stage(config=config, target_stage="A")
    with pytest.raises(ValueError, match="invalid_stage_transition"):
        advance_stage(config=config, target_stage="C")


def test_can_enable_bounce_report_gates_on_verified_semantics_status():
    from app.services.douyin_color_release_service import can_enable_bounce_report

    assert can_enable_bounce_report(bounce_semantics_status="verified_lower_is_better") is True
    assert can_enable_bounce_report(bounce_semantics_status="verified_higher_is_better") is True
    assert can_enable_bounce_report(bounce_semantics_status="pending") is False
    assert can_enable_bounce_report(bounce_semantics_status="rejected") is False
    assert can_enable_bounce_report(bounce_semantics_status="unverified") is False
    assert can_enable_bounce_report(bounce_semantics_status=None) is False


def test_enable_bounce_report_sets_flag_true_and_records_status():
    from app.services.douyin_color_release_service import enable_bounce_report

    config = {
        "current_stage": "D",
        "bounce_report_enabled": False,
        "bounce_semantics_status": "pending",
    }
    updated = enable_bounce_report(
        config=config, bounce_semantics_status="verified_lower_is_better"
    )

    assert updated["bounce_report_enabled"] is True
    # the validated semantics status is reflected on the returned config
    assert updated["bounce_semantics_status"] == "verified_lower_is_better"
    # input is not mutated
    assert config["bounce_report_enabled"] is False
    assert config["bounce_semantics_status"] == "pending"


def test_enable_bounce_report_rejects_unverified_status():
    from app.services.douyin_color_release_service import enable_bounce_report

    config = {"bounce_report_enabled": False, "bounce_semantics_status": "pending"}
    for bad_status in ("pending", "rejected", "unverified", "needs_review"):
        with pytest.raises(ValueError, match="bounce_semantics_not_verified"):
            enable_bounce_report(config=dict(config), bounce_semantics_status=bad_status)


def test_disable_bounce_report_sets_flag_false_and_preserves_semantics():
    from app.services.douyin_color_release_service import disable_bounce_report

    config = {
        "current_stage": "D",
        "bounce_report_enabled": True,
        "bounce_semantics_status": "verified_lower_is_better",
    }
    updated = disable_bounce_report(config=config)

    assert updated["bounce_report_enabled"] is False
    # disabling only flips the flag; semantics status is preserved
    assert updated["bounce_semantics_status"] == "verified_lower_is_better"
    # input is not mutated
    assert config["bounce_report_enabled"] is True


def test_check_constraint_mirror_blocks_enabled_with_pending_semantics():
    """Mirror of the DB CHECK constraint ``ck_release_stage_bounce_gating`` at
    the pure-function layer: a config where ``bounce_report_enabled=True`` while
    ``bounce_semantics_status`` is not verified can never be produced through
    the service.
    """
    from app.services.douyin_color_release_service import enable_bounce_report

    base = {"bounce_report_enabled": False, "bounce_semantics_status": "pending"}
    for bad_status in ("pending", "rejected", "unverified", "needs_review"):
        with pytest.raises(ValueError, match="bounce_semantics_not_verified"):
            result = enable_bounce_report(config=dict(base), bounce_semantics_status=bad_status)
            # defensive: should never reach here
            assert not (result["bounce_report_enabled"] is True and
                        result["bounce_semantics_status"] not in
                        ("verified_lower_is_better", "verified_higher_is_better"))
