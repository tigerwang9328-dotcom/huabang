"""百胜 E3ERP 对接异常定义。"""


class BaisonError(Exception):
    """百胜对接基础异常。"""


class BaisonConfigError(BaisonError):
    """配置缺失或无效（如未配置 AppKey/AppSecret/BaseURL）。"""


class BaisonRequestError(BaisonError):
    """HTTP 请求或响应异常。

    注意：message 必须脱敏，不得包含 AppSecret 等敏感信息。
    """

    def __init__(self, message: str, status_code: int | None = None, raw_response: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
