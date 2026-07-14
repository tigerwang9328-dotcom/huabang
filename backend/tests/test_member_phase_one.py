from pathlib import Path

from app.services.member_sales_service import build_vip_sales_summary


BACKEND = Path(__file__).resolve().parents[1]


def test_vip_sales_summary_uses_reliable_ticket_formulas():
    summary = build_vip_sales_summary({
        "total_sales": 1000,
        "vip_sales": 600,
        "vip_actual": 550,
        "vip_orders": 3,
        "vip_qty": 6,
        "vip_members": 2,
        "repeat_members": 1,
        "vip_standard": 800,
        "return_amount": 50,
        "return_orders": 1,
    })

    assert summary["vip_sales_amount"]["value"] == 600
    assert summary["vip_sales_ratio"]["value"] == 0.6
    assert summary["avg_order_value"]["value"] == 200
    assert summary["attachment_rate"]["value"] == 2
    assert summary["repurchase_rate"]["value"] == 0.5
    assert summary["avg_discount_rate"]["value"] == 0.75
    assert summary["return_rate"]["value"] == round(50 / 600, 4)


def test_unreliable_vip_dimensions_are_explicitly_pending():
    summary = build_vip_sales_summary({})
    assert summary["gross_profit"]["status"] == "pending_data"
    assert summary["gross_margin"]["status"] == "pending_data"
    assert summary["category_analysis"]["status"] == "pending_data"
    assert summary["style_analysis"]["status"] == "pending_data"


def test_member_api_keeps_phone_private_and_audits_explicit_access():
    source = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    assert "include_sensitive" in source
    assert "customer_phone" in source
    assert "sensitive_phone.view" in source
    assert "SysOperationLog" in source


def test_member_scope_and_balance_source_remain_fixed():
    member_service = (BACKEND / "app" / "integrations" / "baison" / "services" / "member_service.py").read_text(encoding="utf-8")
    member_api = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    assert 'raw.get("CZ_DQJE")' in member_service
    assert "ALLOWED_INVENTORY_CODES" in member_api
    assert "GREATEST(COALESCE(current_balance,0),0)" in member_api
    assert "current_balance<0" in member_api
