from app.api.v1.member import _mask_member_key, _num


def test_mask_member_key_masks_phone_like_values():
    assert _mask_member_key("13812345678") == "138****5678"


def test_mask_member_key_keeps_short_codes_readable():
    assert _mask_member_key("VIP001") == "VIP001"


def test_num_handles_none_and_decimal_strings():
    assert _num(None) == 0.0
    assert _num("12.34") == 12.34