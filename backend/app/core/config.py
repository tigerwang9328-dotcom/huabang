from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    # 应用
    APP_ENV: str = "development"
    APP_SECRET_KEY: str
    APP_DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "huabang_ai"
    DB_USER: str = "huabang"
    DB_PASSWORD: str

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
