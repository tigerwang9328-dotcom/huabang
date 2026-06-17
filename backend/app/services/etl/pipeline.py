"""ETL Pipeline 总调度器：ODS → DWD → DWS → DM"""
import traceback
from datetime import date, timedelta
from typing import Optional

from .etl_log import ETLLogger
from .ods_to_dwd import OdsToDwd
from .dwd_to_dws import DwdToDws
from .dws_to_dm import DwsToDm


class ETLPipeline:
    STEP_ORDER = ["ods_to_dwd", "dwd_to_dws", "dws_to_dm"]

    def __init__(self):
        self._steps = {
            "ods_to_dwd": OdsToDwd(),
            "dwd_to_dws": DwdToDws(),
            "dws_to_dm": DwsToDm(),
        }
        self._etl_log = ETLLogger()

    async def run_full(self, stat_date: Optional[str] = None, db=None) -> dict:
        if stat_date is None:
            stat_date = (date.today() - timedelta(days=1)).isoformat()
        steps_result = []
        failed_count = 0
        for step_name in self.STEP_ORDER:
            step_info = await self._run_step(step_name, stat_date, db)
            steps_result.append(step_info)
            if step_info["status"] == "failed":
                failed_count += 1
        overall = "success" if failed_count == 0 else ("failed" if failed_count == len(self.STEP_ORDER) else "partial")
        return {"stat_date": stat_date, "steps": steps_result, "status": overall}

    async def run_step(self, step_name: str, stat_date: str, db) -> dict:
        if step_name not in self.STEP_ORDER:
            raise ValueError(f"未知步骤: {step_name!r}")
        return await self._run_step(step_name, stat_date, db)

    async def _run_step(self, step_name: str, stat_date: str, db) -> dict:
        run_id = self._etl_log.start_task(f"pipeline_{step_name}", stat_date)
        try:
            runner = self._steps[step_name]
            rows = await runner.run(stat_date, db, self._etl_log)
            total = sum(rows.values()) if isinstance(rows, dict) else 0
            self._etl_log.finish_task(run_id, output_rows=total)
            return {"step": step_name, "status": "success", "rows": rows, "error": None}
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            self._etl_log.fail_task(run_id, error_msg)
            print(f"[ETLPipeline] {step_name} 失败: {exc}")
            try:
                await db.rollback()
            except Exception:
                pass
            return {"step": step_name, "status": "failed", "rows": None, "error": str(exc)}
