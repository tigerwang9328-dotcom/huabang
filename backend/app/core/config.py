from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    # 应用
    APP_ENV: str = "development"
    APP_SECRET_KEY: str
    APP_DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # 抖音颜色分析：仅在受控上线阶段显式开启采集控制面。
    DOUYIN_COLOR_COLLECTION_ENABLED: bool = False

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "huabang_ai"
    DB_USER: str = "huabang"
    DB_PASSWORD: str

    # Finance V2 uses a separate, least-privilege login.  Do not fall back to
    # the shared application account when any value is absent.
    FINANCE_DB_HOST: Optional[str] = None
    FINANCE_DB_PORT: Optional[int] = None
    FINANCE_DB_NAME: Optional[str] = None
    FINANCE_DB_USER: Optional[str] = None
    FINANCE_DB_PASSWORD: Optional[str] = None

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI - 阿里云百炼
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen-plus"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # AI - DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # AI经营顾问（确定性事实之外的解释和候选行动）
    AI_BUSINESS_ADVICE_ENABLED: bool = False
    AI_BUSINESS_ADVICE_MODEL: str = "deepseek-v4-pro"
    AI_BUSINESS_ADVICE_CONCURRENCY: int = 3
    AI_BUSINESS_ADVICE_TIMEOUT_SECONDS: int = 60
    AI_BUSINESS_ADVICE_BATCH_TIME: str = "06:45"
    AI_BUSINESS_ADVICE_REFRESH_WINDOW_SECONDS: int = 600

    # 投流决策历史与 DeepSeek 增强
    INVESTMENT_AI_ENABLED: bool = True
    INVESTMENT_AI_MODEL: str = "deepseek-chat"
    INVESTMENT_AI_TIMEOUT_SECONDS: int = 45
    INVESTMENT_AI_MIN_INTERVAL_MINUTES: int = 60
    INVESTMENT_AI_MAX_BUDGET_FEN: int = 30000

    # 老板 AI 助手（只读聊天入口）
    AI_ASSISTANT_ENABLED: bool = True
    AI_ASSISTANT_WEB_SEARCH_ENABLED: bool = False
    TAVILY_API_KEY: str = ""
    AI_ASSISTANT_TAVILY_TIMEOUT_SECONDS: int = 12
    AI_ASSISTANT_TAVILY_CACHE_SECONDS: int = 21600
    AI_ASSISTANT_TAVILY_MAX_RESULTS: int = 5
    AI_ASSISTANT_HISTORY_RETENTION_DAYS: int = 30
    AI_ASSISTANT_RATE_LIMIT_PER_MINUTE: int = 6

    # AI 默认提供商
    AI_PROVIDER: str = "deepseek"

    # 钉钉
    DINGTALK_APP_ID: str = ""
    DINGTALK_AGENT_ID: str = ""
    DINGTALK_CLIENT_ID: str = ""
    DINGTALK_CLIENT_SECRET: str = ""
    DINGTALK_ROBOT_WEBHOOK: str = ""
    DINGTALK_PUSH_ENABLED: bool = False
    DINGTALK_MAX_PUSH_PER_HOUR: int = 1
    DINGTALK_TEST_WEBHOOK: str = ""
    DINGTALK_TEST_MODE: bool = True
    DINGTALK_STREAM_ENABLED: bool = False
    DINGTALK_ENABLED: bool = False
    DINGTALK_CALLBACK_TOKEN: str = ""
    DINGTALK_CALLBACK_AES_KEY: str = ""
    DINGTALK_CALLBACK_URL: str = ""

    # 百盛ERP
    BAISON_API_URL: str = ""
    BAISON_API_KEY: str = ""
    BAISON_API_ENABLED: bool = False

    # 百胜 E3ERP 开放平台（API 联调）
    BAISON_API_BASE_URL: str = ""
    BAISON_APP_KEY: str = ""
    BAISON_APP_SECRET: str = ""
    BAISON_SIGN_METHOD: str = "md5"
    BAISON_PAGE_SIZE: int = 20
    BAISON_HTTP_METHOD: str = "POST"  # GET / POST 可配置
    BAISON_API_VERSION: str = "2.0"
    BAISON_FORMAT: str = "json"

    # 金蝶
    KINGDEE_API_URL: str = ""
    KINGDEE_API_KEY: str = ""
    KINGDEE_API_ENABLED: bool = False

    # 生意经采集
    LIFE_DATA_COLLECTOR_TOKEN_SHA256: str = ""
    LIFE_DATA_ACCOUNT_ID: str = "1798826701211732"
    LIFE_DATA_TASK_CREATOR_ID: int = 1
    LIFE_DATA_MAX_PAYLOAD_BYTES: int = 2_000_000

    # 文件上传
    UPLOAD_MAX_SIZE_MB: int = 50
    UPLOAD_ALLOWED_TYPES: str = "xlsx,xls,csv"

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def FINANCE_DATABASE_URL(self) -> str:
        values = {
            "FINANCE_DB_HOST": self.FINANCE_DB_HOST,
            "FINANCE_DB_PORT": self.FINANCE_DB_PORT,
            "FINANCE_DB_NAME": self.FINANCE_DB_NAME,
            "FINANCE_DB_USER": self.FINANCE_DB_USER,
            "FINANCE_DB_PASSWORD": self.FINANCE_DB_PASSWORD,
        }
        missing = [key for key, value in values.items() if value is None or value == ""]
        if missing:
            raise ValueError(
                "Finance V2 dedicated database settings are required: " + ", ".join(missing)
            )
        return URL.create(
            "postgresql+asyncpg",
            username=self.FINANCE_DB_USER,
            password=self.FINANCE_DB_PASSWORD,
            host=self.FINANCE_DB_HOST,
            port=self.FINANCE_DB_PORT,
            database=self.FINANCE_DB_NAME,
        ).render_as_string(hide_password=False)

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
