from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "spoken-english-ai"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./spoken_english_ai.db"
    llm_provider: str = "disabled"
    speech_to_text_provider: str = "disabled"
    text_to_speech_provider: str = "disabled"
    auto_create_tables: bool = True
    temporary_audio_expiration_hours: int = 24
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "spoken-english-ai"
    jwt_audience: str = "spoken-english-ai-api"
    access_token_lifetime_minutes: int = 15
    refresh_token_lifetime_days: int = 30
    password_minimum_length: int = 12
    password_maximum_bytes: int = 72
    login_attempt_limit: int = 5

    model_config = SettingsConfigDict(
        env_prefix="SPOKEN_ENGLISH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
