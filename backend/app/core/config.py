from functools import lru_cache

from pydantic import model_validator
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
    commercial_monthly_price_inr: int = 299
    commercial_yearly_price_inr: int = 2999
    commercial_trial_days: int = 7
    commercial_free_daily_conversations: int = 5
    commercial_free_daily_voice_minutes: int = 5
    commercial_free_daily_grammar_checks: int = 5
    commercial_free_daily_pronunciation_checks: int = 3
    commercial_premium_fair_use_daily_requests: int = 200
    commercial_premium_voice_minutes: int = 120
    commercial_monthly_ai_cost_limit_usd: float = 20
    commercial_trial_daily_requests: int = 50
    commercial_monthly_request_limit: int = 5000
    commercial_token_limit: int = 500000
    commercial_advertisements_enabled: bool = False
    commercial_premium_tutors_enabled: bool = True
    razorpay_enabled: bool = False
    razorpay_webhook_secret: str = ""
    public_frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    force_https: bool = False
    secure_cookies: bool = False
    request_size_limit_bytes: int = 2_000_000
    upload_size_limit_bytes: int = 10_000_000
    database_pool_size: int = 5
    database_pool_timeout_seconds: int = 10
    database_connect_timeout_seconds: int = 10
    redis_url: str = ""
    redis_required: bool = False
    object_storage_backend: str = "local"
    object_storage_bucket: str = ""
    object_storage_endpoint: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_retention_hours: int = 24
    openai_api_key: str = ""
    openai_llm_model: str = "gpt-5-mini"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    tracing_enabled: bool = False
    maintenance_mode: bool = False
    product_name: str = "SpeakMate"
    release_version: str = "1.0.0-rc1"
    closed_beta_enabled: bool = True
    beta_invite_code: str = ""
    beta_invite_codes: str = ""
    beta_allowlist: str = ""
    founder_emails: str = ""
    razorpay_mode: str = "test"
    support_email: str = "support@example.com"

    def beta_codes(self) -> set[str]:
        return {item.strip() for item in (self.beta_invite_codes or self.beta_invite_code).split(",") if item.strip()}

    def beta_allowed_emails(self) -> set[str]:
        return {item.strip().lower() for item in self.beta_allowlist.split(",") if item.strip()}

    def founders(self) -> set[str]:
        return {item.strip().lower() for item in self.founder_emails.split(",") if item.strip()}
    worker_enabled: bool = False
    worker_heartbeat_key: str = "spoken-english:worker:heartbeat"
    worker_heartbeat_ttl_seconds: int = 30

    @model_validator(mode="after")
    def validate_environment(self):
        if self.environment != "production":
            return self
        missing = []
        if not self.database_url.startswith("postgresql"):
            missing.append("database_url")
        if not self.jwt_secret and self.jwt_verification_keys_json == "{}":
            missing.append("jwt_signing_keys")
        else:
            try:
                if any(len(value) < 32 for value in self.signing_keys().values()):
                    missing.append("jwt_signing_keys")
            except (TypeError, ValueError):
                missing.append("jwt_signing_keys")
        if not self.force_https:
            missing.append("force_https")
        if not self.secure_cookies:
            missing.append("secure_cookies")
        if not self.cors_origins or "*" in self.cors_origins:
            missing.append("cors_origins")
        if not self.trusted_hosts or "*" in self.trusted_hosts:
            missing.append("trusted_hosts")
        if self.llm_provider == "openai" and not self.openai_api_key:
            missing.append("openai_api_key")
        if self.razorpay_enabled and not self.razorpay_webhook_secret:
            missing.append("razorpay_webhook_secret")
        if self.razorpay_enabled and self.razorpay_mode != "test":
            missing.append("razorpay_test_mode")
        if self.redis_required and not self.redis_url:
            missing.append("redis_url")
        if self.object_storage_backend not in {"local", "s3"}:
            missing.append("object_storage_backend")
        if self.object_storage_backend == "s3" and not self.object_storage_bucket:
            missing.append("object_storage_bucket")
        if self.object_storage_backend == "local":
            missing.append("object_storage_backend")
        if missing:
            raise ValueError("Unsafe production configuration; missing: " + ", ".join(missing))
        if self.debug or self.auto_create_tables:
            raise ValueError("Production requires debug=false and auto_create_tables=false")
        return self

    def safe_summary(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "database": "postgresql" if self.database_url.startswith("postgresql") else "sqlite",
            "redis_configured": bool(self.redis_url),
            "object_storage_backend": self.object_storage_backend,
            "llm_provider": self.llm_provider,
            "razorpay_enabled": self.razorpay_enabled,
            "build_identifier": self.build_identifier,
        }

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
        return (
            self.llm_provider in {"disabled", "fake", "rule_based", "openai"}
            and self.speech_to_text_provider in {"disabled", "fake", "openai"}
            and self.text_to_speech_provider in {"disabled", "fake", "openai"}
            and ("openai" not in {
                self.llm_provider,
                self.speech_to_text_provider,
                self.text_to_speech_provider,
            } or bool(self.openai_api_key))
        )

    model_config = SettingsConfigDict(
        env_prefix="SPOKEN_ENGLISH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
