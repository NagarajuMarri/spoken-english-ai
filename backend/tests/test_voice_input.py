import io
import json
import wave

import pytest

from backend.app.ai.exceptions import ProviderUnavailable
from backend.app.core.config import Settings
from backend.app.providers.stt.contracts import SpeechToTextResult
from backend.app.providers.stt.openai_boundary import OpenAICompatibleSTTProvider, OpenAITranscriptionHTTPClient
from backend.app.transcript_safety import UnusableTranscript, safe_transcript


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
        "X-Voice-Processing-Consent": "accepted", **headers,
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
    assert received == {
        "audio": audio, "type": "audio/wav", "duration": 0.25,
        "filename": "speech.wav", "language": "te",
    }


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


@pytest.mark.parametrize("malformed", ["కిీ", "క్ి"])
def test_invalid_telugu_vowel_and_virama_sequences_are_rejected(malformed):
    with pytest.raises(UnusableTranscript):
        safe_transcript(malformed, expected_language="te")


def test_valid_complex_telugu_graphemes_are_accepted():
    transcript = "క్షేత్రంలో ప్రశ్న అడగండి"
    assert safe_transcript(transcript, expected_language="te") == transcript


def test_kannada_dominant_transcript_is_rejected_when_telugu_expected():
    with pytest.raises(UnusableTranscript):
        safe_transcript("ದೀನಿ ದರ ಎಂಥ?", expected_language="te")


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


def test_kannada_mismatch_is_not_persisted_as_voice_ai_turn(client, conversation):
    assert client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "ananya", "language_mode": "ENGLISH_TELUGU"},
    ).status_code == 200
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    response = client.post(
        route,
        json={"message": "ದೀನಿ ದರ ಎಂಥ?", "input_source": "VOICE", "detected_language": "kn"},
        headers={"Idempotency-Key": "kannada-mismatch-turn"},
    )
    assert response.status_code == 422
    with client.app.state.session_factory() as db:
        from backend.app.models import AICostMetricEvent, AITurnAttempt, AIUsageRecord, ConversationMessage
        from sqlalchemy import func, select

        assert db.scalar(select(func.count()).select_from(AITurnAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 0
        assert db.scalar(select(func.count()).select_from(AIUsageRecord)) == 0


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
    from backend.app.providers.stt.contracts import SpeechToTextRequest
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


def test_production_requires_openai_stt_policy():
    base = dict(
        environment="production", database_url="postgresql://db/app", auto_create_tables=False,
        jwt_secret="x" * 48, force_https=True, secure_cookies=True,
        cors_origins="https://app.example.com", trusted_hosts="app.example.com",
        object_storage_backend="s3", object_storage_bucket="private",
        password_reset_delivery_provider="smtp", smtp_host="smtp.example.com", _env_file=None,
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
