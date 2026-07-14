from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from scripts.generate_boss_command_center import (
    MEMBER_BALANCE_CHECK_SQL,
    member_balance_check_params,
)


def test_member_balance_check_uses_confirmed_ten_code_scope():
    assert member_balance_check_params() == {"codes": sorted(ALLOWED_INVENTORY_CODES)}
    assert "UPPER(register_store)=ANY(:codes)" in MEMBER_BALANCE_CHECK_SQL
    assert "COALESCE(status,'active')='active'" in MEMBER_BALANCE_CHECK_SQL
