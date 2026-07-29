"""Finance V2 authorization rules backed by the Huabang platform identity."""

FINANCE_MANAGER_ROLE = "finance_manager"
FINANCE_V2_READ_PERMISSION = "finance:center:view"
FINANCE_V2_WRITE_PERMISSION = "finance:center:operate"


class FinanceV2PlatformPermissionError(PermissionError):
    """Raised when a platform principal is not eligible for Finance V2."""


def assert_finance_v2_access(
    *,
    is_admin: bool,
    role_codes: list[str],
    permission_codes: list[str],
    required_permission: str,
) -> None:
    """Allow only a platform administrator or an authorized finance manager."""
    if is_admin:
        return
    if FINANCE_MANAGER_ROLE not in role_codes:
        raise FinanceV2PlatformPermissionError("Finance V2 requires finance_manager role")
    if required_permission not in permission_codes:
        raise FinanceV2PlatformPermissionError(
            f"Finance V2 missing platform permission: {required_permission}"
        )
