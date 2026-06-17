from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    HOST: str = "127.0.0.1"
    PORT: int = 3306
    USER: str = "root"
    PASSWORD: str = ""
    DATABASE: str = "ai_assistant"
    POOL_SIZE: int = 20
    POOL_TIMEOUT: int = 30

    @property
    def async_url(self) -> str:
        return f"mysql+aiomysql://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DATABASE}?charset=utf8mb4"

    @property
    def sync_url(self) -> str:
        return f"mysql+pymysql://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DATABASE}?charset=utf8mb4"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    JWT_PRIVATE_KEY_PATH: str = ""
    JWT_PUBLIC_KEY_PATH: str = ""
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    VERIFICATION_CODE_LENGTH: int = 6
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 5
    VERIFICATION_CODE_MAX_ATTEMPTS: int = 3

    SEND_CODE_COOLDOWN_SECONDS: int = 60
    SEND_CODE_DAILY_LIMIT: int = 5
    LOGIN_FAILURE_LOCKOUT_THRESHOLD: int = 5
    LOGIN_FAILURE_LOCKOUT_WINDOW_MINUTES: int = 15
    LOGIN_FAILURE_LOCKOUT_DURATION_MINUTES: int = 30
    IP_RATE_LIMIT_PER_MINUTE: int = 100
    IP_ANOMALY_EMAIL_THRESHOLD: int = 10
    IP_ANOMALY_WINDOW_HOURS: int = 1


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    MODEL_NAME: str = "gpt-4o-mini"
    API_KEY: str = ""
    API_BASE: str | None = None
    TEMPERATURE: float = 0.1
    MAX_TOKENS: int = 4096


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SKILLS_DIR: str = ".agents/skills"
    SANDBOX_TIMEOUT_SECONDS: int = 30
    SANDBOX_CPU_LIMIT_PERCENT: int = 50
    SANDBOX_MEMORY_LIMIT_MB: int = 512
    SSE_HEARTBEAT_SECONDS: int = 30
    SSE_MAX_CONNECTIONS_PER_CLIENT: int = 5
    SSE_MAX_MESSAGE_SIZE_MB: int = 10


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:*", "electron://*"]
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db: DatabaseSettings = DatabaseSettings()
    auth: AuthSettings = AuthSettings()
    llm: LLMSettings = LLMSettings()
    agent: AgentSettings = AgentSettings()
    app: AppSettings = AppSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
