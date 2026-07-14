from app.api.v1.member import (
    _mask_member_key,
    _num,
    _redact_member_fields,
    _redact_segment_item,
    _safe_csv_cell,
)


def test_mask_member_key_masks_phone_like_values():
    assert _mask_member_key("13812345678") == "138****5678"


def test_mask_member_key_keeps_short_codes_readable():
    assert _mask_member_key("VIP001") == "VIP001"


def test_num_handles_none_and_decimal_strings():
    assert _num(None) == 0.0
    assert _num("12.34") == 12.34


def test_csv_cells_neutralize_spreadsheet_formulas():
    assert _safe_csv_cell("=HYPERLINK(\"https://bad.example\")") == "'=HYPERLINK(\"https://bad.example\")"
    assert _safe_csv_cell("+SUM(1,2)") == "'+SUM(1,2)"
    assert _safe_csv_cell("正常会员") == "正常会员"


def test_segment_redaction_removes_sensitive_values_and_evidence():
    item = {
        "phone": "13812345678",
        "current_balance": 5000,
        "total_amount": 12000,
        "total_count": 8,
        "last_consume_date": "2026-07-01",
        "labels": [{"code": "HIGH_BALANCE", "name": "高余额", "evidence": {"current_balance": 5000}}],
        "risks": [{"code": "HIGH_BALANCE_DORMANT", "name": "大额余额长期未消费", "evidence": {"current_balance": 5000}}],
        "metrics": {"current_balance": 5000},
        "preferences": [{"product_code": "A001"}],
        "suggested_products": [{"product_code": "A001"}],
    }
    redacted = _redact_segment_item(item)
    assert redacted["phone"] == "138****5678"
    assert redacted["current_balance"] is None
    assert redacted["total_amount"] is None
    assert redacted["last_consume_date"] is None
    assert redacted["metrics"] == {}
    assert redacted["preferences"] == []
    assert redacted["labels"][0].get("evidence") is None
    assert redacted["risks"][0].get("evidence") is None
    assert redacted["sensitive_redacted"] is True


def test_member_field_redaction_never_turns_hidden_money_into_zero():
    redacted = _redact_member_fields(
        {"member_no": "VIP001", "current_balance": 5000, "total_amount": 12000},
        ("current_balance", "total_amount"),
    )
    assert redacted == {
        "member_no": "VIP001",
        "current_balance": None,
        "total_amount": None,
        "sensitive_redacted": True,
    }
