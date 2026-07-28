from dataclasses import dataclass


@dataclass(frozen=True)
class UsageLimits:
    learner_requests_per_day: int = 100
    account_requests_per_day: int = 200
    voice_session_requests: int = 30
    maximum_audio_duration_seconds: int = 120
    maximum_transcript_length: int = 4000
    maximum_tts_characters: int = 2000
    maximum_provider_retries: int = 2
