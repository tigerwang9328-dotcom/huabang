from app.api.v1.product import _product_decision


def test_product_decision_returns_stable_action_enums_and_evidence():
    cases = [
        ({"sales_qty": 8, "inventory_qty": 5}, "replenish"),
        ({"sales_qty": 0, "inventory_qty": 20}, "clearance"),
        ({"sales_qty": 2, "inventory_qty": 18}, "transfer"),
        ({"sales_qty": 4, "inventory_qty": 10}, "continue_sale"),
    ]

    for row, expected in cases:
        result = _product_decision(row)
        assert result["action"] == expected
        assert result["action_label"]
        assert result["rule_code"].startswith("product_")
        assert result["evidence"] == {
            "sales_qty_7d": float(row["sales_qty"]),
            "inventory_qty": float(row["inventory_qty"]),
        }


def test_product_decision_boundary_does_not_emit_natural_language_only():
    result = _product_decision({"sales_qty": 0, "inventory_qty": 19})
    assert result["action"] == "continue_sale"
    assert set(result) >= {"action", "action_label", "rule_code", "reason", "evidence"}
