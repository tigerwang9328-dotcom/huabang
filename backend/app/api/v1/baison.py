"""百胜 E3ERP 开放平台 API 联调测试接口。"""
import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.integrations.baison.exceptions import BaisonError
from app.integrations.baison.services.shop_service import SHOP_LIST_METHOD, sync_shop_list

logger = logging.getLogger("baison.api")

router = APIRouter(prefix="/integrations/baison", tags=["百胜E3ERP对接"])


class ShopListTestRequest(BaseModel):
    page: int = 1
    page_size: int = 20


@router.post("/test/shop-list")
async def test_shop_list(req: ShopListTestRequest):
    """联调测试：调用 base.shop.get_list 获取商店档案。

    返回脱敏后的请求参数与百胜原始响应。
    """
    try:
        # sync_shop_list 内部用同步 httpx，放线程池避免阻塞事件循环
        result = await run_in_threadpool(sync_shop_list, req.page, req.page_size)
        return {
            "success": True,
            "method": result["method"],
            "request_params": result["request_params"],  # 已脱敏
            "raw_response": result["raw_response"],        # 百胜原始响应
        }
    except BaisonError as exc:
        # 已知业务/配置/请求异常，返回脱敏错误信息
        logger.warning("baison shop-list test failed: %s", exc.__class__.__name__)
        return {
            "success": False,
            "method": SHOP_LIST_METHOD,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    except Exception:
        # 兜底：不外泄内部细节
        logger.exception("baison shop-list unexpected error")
        return {
            "success": False,
            "method": SHOP_LIST_METHOD,
            "error": "内部错误，请查看服务日志",
        }
