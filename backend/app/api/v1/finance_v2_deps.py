"""Finance V2-specific adapters for Huabang platform authorization."""

from fastapi import Depends

from app.api.v1.deps import (
    get_current_user,
    get_current_user_permissions,
    get_current_user_roles,
)
from app.core.exceptions import PermissionDeniedException
from app.models.sys import SysUser
from app.services.finance_v2.platform_permissions import (
    FinanceV2PlatformPermissionError,
    assert_finance_v2_access,
)


def require_finance_v2_permission(permission_code: str):
    """Require the central finance role and one Finance V2 platform permission."""
    async def check_finance_v2_permission(
        current_user: SysUser = Depends(get_current_user),
        roles: list[str] = Depends(get_current_user_roles),
        permissions: list[str] = Depends(get_current_user_permissions),
    ) -> SysUser:
        try:
            assert_finance_v2_access(
                is_admin=bool(current_user.is_admin),
                role_codes=roles,
                permission_codes=permissions,
                required_permission=permission_code,
            )
        except FinanceV2PlatformPermissionError as error:
            raise PermissionDeniedException(str(error)) from error
        return current_user

    check_finance_v2_permission.finance_v2_permission = permission_code
    return check_finance_v2_permission
