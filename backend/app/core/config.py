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
    jwt_active_key_id: str = "legacy"
    jwt_verification_keys_json: str = "{}"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "spoken-english-ai"
    jwt_audience: str = "spoken-english-ai-api"
    access_token_lifetime_minutes: int = 15
    refresh_token_lifetime_days: int = 30
    password_minimum_length: int = 12
    password_maximum_bytes: int = 72
    login_attempt_limit: int = 5
    build_identifier: str = "development"
    expose_development_metrics: bool = False
    audio_cleanup_batch_size: int = 100
    provider_sandbox_enabled: bool = False
    provider_sandbox_daily_budget_usd: float = 10
    provider_sandbox_monthly_budget_usd: float = 150
    provider_sandbox_per_user_budget_usd: float = 7.5
    provider_sandbox_daily_requests: int = 100
    provider_sandbox_per_user_requests: int = 10
    provider_sandbox_token_limit: int = 4096
    provider_sandbox_audio_seconds_limit: float = 120

    def signing_keys(self) -> dict[str, str]:
        import json
        def reject_duplicates(pairs):
            keys = {}
            for key, value in pairs:
                if key in keys:
                    raise ValueError("Duplicate JWT key IDs are not allowed.")
                keys[key] = value
            return keys

        keys = json.loads(self.jwt_verification_keys_json, object_pairs_hook=reject_duplicates)
        if not isinstance(keys, dict) or not all(
            isinstance(key, str) and key and isinstance(value, str)
            for key, value in keys.items()
        ):
            raise ValueError("JWT verification keys must be a string map.")
        if self.jwt_secret:
            keys.setdefault("legacy", self.jwt_secret)
        if self.jwt_active_key_id not in keys:
            raise ValueError("Active JWT key ID is not configured.")
        return keys

    def providers_ready(self) -> bool:
        allowed = {"disabled", "fake", "rule_based"}
        return all(provider in allowed for provider in (
            self.llm_provider,
            self.speech_to_text_provider,
            self.text_to_speech_provider,
        ))

    model_config = SettingsConfigDict(
        env_prefix="SPOKEN_ENGLISH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
