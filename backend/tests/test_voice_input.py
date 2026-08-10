import io
import json
import wave
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.core.config import Settings
from backend.app.models import AIUsageRecord, Learner, ProviderCallEvent, VoiceTranscriptionAttempt
from backend.app.providers.stt.contracts import SpeechToTextRequest, SpeechToTextResult
from backend.app.providers.stt.openai_boundary import OpenAICompatibleSTTProvider, OpenAITranscriptionHTTPClient
from backend.app.transcript_safety import UnusableTranscript, safe_transcript
from backend.app.usage.service import ProviderCallLeaseLost, UsageService


def wav_fixture(duration_ms=250):
    frames = b"\x00\x00" * int(16_000 * duration_ms / 1000)
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(frames)
    return output.getvalue()


def transcribe(client, conversation_id, audio=None, **headers):
    values = {
        "Content-Type": "audio/wav", "X-Audio-Duration-Ms": "250",
        "X-Voice-Processing-Consent": "accepted",
        "Idempotency-Key": f"voice-{uuid4()}",
        **headers,
    }
    return client.post(
        f"/api/v1/conversations/{conversation_id}/transcriptions",
        content=wav_fixture() if audio is None else audio,
        headers=values,
    )


def test_real_audio_bytes_reach_stt_and_transcript_returns(client, conversation):
    received = {}

    class RecordingProvider:
        def transcribe(self, request):
            received.update({
                "audio": request.audio_bytes,
                "type": request.content_type,
                "duration": request.duration_seconds,
                "filename": request.filename,
                "language": request.language_hint,
            })
            return SpeechToTextResult(
                transcript="I practise English every morning.", detected_language="en", confidence=0.98,
                provider_job_id="recording-provider", duration_seconds=request.duration_seconds,
                usage_units=request.duration_seconds, processing_status="SUCCEEDED",
            )

    client.app.state.speech_to_text_provider = RecordingProvider()
    audio = wav_fixture()
    response = transcribe(client, conversation["id"], audio)
    assert response.status_code == 200
    assert response.json() == {
        "transcript": "I practise English every morning.",
        "detected_language": "en",
        "confidence": 0.98,
        "duration_ms": 250,
        "size_bytes": len(audio),
    }
    assert response.headers["server-timing"].startswith("stt;dur=")
    assert "I practise" not in response.headers["server-timing"]
    stage_timings = client.app.state.metrics.snapshot()["observations"]["stt_stage_duration_ms"]
    assert stage_timings[-1] >= 0
    assert received == {
        "audio": audio, "type": "audio/wav", "duration": 0.25,
        "filename": "speech.wav", "language": "te",
    }
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        assert attempt.status == "COMPLETED"
        assert attempt.charge_duration_ms == 250
        assert attempt.audio_digest


def test_provider_duration_overrides_forged_browser_duration(client, conversation):
    class DurationProvider:
        def transcribe(self, request):
            return SpeechToTextResult(
                transcript="I practised for two minutes.",
                detected_language="en",
                confidence=0.97,
                provider_job_id="duration-provider",
                duration_seconds=2.5,
                usage_units=2.5,
                processing_status="SUCCEEDED",
            )

    client.app.state.speech_to_text_provider = DurationProvider()
    response = transcribe(
        client,
        conversation["id"],
        **{"X-Audio-Duration-Ms": "100", "Idempotency-Key": "forged-duration-capture"},
    )
    assert response.status_code == 200
    assert response.json()["duration_ms"] == 2500
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        usage = session.scalar(select(AIUsageRecord).where(AIUsageRecord.provider_kind == "stt"))
        assert attempt.charge_duration_ms == 2500
        assert usage.input_units == 2500


def test_completed_transcription_replays_without_provider_or_quota_work(client, conversation):
    key = "voice-completed-replay"
    first = transcribe(client, conversation["id"], **{"Idempotency-Key": key})
    assert first.status_code == 200
    calls = client.app.state.speech_to_text_provider.calls
    client.app.state.commercial_service.config = replace(
        client.app.state.commercial_service.config,
        free_daily_voice_minutes=1,
    )
    with client.app.state.session_factory() as session:
        session.add(VoiceTranscriptionAttempt(
            conversation_id=conversation["id"],
            learner_id=session.scalar(select(VoiceTranscriptionAttempt.learner_id)),
            idempotency_key="exhaust-remaining-voice",
            audio_digest="e" * 64,
            content_type="audio/wav",
            status="FAILED_RETRYABLE",
            charge_duration_ms=59_750,
            provider_requests=1,
        ))
        session.commit()
    replay = transcribe(client, conversation["id"], **{"Idempotency-Key": key})
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert client.app.state.speech_to_text_provider.calls == calls
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(VoiceTranscriptionAttempt)) == 2
        assert session.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.provider_kind == "stt"
        )) == 1


def test_transcription_idempotency_rejects_different_audio(client, conversation):
    key = "voice-audio-conflict"
    assert transcribe(client, conversation["id"], **{"Idempotency-Key": key}).status_code == 200
    conflict = transcribe(
        client,
        conversation["id"],
        audio=wav_fixture(300),
        **{"Idempotency-Key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "speech_to_text_idempotency_conflict"


def test_failed_stt_call_consumes_conservative_voice_reservation(client, conversation):
    class FailedProvider:
        calls = 0

        def transcribe(self, _request):
            self.calls += 1
            raise ProviderUnavailable("private provider detail")

    provider = FailedProvider()
    client.app.state.speech_to_text_provider = provider
    client.app.state.commercial_service.config = replace(
        client.app.state.commercial_service.config,
        free_daily_voice_minutes=1,
    )
    failed = transcribe(
        client,
        conversation["id"],
        **{"Idempotency-Key": "failed-reserved-capture"},
    )
    limited = transcribe(
        client,
        conversation["id"],
        **{"Idempotency-Key": "second-reserved-capture"},
    )
    assert failed.status_code == 503
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "daily_voice_limit_reached"
    assert provider.calls == 1
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        assert attempt.status == "FAILED_RETRYABLE"
        assert attempt.charge_duration_ms == 60_000


@pytest.mark.parametrize("unsafe", ["...", "\u0301\u0301", "   "])
def test_unusable_voice_transcript_is_rejected(client, conversation, unsafe):
    class UnsafeSTT:
        def transcribe(self, request):
            return SpeechToTextResult(
                transcript=unsafe, detected_language="te", confidence=0.1,
                provider_job_id="unsafe", duration_seconds=request.duration_seconds,
                usage_units=request.duration_seconds, processing_status="SUCCEEDED",
            )

    client.app.state.speech_to_text_provider = UnsafeSTT()
    response = transcribe(client, conversation["id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_speech_detected"


def test_malformed_telugu_graphemes_are_rejected():
    with pytest.raises(UnusableTranscript):
        safe_transcript("ో ం ి ీ ి ం ి ్ ై ్ ం")


@pytest.mark.parametrize("malformed", ["కిీ", "క్ి", "కౢౣ", "క్ౣ"])
def test_invalid_telugu_vowel_and_virama_sequences_are_rejected(malformed):
    with pytest.raises(UnusableTranscript):
        safe_transcript(malformed, expected_language="te")


def test_valid_complex_telugu_graphemes_are_accepted():
    transcript = "క్షేత్రంలో ప్రశ్న అడగండి"
    assert safe_transcript(transcript, expected_language="te") == transcript


def test_kannada_dominant_transcript_is_rejected_when_telugu_expected():
    with pytest.raises(UnusableTranscript):
        safe_transcript("ದೀನಿ ದರ ಎಂಥ?", expected_language="te")


@pytest.mark.parametrize(
    "unsupported",
    [
        "ದೀನಿ ದರ ಎಂಥ?",
        "هذا نص عربي",
        "Это русский текст",
        "यह हिन्दी पाठ है",
    ],
)
def test_substantive_unsupported_scripts_are_rejected_in_every_input_mode(unsupported):
    for expected_language in (None, "en", "te"):
        with pytest.raises(UnusableTranscript):
            safe_transcript(unsupported, expected_language=expected_language)


def test_supported_latin_telugu_common_and_inherited_input_is_nfc_normalized():
    transcript = "Cafe\u0301 లో price ₹50 — okay?"
    assert safe_transcript(transcript, expected_language="en") == "Café లో price ₹50 — okay?"


@pytest.mark.parametrize(
    "malformed",
    [
        "a\u1037",  # Myanmar sign misclassified as Inherited by a name-only policy
        "a\u0f71",  # Tibetan vowel sign
        "a\u17b6",  # Khmer vowel sign
        "Wait.\u0301",  # inherited mark after punctuation, not a lexical base
    ],
)
def test_unsupported_or_detached_combining_marks_are_rejected(malformed):
    with pytest.raises(UnusableTranscript):
        safe_transcript(malformed)


def test_supported_inherited_mark_must_attach_to_a_latin_or_telugu_base():
    valid = "q\u0301 తెలుగు"
    assert safe_transcript(valid) == valid


def test_valid_telugu_english_mix_is_accepted():
    transcript = "దీని ధర ఎంత? How much is this?"
    assert safe_transcript(transcript, expected_language="te") == transcript


@pytest.mark.parametrize(("transcript", "detected", "expected_status"), [
    ("ದೀನಿ ದರ ಎಂಥ?", "kn", 422),
    ("దీని ధర ఎంత? How much is this?", "te", 200),
    ("How much is this?", "en", 200),
])
def test_transcription_boundary_enforces_script_without_rejecting_valid_mix(
    client, conversation, transcript, detected, expected_status,
):
    class ScriptedSTT:
        def transcribe(self, request):
            return SpeechToTextResult(
                transcript=transcript, detected_language=detected, confidence=0.95,
                provider_job_id="scripted", duration_seconds=request.duration_seconds,
                usage_units=request.duration_seconds, processing_status="SUCCEEDED",
            )

    client.app.state.speech_to_text_provider = ScriptedSTT()
    before = client.app.state.metrics.snapshot()["counters"].get("voice_transcriptions_completed", 0)
    response = transcribe(client, conversation["id"])
    assert response.status_code == expected_status
    after = client.app.state.metrics.snapshot()["counters"].get("voice_transcriptions_completed", 0)
    assert after == before + (1 if expected_status == 200 else 0)
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        assert attempt.status == ("COMPLETED" if expected_status == 200 else "REJECTED_FINAL")
        if expected_status != 200:
            assert session.scalar(select(func.count()).select_from(AIUsageRecord)) == 0


def test_low_confidence_transcription_is_rejected_before_frontend_submission(client, conversation):
    class LowConfidenceSTT:
        def transcribe(self, request):
            return SpeechToTextResult(
                transcript="దీని ధర ఎంత?", detected_language="te", confidence=0.1,
                provider_job_id="low-confidence", duration_seconds=request.duration_seconds,
                usage_units=request.duration_seconds, processing_status="SUCCEEDED",
            )

    client.app.state.speech_to_text_provider = LowConfidenceSTT()
    response = transcribe(client, conversation["id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_speech_detected"


@pytest.mark.parametrize(
    ("message", "detected_language"),
    [
        ("ದೀನಿ ದರ ಎಂಥ?", "kn"),
        ("هذا نص عربي", "ar"),
        ("Это русский текст", "ru"),
    ],
)
def test_unsupported_script_is_not_persisted_as_voice_ai_turn(
    client, conversation, message, detected_language,
):
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    response = client.post(
        route,
        json={
            "message": message,
            "input_source": "VOICE",
            "detected_language": detected_language,
        },
        headers={"Idempotency-Key": f"unsupported-{detected_language}-turn"},
    )
    assert response.status_code == 422
    with client.app.state.session_factory() as db:
        from backend.app.models import AICostMetricEvent, AITurnAttempt, AIUsageRecord, ConversationMessage
        from sqlalchemy import func, select

        assert db.scalar(select(func.count()).select_from(AITurnAttempt).where(
            AITurnAttempt.turn_kind == "LEARNER"
        )) == 0
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 0
        assert db.scalar(select(func.count()).select_from(AIUsageRecord)) == 0


def test_unsupported_typed_ai_turn_uses_message_specific_copy(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": "Это русский текст", "input_source": "TEXT"},
        headers={"Idempotency-Key": "unsupported-typed-turn"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_learner_message"
    assert response.json()["error"]["message"] == (
        "This message contains unsupported or malformed text. Please edit it and try again."
    )


def test_voice_input_rejects_empty_unsupported_and_invalid_duration(client, conversation):
    empty = transcribe(client, conversation["id"], b"")
    unsupported = transcribe(client, conversation["id"], b"audio", **{"Content-Type": "text/plain"})
    invalid_duration = transcribe(client, conversation["id"], **{"X-Audio-Duration-Ms": "60001"})
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "empty_audio"
    assert unsupported.status_code == 415 and unsupported.json()["error"]["code"] == "unsupported_audio_type"
    assert invalid_duration.status_code == 422 and invalid_duration.json()["error"]["code"] == "invalid_audio_duration"


def test_voice_input_requires_explicit_turn_consent(client, conversation):
    response = transcribe(client, conversation["id"], **{"X-Voice-Processing-Consent": ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "voice_consent_required"


def test_disabled_or_failed_stt_is_customer_safe(client, conversation):
    client.app.state.speech_to_text_provider = None
    disabled = transcribe(client, conversation["id"])

    class FailedProvider:
        def transcribe(self, _):
            raise ProviderUnavailable("raw provider detail")

    client.app.state.speech_to_text_provider = FailedProvider()
    failed = transcribe(client, conversation["id"])
    assert disabled.status_code == 503 and disabled.json()["error"]["code"] == "speech_to_text_unavailable"
    assert failed.status_code == 503 and failed.json()["error"]["message"] == "Speech recognition is unavailable."
    assert "raw provider detail" not in failed.text


def test_voice_input_enforces_conversation_ownership(client, learner, conversation):
    second = client.post("/api/v1/auth/register", json={
        "email": "voice-second@example.com", "password": "StrongPassword123!",
        "display_name": "Second", "terms_privacy_accepted": True,
    }).json()
    client.headers["Authorization"] = f"Bearer {second['tokens']['access_token']}"
    response = transcribe(client, conversation["id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_openai_stt_boundary_builds_audio_multipart_without_logging_secret():
    captured = {}

    def opener(outgoing, timeout):
        captured["request"] = outgoing
        captured["timeout"] = timeout
        return Response({"text": "Hello from speech.", "language": "en", "duration": 0.25})

    audio = wav_fixture()
    provider = OpenAICompatibleSTTProvider(OpenAITranscriptionHTTPClient("secret-key", opener), model="configured-stt")
    result = provider.transcribe(SpeechToTextRequest(
        audio_asset_reference="ephemeral/test.wav", audio_bytes=audio, filename="speech.wav",
        content_type="audio/wav", learner_id="learner", voice_session_id="conversation",
        voice_turn_id="request", correlation_id="correlation", duration_seconds=0.25, size_bytes=len(audio),
    ))
    outgoing = captured["request"]
    assert result.transcript == "Hello from speech."
    assert outgoing.full_url == "https://api.openai.com/v1/audio/transcriptions"
    assert outgoing.get_header("Authorization") == "Bearer secret-key"
    assert b'name="model"' in outgoing.data and b"configured-stt" in outgoing.data
    assert b'name="file"; filename="speech.wav"' in outgoing.data
    assert audio in outgoing.data


def test_openai_stt_boundary_reports_every_internal_request():
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return Response({"text": "Recovered speech.", "language": "en", "duration": 0.25})

    audio = wav_fixture()
    provider = OpenAICompatibleSTTProvider(
        OpenAITranscriptionHTTPClient("secret-key", opener),
        model="configured-stt",
        max_retries=2,
    )
    result = provider.transcribe(SpeechToTextRequest(
        audio_asset_reference="ephemeral/test.wav",
        audio_bytes=audio,
        filename="speech.wav",
        content_type="audio/wav",
        learner_id="learner",
        voice_session_id="conversation",
        voice_turn_id="request",
        correlation_id="correlation",
        duration_seconds=0.25,
        size_bytes=len(audio),
    ))
    assert calls == 2
    assert result.provider_requests == 2


def test_openai_stt_rejection_and_timeout_preserve_internal_request_count():
    rejection_calls = 0

    def empty_after_timeout(*_args, **_kwargs):
        nonlocal rejection_calls
        rejection_calls += 1
        if rejection_calls == 1:
            raise TimeoutError
        return Response({"text": "", "language": "en", "duration": 0.25})

    request = SpeechToTextRequest(
        audio_asset_reference="ephemeral/test.wav",
        audio_bytes=wav_fixture(),
        filename="speech.wav",
        content_type="audio/wav",
        learner_id="learner",
        voice_session_id="conversation",
        voice_turn_id="request",
        correlation_id="correlation",
        duration_seconds=0.25,
        size_bytes=len(wav_fixture()),
    )
    rejected_provider = OpenAICompatibleSTTProvider(
        OpenAITranscriptionHTTPClient("secret-key", empty_after_timeout),
        model="configured-stt",
        max_retries=2,
    )
    with pytest.raises(ValueError) as rejected:
        rejected_provider.transcribe(request)
    assert rejected.value.provider_requests == 2

    timeout_provider = OpenAICompatibleSTTProvider(
        OpenAITranscriptionHTTPClient(
            "secret-key",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
        ),
        model="configured-stt",
        max_retries=2,
    )
    with pytest.raises(ProviderTimeout) as timed_out:
        timeout_provider.transcribe(request)
    assert timed_out.value.provider_requests == 3

    malformed_calls = 0

    def malformed_after_timeout(*_args, **_kwargs):
        nonlocal malformed_calls
        malformed_calls += 1
        if malformed_calls == 1:
            raise TimeoutError
        return Response([])

    malformed_provider = OpenAICompatibleSTTProvider(
        OpenAITranscriptionHTTPClient("secret-key", malformed_after_timeout),
        model="configured-stt",
        max_retries=2,
    )
    with pytest.raises(ProviderUnavailable) as malformed:
        malformed_provider.transcribe(request)
    assert malformed.value.provider_requests == 2


def test_stt_rejection_meters_provider_retries(client, conversation):
    class RetriedNoSpeech(ValueError):
        provider_requests = 2

    class RejectedProvider:
        def transcribe(self, _request):
            raise RetriedNoSpeech("provider detail")

    client.app.state.speech_to_text_provider = RejectedProvider()
    response = transcribe(
        client,
        conversation["id"],
        **{"Idempotency-Key": "stt-rejected-after-retry"},
    )
    assert response.status_code == 422
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        event = session.scalar(select(ProviderCallEvent).where(
            ProviderCallEvent.operation_kind == "stt"
        ))
        assert attempt.status == "REJECTED_FINAL"
        assert attempt.provider_requests == 2
        assert event.request_count == 2
        assert event.outcome == "REJECTED"


def test_stale_pre_event_stt_attempt_recovers_and_old_lease_is_fenced(client, learner, conversation):
    audio = wav_fixture()
    key = "stale-pre-event-stt"
    with client.app.state.session_factory() as session:
        learner_row = session.get(Learner, learner["id"])
        attempt = VoiceTranscriptionAttempt(
            conversation_id=conversation["id"],
            learner_id=learner["id"],
            idempotency_key=key,
            audio_digest=sha256(audio).hexdigest(),
            content_type="audio/wav",
            status="IN_PROGRESS",
            charge_duration_ms=60_000,
            provider_requests=1,
            result_json={},
            updated_at=datetime.now(UTC) - timedelta(minutes=6),
        )
        session.add(attempt)
        session.commit()
        user_id = learner_row.user_account_id

    response = transcribe(
        client,
        conversation["id"],
        audio=audio,
        **{"Idempotency-Key": key},
    )
    assert response.status_code == 200
    with client.app.state.session_factory() as session:
        attempt = session.scalar(select(VoiceTranscriptionAttempt))
        event = session.scalar(select(ProviderCallEvent).where(
            ProviderCallEvent.operation_kind == "stt"
        ))
        assert attempt.status == "COMPLETED"
        assert attempt.provider_requests == 2
        assert event.outcome == "SUCCESS"
        event.outcome = "FAILURE"
        event.failed = True
        session.commit()
        with pytest.raises(ProviderCallLeaseLost):
            UsageService(session).reconcile_provider_call(event.id, request_count=1)
        assert event.user_id == user_id


def test_openai_stt_missing_duration_fails_closed_to_capture_maximum():
    provider = OpenAICompatibleSTTProvider(
        OpenAITranscriptionHTTPClient(
            "secret-key",
            lambda *_args, **_kwargs: Response({"text": "Hello.", "language": "en"}),
        ),
        model="configured-stt",
    )
    result = provider.transcribe(SpeechToTextRequest(
        audio_asset_reference="ephemeral/test.wav",
        audio_bytes=wav_fixture(),
        filename="speech.wav",
        content_type="audio/wav",
        learner_id="learner",
        voice_session_id="conversation",
        voice_turn_id="request",
        correlation_id="correlation",
        maximum_duration_seconds=60,
        duration_seconds=0.1,
        size_bytes=len(wav_fixture()),
    ))
    assert result.duration_seconds == 60
    assert result.usage_units == 60


def test_production_requires_openai_stt_policy():
    base = dict(
        environment="production", database_url="postgresql://db/app", auto_create_tables=False,
        jwt_secret="x" * 48, force_https=True, secure_cookies=True,
        cors_origins="https://app.example.com", trusted_hosts="app.example.com",
        public_frontend_url="https://app.example.com",
        object_storage_backend="s3", object_storage_bucket="private",
        redis_required=True, redis_url="rediss://redis:6379/0", worker_enabled=True,
        password_reset_delivery_provider="smtp", smtp_host="smtp.test.speakmate.in",
        password_reset_email_from="no-reply@test.speakmate.in",
        smtp_username="smtp-user", smtp_password="smtp-password-for-config-test", _env_file=None,
    )
    with pytest.raises(ValueError, match="speech_to_text_provider"):
        Settings(**base, speech_to_text_provider="disabled")
    configured = Settings(
        **base,
            llm_provider="openai",
            language_review_provider="openai",
            speech_to_text_provider="openai",
        text_to_speech_provider="openai",
        openai_api_key="test-key",
    )
    assert configured.speech_to_text_provider == "openai"
