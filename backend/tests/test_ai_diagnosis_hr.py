import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_hr():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).hr()
    await engine.dispose()
    return result


def test_hr_uses_dingtalk_employee_and_attendance_data():
    result = asyncio.run(_run_hr())
    summary = result["summary"]

    assert summary["employee_count"] >= 30
    assert summary["attendance_stat_date"]
    assert summary["attendance_employee_count"] > 0
    assert summary["attendance_abnormal_count"] >= 0
