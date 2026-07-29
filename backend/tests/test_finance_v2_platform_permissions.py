import pytest

from app.services.finance_v2.platform_permissions import (
    FINANCE_MANAGER_ROLE,
    FINANCE_V2_READ_PERMISSION,
    FINANCE_V2_WRITE_PERMISSION,
    FinanceV2PlatformPermissionError,
    assert_finance_v2_access,
)


def test_finance_manager_with_the_required_platform_permission_is_allowed():
    assert_finance_v2_access(
        is_admin=False,
        role_codes=[FINANCE_MANAGER_ROLE],
        permission_codes=[FINANCE_V2_READ_PERMISSION],
        required_permission=FINANCE_V2_READ_PERMISSION,
    )


def test_finance_v2_rejects_a_user_without_the_finance_manager_role():
    with pytest.raises(FinanceV2PlatformPermissionError, match="requires finance_manager"):
        assert_finance_v2_access(
            is_admin=False,
            role_codes=["sales_manager"],
            permission_codes=[FINANCE_V2_READ_PERMISSION],
            required_permission=FINANCE_V2_READ_PERMISSION,
        )


def test_finance_v2_rejects_a_finance_manager_without_the_required_permission():
    with pytest.raises(FinanceV2PlatformPermissionError, match="missing platform permission: finance:center:operate"):
        assert_finance_v2_access(
            is_admin=False,
            role_codes=[FINANCE_MANAGER_ROLE],
            permission_codes=[FINANCE_V2_READ_PERMISSION],
            required_permission=FINANCE_V2_WRITE_PERMISSION,
        )


def test_finance_v2_allows_a_platform_super_administrator_without_a_role_assignment():
    assert_finance_v2_access(
        is_admin=True,
        role_codes=[],
        permission_codes=[],
        required_permission=FINANCE_V2_WRITE_PERMISSION,
    )
