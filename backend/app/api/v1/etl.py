from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.v1.deps import get_current_user, require_permission
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/etl", tags=["ETL数据处理"])

@router.post("/run", response_model=ApiResponse)
async def run_etl(
    stat_date: str = None,
    step: str = "full",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: SysUser = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发ETL。step: full|ods_to_dwd|dwd_to_dws|dws_to_dm"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    
    from app.services.etl.pipeline import ETLPipeline
    pipeline = ETLPipeline()
    
    async def _run():
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            if step == "full":
                result = await pipeline.run_full(stat_date, session)
            else:
                result = await pipeline.run_step(step, stat_date, session)
            logger.info(f"ETL完成: {result}")
    
    background_tasks.add_task(_run)
    return ApiResponse.ok(data={"stat_date": stat_date, "step": step}, message="ETL已触发，在后台执行")

@router.get("/status", response_model=ApiResponse)
async def get_etl_status(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """获取最近ETL状态"""
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT task_name, status, stat_date,
               to_char(started_at, 'YYYY-MM-DD HH24:MI:SS') as started_at,
               to_char(finished_at, 'YYYY-MM-DD HH24:MI:SS') as finished_at,
               input_rows, output_rows, error_msg
        FROM log.log_etl_run
        ORDER BY started_at DESC LIMIT 10
    """))
    rows = [dict(r._mapping) for r in result.fetchall()]
    latest = rows[0] if rows else None
    return ApiResponse.ok(data={"latest": latest, "recent": rows})

@router.get("/logs", response_model=ApiResponse)
async def get_etl_logs(
    page: int = 1,
    page_size: int = 20,
    stat_date: str = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    where = "WHERE 1=1"
    params = {}
    if stat_date:
        where += " AND stat_date = :stat_date"
        params["stat_date"] = stat_date
    
    count_r = await db.execute(text(f"SELECT count(*) FROM log.log_etl_run {where}"), params)
    total = count_r.scalar()
    
    offset = (page - 1) * page_size
    rows_r = await db.execute(text(f"""
        SELECT task_name, status, stat_date,
               to_char(started_at, 'YYYY-MM-DD HH24:MI:SS') as started_at,
               to_char(finished_at, 'YYYY-MM-DD HH24:MI:SS') as finished_at,
               input_rows, output_rows, error_msg, is_retryable
        FROM log.log_etl_run {where}
        ORDER BY started_at DESC LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": offset})
    
    items = [dict(r._mapping) for r in rows_r.fetchall()]
    return ApiResponse.ok(data={"total": total, "page": page, "page_size": page_size, "items": items})
