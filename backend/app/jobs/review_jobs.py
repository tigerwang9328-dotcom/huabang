"""review_jobs - 晚间门店诊断（从push_jobs复用run_evening_diagnosis）"""
import logging

logger = logging.getLogger(__name__)


async def run_evening_diagnosis():
    """21:30 晚间门店诊断 + 推送"""
    from app.jobs.push_jobs import run_evening_diagnosis as _impl
    await _impl()
