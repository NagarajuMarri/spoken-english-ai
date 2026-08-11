from email.utils import parseaddr
from functools import lru_cache
from urllib.parse import urlsplit

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
    language_review_provider: str = "disabled"
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
    password_reset_token_lifetime_minutes: int = 10
    password_reset_code_max_attempts: int = 5
    password_reset_resend_cooldown_seconds: int = 60
    password_reset_minimum_response_milliseconds: int = 250
    password_reset_job_max_attempts: int = 3
    password_reset_job_idempotency_ttl_seconds: int = 3_600
    password_reset_job_retry_delay_seconds: int = 5
    password_reset_delivery_provider: str = "development_file"
    password_reset_development_outbox_path: str = ".local-password-reset-outbox.jsonl"
    password_reset_email_from: str = "no-reply@example.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_timeout_seconds: int = 10
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
    openai_llm_fast_model: str = "gpt-4.1-mini"
    openai_llm_model: str = "gpt-5-mini"
    openai_llm_timeout_seconds: int = 45
    openai_llm_max_retries: int = 0
    openai_llm_reasoning_effort: str = "minimal"
    openai_llm_max_output_tokens: int = 1024
    openai_llm_input_usd_per_million: float = 0.25
    openai_llm_cached_input_usd_per_million: float = 0.025
    openai_llm_output_usd_per_million: float = 2.0
    openai_language_review_model: str = "gpt-4.1-mini"
    openai_language_review_timeout_seconds: int = 45
    openai_language_review_max_retries: int = 0
    openai_language_review_reasoning_effort: str = "minimal"
    openai_language_review_max_output_tokens: int = 1024
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_timeout_seconds: int = 30
    openai_tts_max_retries: int = 0
    openai_tts_response_format: str = "mp3"
    openai_tts_ananya_voice: str = "marin"
    openai_tts_arjun_voice: str = "cedar"
    openai_tts_speed: float = 1.0
    realtime_voice_enabled: bool = False
    openai_realtime_model: str = "gpt-realtime-2.1"
    openai_realtime_voice: str = "marin"
    openai_realtime_connect_timeout_seconds: int = 15
    realtime_vad_threshold: float = 0.5
    realtime_vad_prefix_padding_ms: int = 300
    realtime_vad_silence_ms: int = 500
    realtime_sdp_max_bytes: int = 100_000
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
        if (
            self.environment != "test"
            and self.llm_provider == "openai"
            and self.language_review_provider != "openai"
        ):
            raise ValueError(
                "language_review_provider must be openai when llm_provider is openai"
            )
        if not 1 <= self.openai_llm_timeout_seconds <= 60:
            raise ValueError("openai_llm_timeout_seconds must be between 1 and 60")
        if self.openai_llm_max_retries not in {0, 1}:
            raise ValueError("openai_llm_max_retries must be 0 or 1")
        if self.openai_llm_reasoning_effort not in {"minimal", "low", "medium", "high"}:
            raise ValueError("openai_llm_reasoning_effort must be minimal, low, medium, or high")
        if not 1024 <= self.openai_llm_max_output_tokens <= 25_000:
            raise ValueError("openai_llm_max_output_tokens must be between 1024 and 25000")
        if not 1 <= self.openai_language_review_timeout_seconds <= 60:
            raise ValueError("openai_language_review_timeout_seconds must be between 1 and 60")
        if self.openai_language_review_max_retries not in {0, 1}:
            raise ValueError("openai_language_review_max_retries must be 0 or 1")
        if self.openai_language_review_reasoning_effort not in {"minimal", "low", "medium", "high"}:
            raise ValueError("openai_language_review_reasoning_effort is unsupported")
        if not 1024 <= self.openai_language_review_max_output_tokens <= 8192:
            raise ValueError("openai_language_review_max_output_tokens must be between 1024 and 8192")
        if not 1 <= self.openai_tts_timeout_seconds <= 60:
            raise ValueError("openai_tts_timeout_seconds must be between 1 and 60")
        if self.openai_tts_max_retries != 0:
            raise ValueError("openai_tts_max_retries must be 0 for controlled paid synthesis")
        if self.openai_tts_response_format != "mp3":
            raise ValueError("openai_tts_response_format must be mp3 for RC1 browser acceptance")
        supported_tts_voices = {
            "alloy", "ash", "ballad", "coral", "echo", "fable", "nova",
            "onyx", "sage", "shimmer", "verse", "marin", "cedar",
        }
        if self.openai_tts_ananya_voice not in supported_tts_voices:
            raise ValueError("openai_tts_ananya_voice is unsupported")
        if self.openai_tts_arjun_voice not in supported_tts_voices:
            raise ValueError("openai_tts_arjun_voice is unsupported")
        if not 0.5 <= self.openai_tts_speed <= 2:
            raise ValueError("openai_tts_speed must be between 0.5 and 2")
        if not 5 <= self.openai_realtime_connect_timeout_seconds <= 30:
            raise ValueError("openai_realtime_connect_timeout_seconds must be between 5 and 30")
        if not 0 <= self.realtime_vad_threshold <= 1:
            raise ValueError("realtime_vad_threshold must be between 0 and 1")
        if not 200 <= self.realtime_vad_prefix_padding_ms <= 1_000:
            raise ValueError("realtime_vad_prefix_padding_ms must be between 200 and 1000")
        if not 500 <= self.realtime_vad_silence_ms <= 1_000:
            raise ValueError("realtime_vad_silence_ms must be between 500 and 1000")
        if not 0 <= self.password_reset_minimum_response_milliseconds <= 2_000:
            raise ValueError(
                "password_reset_minimum_response_milliseconds must be between 0 and 2000"
            )
        if not 1 <= self.password_reset_job_max_attempts <= 5:
            raise ValueError("password_reset_job_max_attempts must be between 1 and 5")
        if not 1 <= self.password_reset_job_retry_delay_seconds <= 60:
            raise ValueError("password_reset_job_retry_delay_seconds must be between 1 and 60")
        if (
            self.password_reset_job_idempotency_ttl_seconds
            < self.password_reset_token_lifetime_minutes * 60
        ):
            raise ValueError(
                "password_reset_job_idempotency_ttl_seconds must cover the reset token lifetime"
            )
        if not 10 <= self.worker_heartbeat_ttl_seconds <= 300:
            raise ValueError("worker_heartbeat_ttl_seconds must be between 10 and 300")
        if not 1 <= self.smtp_port <= 65_535:
            raise ValueError("smtp_port must be between 1 and 65535")
        if not 1 <= self.smtp_timeout_seconds <= 60:
            raise ValueError("smtp_timeout_seconds must be between 1 and 60")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("smtp_username and smtp_password must be configured together")
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
        if self.llm_provider != "openai":
            missing.append("llm_provider")
        elif not self.openai_api_key:
            missing.append("openai_api_key")
        if self.speech_to_text_provider != "openai":
            missing.append("speech_to_text_provider")
        elif not self.openai_api_key:
            missing.append("openai_api_key")
        if self.text_to_speech_provider != "openai":
            missing.append("text_to_speech_provider")
        elif not self.openai_api_key:
            missing.append("openai_api_key")
        if self.language_review_provider != "openai":
            missing.append("language_review_provider")
        elif not self.openai_api_key:
            missing.append("openai_api_key")
        if self.razorpay_enabled and not self.razorpay_webhook_secret:
            missing.append("razorpay_webhook_secret")
        if self.razorpay_enabled and self.razorpay_mode != "test":
            missing.append("razorpay_test_mode")
        redis_url = urlsplit(self.redis_url)
        if not self.redis_required:
            missing.append("redis_required")
        if redis_url.scheme != "rediss" or not redis_url.hostname:
            missing.append("redis_url")
        if not self.worker_enabled:
            missing.append("worker_enabled")
        if self.object_storage_backend not in {"local", "s3"}:
            missing.append("object_storage_backend")
        if self.object_storage_backend == "s3" and not self.object_storage_bucket:
            missing.append("object_storage_bucket")
        if self.object_storage_backend == "local":
            missing.append("object_storage_backend")
        frontend_url = urlsplit(self.public_frontend_url)
        if (
            frontend_url.scheme != "https"
            or not frontend_url.hostname
            or frontend_url.username is not None
            or frontend_url.password is not None
            or frontend_url.query
            or frontend_url.fragment
        ):
            missing.append("public_frontend_url")
        _, sender_address = parseaddr(self.password_reset_email_from)
        sender_domain = sender_address.rpartition("@")[2].casefold()
        if (
            not sender_address
            or not sender_domain
            or sender_domain in {"example.com", "example.org", "example.net", "example.invalid", "localhost"}
            or sender_domain.endswith(".invalid")
        ):
            missing.append("password_reset_email_from")
        smtp_host = self.smtp_host.strip().casefold()
        if self.password_reset_delivery_provider != "smtp":
            missing.append("password_reset_delivery_provider")
        if not smtp_host or smtp_host in {"smtp_host", "smtp.example.com"} or smtp_host.endswith(".invalid"):
            missing.append("smtp_host")
        if not self.smtp_username or self.smtp_username == "FROM_SECRET_STORE":
            missing.append("smtp_username")
        if not self.smtp_password or self.smtp_password == "FROM_SECRET_STORE":
            missing.append("smtp_password")
        if self.password_reset_minimum_response_milliseconds < 200:
            missing.append("password_reset_minimum_response_milliseconds")
        if missing:
            raise ValueError("Unsafe production configuration; missing: " + ", ".join(dict.fromkeys(missing)))
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
            "language_review_provider": self.language_review_provider,
            "speech_to_text_provider": self.speech_to_text_provider,
            "text_to_speech_provider": self.text_to_speech_provider,
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
        reset_delivery_ready = (
            (
                self.password_reset_delivery_provider == "smtp"
                and bool(self.smtp_host)
                and bool(self.smtp_username)
                and bool(self.smtp_password)
            )
            or (self.environment != "production" and self.password_reset_delivery_provider == "development_file")
            or (self.environment == "test" and self.password_reset_delivery_provider == "memory")
        )
        return (
            self.llm_provider in {"disabled", "fake", "rule_based", "openai"}
            and self.speech_to_text_provider in {"disabled", "fake", "openai"}
            and self.text_to_speech_provider in {"disabled", "fake", "openai"}
            and self.language_review_provider in {"disabled", "fake", "openai"}
            and ("openai" not in {
                self.llm_provider,
                self.speech_to_text_provider,
                self.text_to_speech_provider,
                self.language_review_provider,
            } or bool(self.openai_api_key))
            and reset_delivery_ready
            and (
                self.environment != "production"
                or (self.redis_required and bool(self.redis_url) and self.worker_enabled)
            )
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
