import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

async def run_etl_pipeline(stat_date: str = None):
    """定时触发ETL Pipeline"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    try:
        from app.services.etl.pipeline import ETLPipeline
        from app.core.database import AsyncSessionLocal
        pipeline = ETLPipeline()
        async with AsyncSessionLocal() as db:
            result = await pipeline.run_full(stat_date, db)
            logger.info(f"定时ETL完成: {result}")
    except Exception as e:
        logger.error(f"定时ETL失败: {e}", exc_info=True)
