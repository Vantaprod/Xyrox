"""
Xyrox — Configuration (Phase 1, corrected)

Uses Pydantic V2 style (model_config = ConfigDict(...)) to avoid
the deprecation warning from the old `class Config:` style.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Xyrox"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Security
    SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION_TO_A_RANDOM_STRING"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # AI Provider
    AI_PROVIDER: str = "local"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    AI_MODEL: str = "llama3"

    # Timezone
    TZ: str = "Africa/Lagos"
    # Telegram (Phase 7.1)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_CHAT_IDS: str = ""

    # Email (Phase 7.2)
    EMAIL_IMAP_HOST: str = ""
    EMAIL_IMAP_PORT: int = 993
    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_USER: str = ""
    EMAIL_PASSWORD: str = ""

    # Telephony (Phase 7.4) — NOT CONFIGURED by default
    TELEPHONY_PROVIDER: str = ""
    TELEPHONY_API_KEY: str = ""
    TELEPHONY_USERNAME: str = ""
    TELEPHONY_FROM_NUMBER: str = ""

@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()