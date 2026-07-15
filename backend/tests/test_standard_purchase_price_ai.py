import inspect

from app.services import ai_diagnosis_service
from app.services.ai_engine import (
    SENSITIVE_FIELDS_BY_PERMISSION,
    build_template_command_conclusion,
    sanitize_command_context,
)
from app.services.rule_engine import RuleEngine


def test_ai_diagnosis_uses_only_canonical_standard_purchase_price():
    source = inspect.getsource(ai_diagnosis_service)

    assert "v_baison_sku_standard_purchase_price" in source
    assert "baison_sku.marketPrice" in source
    assert "缺标准进价" in source
    assert "coalesce(nullif(sku.cost_price" not in source
    assert "coalesce(sku.cost_price" not in source
    assert "product.cost_price" not in source
    assert "missing_standard_purchase_price_qty" in source
    assert "inventory_amount_status" in source
    assert '"estimated"' in source


def test_size_wall_and_ai_do_not_turn_missing_standard_price_into_zero():
    from app.services.size_wall_service import SizeWallService

    size_wall_source = inspect.getsource(SizeWallService.build_snapshot)
    ai_source = inspect.getsource(ai_diagnosis_service)

    assert "coalesce(sp.standard_purchase_price,0)" not in size_wall_source.lower()
    assert "coalesce(sum(qty*standard_purchase_price)" not in ai_source.lower()


def test_cost_permission_uses_standard_purchase_price_name():
    assert "standard_purchase_price" in SENSITIVE_FIELDS_BY_PERMISSION["cost"]
    assert "cost_price" not in SENSITIVE_FIELDS_BY_PERMISSION["cost"]


def test_incomplete_finance_removes_operating_profit_from_ai_context():
    safe = sanitize_command_context({
        "finance_complete": False,
        "metrics": {
            "operating_profit": {
                "value": -200,
                "status": "estimated",
                "source": "finance",
                "reason": "费用缺失：租金、工资",
            },
        },
    })
    conclusion = build_template_command_conclusion(safe)

    assert "operating_profit" not in safe["metrics"]
    assert not conclusion["facts"]
    assert any("不能判断最终盈亏" in item for item in conclusion["limitations"])


def test_profit_rules_keep_ready_finance_gate_and_standard_price_evidence():
    source = inspect.getsource(RuleEngine)

    assert "operating_profit_status='ready'" in source
    assert "finance_approved=true" in source
    assert "baison_sku.marketPrice" in source
