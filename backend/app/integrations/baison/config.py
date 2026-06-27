"""百胜 E3ERP 开放平台配置读取。

统一从全局 settings（app/core/config.py）取值，禁止在代码中硬编码
AppKey / AppSecret。本模块只做读取与归一化，不持有任何明文密钥常量。
"""
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class BaisonConfig:
    base_url: str
    app_key: str
    app_secret: str
    sign_method: str
    api_version: str   # 公共参数 v，百胜文档要求 2.0
    format: str        # 公共参数 format，固定 json
    page_size: int
    http_method: str   # GET / POST，可在 .env 配置


def get_baison_config() -> BaisonConfig:
    """从环境配置构造百胜对接配置对象。"""
    return BaisonConfig(
        base_url=(settings.BAISON_API_BASE_URL or "").strip(),
        app_key=(settings.BAISON_APP_KEY or "").strip(),
        app_secret=(settings.BAISON_APP_SECRET or "").strip(),
        sign_method=(settings.BAISON_SIGN_METHOD or "md5").strip().lower(),
        api_version=(settings.BAISON_API_VERSION or "2.0").strip(),
        format=(settings.BAISON_FORMAT or "json").strip().lower(),
        page_size=int(settings.BAISON_PAGE_SIZE or 20),
        http_method=(settings.BAISON_HTTP_METHOD or "POST").strip().upper(),
    )
