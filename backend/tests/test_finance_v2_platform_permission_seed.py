import pytest

from app.services.finance_v2.platform_permission_seed import (
    FINANCE_V2_PLATFORM_PERMISSION_ROWS,
    FINANCE_V2_PLATFORM_ROLE,
    seed_finance_v2_platform_permissions,
)


@pytest.mark.asyncio
async def test_finance_v2_platform_permission_seed_only_adds_the_finance_manager_access_rules():
    calls = []

    class RecordingDb:
        async def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    result = await seed_finance_v2_platform_permissions(RecordingDb())

    assert result.role_code == "finance_manager"
    assert result.permission_codes == ("finance:center:view", "finance:center:operate")
    assert FINANCE_V2_PLATFORM_ROLE["code"] == "finance_manager"
    assert tuple(row["code"] for row in FINANCE_V2_PLATFORM_PERMISSION_ROWS) == result.permission_codes
    assert len(calls) == 4
    assert all("ON CONFLICT" in statement for statement, _ in calls)
    assert all("UPDATE sys.sys_role" not in statement for statement, _ in calls)
    assert calls[-1][1]["role_code"] == "finance_manager"
    assert calls[-1][1]["permission_codes"] == ["finance:center:view", "finance:center:operate"]
