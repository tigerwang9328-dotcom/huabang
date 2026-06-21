"""百胜 E3ERP 开放平台 HTTP 客户端。

负责：填充公共参数 -> 生成签名 -> 拼装并发起 HTTP 请求 -> 返回响应（含 raw_response）。

安全约束：
- AppSecret 只用于本地签名计算，绝不放进请求参数、绝不写日志。
- 日志中的参数全部脱敏（sign 截断展示）。
"""
import json
import logging
import time
from typing import Optional

import httpx

from app.integrations.baison.auth import generate_sign
from app.integrations.baison.config import BaisonConfig, get_baison_config
from app.integrations.baison.exceptions import BaisonConfigError, BaisonRequestError

logger = logging.getLogger("baison.client")

# 日志脱敏：这些 key 一旦出现一律打码（兜底，正常请求参数里不应含 secret）
_SENSITIVE_KEYS = {"app_secret", "appsecret", "secret"}


def mask_params(params: dict) -> dict:
    """对请求参数做脱敏，用于日志与对外返回。"""
    masked = {}
    for key, value in params.items():
        if key.lower() in _SENSITIVE_KEYS:
            masked[key] = "***"
        elif key == "sign" and isinstance(value, str) and len(value) > 8:
            masked[key] = f"{value[:4]}***{value[-4:]}"
        else:
            masked[key] = value
    return masked


class BaisonResponse:
    """百胜响应封装，保留原始响应文本。"""

    def __init__(self, status_code: int, raw_response: str, data, request_params: dict):
        self.status_code = status_code
        self.raw_response = raw_response  # 原始响应文本，未做任何清洗
        self.data = data                  # 解析后的 json（解析失败为 None）
        self.request_params = request_params  # 已脱敏的请求参数


class BaisonClient:
    """百胜开放平台调用客户端。"""

    def __init__(self, config: Optional[BaisonConfig] = None):
        self.config = config or get_baison_config()

    def _validate(self) -> None:
        if not self.config.base_url:
            raise BaisonConfigError("BAISON_API_BASE_URL 未配置")
        if not self.config.app_key or not self.config.app_secret:
            raise BaisonConfigError("BAISON_APP_KEY / BAISON_APP_SECRET 未配置")

    def _build_params(self, method: str, params: Optional[dict]) -> dict:
        """合并业务参数与公共参数，并生成 sign。"""
        # 业务参数（剔除 None）
        full = {k: v for k, v in (params or {}).items() if v is not None}
        # 公共参数
        full.update(
            {
                "app_key": self.config.app_key,
                "method": method,
                "sign_method": self.config.sign_method,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "format": "json",
            }
        )
        # 生成签名（app_secret 仅用于计算，不进入 full）
        full["sign"] = generate_sign(full, self.config.app_secret)
        return full

    def request(self, method: str, params: Optional[dict] = None, *, timeout: float = 30.0) -> BaisonResponse:
        """发起一次百胜 API 调用。

        :param method: 百胜接口名，如 base.shop.get_list。
        :param params: 业务参数。
        :return: BaisonResponse。
        :raises BaisonConfigError: 配置缺失。
        :raises BaisonRequestError: HTTP 层失败（已脱敏）。
        """
        self._validate()
        full_params = self._build_params(method, params)
        masked = mask_params(full_params)
        http_method = self.config.http_method

        logger.info(
            "baison request method=%s http=%s url=%s params=%s",
            method, http_method, self.config.base_url, masked,
        )

        try:
            with httpx.Client(timeout=timeout) as client:
                if http_method == "GET":
                    resp = client.get(self.config.base_url, params=full_params)
                else:
                    resp = client.post(self.config.base_url, data=full_params)
        except httpx.HTTPError as exc:
            # 不打印异常详情中可能携带的敏感 URL 参数，仅记录类型
            logger.error("baison http error method=%s err_type=%s", method, exc.__class__.__name__)
            raise BaisonRequestError(f"HTTP 请求失败: {exc.__class__.__name__}") from exc

        raw_text = resp.text
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            data = None

        logger.info(
            "baison response method=%s status=%s body_len=%s",
            method, resp.status_code, len(raw_text or ""),
        )

        return BaisonResponse(
            status_code=resp.status_code,
            raw_response=raw_text,
            data=data,
            request_params=masked,
        )
