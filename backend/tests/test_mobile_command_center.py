from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import mobile


@pytest.mark.asyncio
async def test_mobile_command_center_reuses_web_snapshot(monkeypatch):
    expected = {
        "available": True,
        "report_date": "2026-07-13",
        "core_metrics": {"sales": {"value": 18100, "status": "ready"}},
        "major_risks": [],
        "today_actions": [],
    }
    shared_snapshot = AsyncMock(return_value=expected)
    monkeypatch.setattr(mobile, "get_command_center_snapshot", shared_snapshot)
    db = SimpleNamespace()

    result = await mobile.mobile_command_center(
        stat_date="2026-07-13",
        current_user=SimpleNamespace(id=1),
        db=db,
    )

    shared_snapshot.assert_awaited_once_with(db, date(2026, 7, 13))
    assert result["success"] is True
    assert result["data"] == expected
