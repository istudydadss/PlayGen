"""PlayGen 平台配置管理"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置，支持环境变量和 .env 文件"""

    # 应用基础
    APP_NAME: str = "PlayGen"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "playgen-secret-key-change-in-production"

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://playgen:playgen123@localhost:5432/playgen"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "playgen"
    MINIO_SECURE: bool = False

    # Playwright
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 30000
    RESPONSE_BODY_MAX_SIZE: int = 1_048_576  # 1MB

    # 执行器
    EXECUTION_TIMEOUT: int = 300  # 秒
    EXECUTION_MAX_RETRIES: int = 3

    # 脱敏字段
    SENSITIVE_FIELD_NAMES: list[str] = [
        "password", "token", "accessToken", "refreshToken",
        "secret", "cookie", "authorization", "phone", "idCard"
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
