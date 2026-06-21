"""商店档案（base.shop.get_list）服务。

当前阶段仅做接口联通验证，返回原始响应，不做复杂清洗。
"""
import logging
from typing import Optional

from app.integrations.baison.client import BaisonClient

logger = logging.getLogger("baison.shop_service")

SHOP_LIST_METHOD = "base.shop.get_list"


def sync_shop_list(page: int = 1, page_size: int = 20, client: Optional[BaisonClient] = None) -> dict:
    """调用 base.shop.get_list 获取商店档案信息。

    :return: dict，包含 method / request_params(脱敏) / status_code / raw_response / data。
    """
    client = client or BaisonClient()
    resp = client.request(SHOP_LIST_METHOD, {"page": page, "page_size": page_size})
    return {
        "method": SHOP_LIST_METHOD,
        "request_params": resp.request_params,  # 已脱敏
        "status_code": resp.status_code,
        "raw_response": resp.raw_response,       # 百胜原始响应
        "data": resp.data,
    }
