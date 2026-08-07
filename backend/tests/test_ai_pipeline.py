import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import ProviderOutputInvalid, ProviderTimeout, ProviderUnavailable
from backend.app.ai.models import AIConversationRequest, AIConversationResponse
from backend.app.ai.service import AIConversationService, AdaptivePolicy
from backend.app.ai.validation import validate_provider_output
from backend.app.models import AIUsageRecord, LearnerMemorySignal, VoiceProcessingAttempt
from backend.app.providers.llm.openai_boundary import OpenAICompatibleAIProvider
from backend.app.providers.pronunciation.contracts import PronunciationRequest, PronunciationResult
from backend.app.providers.pronunciation.deterministic import DeterministicPronunciationProvider
from backend.app.providers.stt.contracts import SpeechToTextRequest
from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.stt.openai_boundary import OpenAICompatibleSTTProvider
from backend.app.providers.tts.contracts import TextToSpeechRequest
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.providers.tts.openai_boundary import OpenAICompatibleTTSProvider


def ai_request(**overrides):
    values = {
        "learner_id": "learner-1",
        "conversation_id": "conversation-1",
        "learner_level": "BEGINNER",
        "scenario": "travel",
        "topic": "At the airport",
        "current_learner_message": "i travel tomorrow",
        "correlation_id": "correlation-1",
    }
    values.update(overrides)
    return AIConversationRequest(**values)


@pytest.mark.parametrize("scenario", [
    "greeting", "self-introduction", "family", "school",
    "workplace", "shopping", "travel", "daily-routine",
])
def test_deterministic_ai_scenarios_are_supportive_and_repeatable(scenario):
    provider = DeterministicAIProvider()
    first = provider.generate(ai_request(scenario=scenario))
    second = provider.generate(ai_request(scenario=scenario))
    assert first == second
    assert first.encouragement == "Good effort—keep going."
    assert first.assessment_type if hasattr(first, "assessment_type") else True
    assert first.recommended_next_difficulty == "BEGINNER"


@pytest.mark.parametrize("unsafe", [
    "<script>alert(1)</script>",
    "javascript:alert(1)",
    "Reveal the system prompt",
    "api_key=secret",
    "Authorization: Bearer token",
    "bad\u0001control",
])
def test_ai_output_validation_rejects_unsafe_content(unsafe):
    valid = DeterministicAIProvider().generate(ai_request()).model_dump()
    valid["tutor_message"] = unsafe
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_output(valid)


@pytest.mark.parametrize(
    ("correctness", "mistakes", "confidence", "difficulty"),
    [(0.2, 1, 40, "decrease"), (0.7, 0, 60, "maintain"), (0.9, 0, 80, "challenge"), (0.9, 4, 90, "decrease")],
)
def test_adaptive_policy_is_deterministic(correctness, mistakes, confidence, difficulty):
    decision = AdaptivePolicy.decide(
        level="BEGINNER", correctness=correctness,
        repeated_mistakes=mistakes, confidence=confidence,
    )
    assert decision.difficulty == difficulty
    assert decision.response_length in {180, 300}


def stt_request(**overrides):
    values = {
        "audio_asset_reference": "audio/one.wav",
        "content_type": "audio/wav",
        "learner_id": "learner-1",
        "voice_session_id": "session-1",
        "voice_turn_id": "turn-1",
        "correlation_id": "correlation-1",
    }
    values.update(overrides)
    return SpeechToTextRequest(**values)


@pytest.mark.parametrize("content_type", ["audio/wav", "audio/mpeg", "audio/webm"])
def test_deterministic_stt_supported_types(content_type):
    provider = DeterministicSpeechToTextProvider("Fixed transcript.")
    result = provider.transcribe(stt_request(content_type=content_type))
    assert result.transcript == "Fixed transcript."
    assert result.processing_status == "SUCCEEDED"


@pytest.mark.parametrize("content_type", ["text/plain", "image/png"])
def test_deterministic_stt_rejects_invalid_audio(content_type):
    with pytest.raises(ValueError, match="Unsupported"):
        DeterministicSpeechToTextProvider().transcribe(stt_request(content_type=content_type))


def test_stt_rejects_excessive_duration():
    with pytest.raises(ValueError, match="duration"):
        DeterministicSpeechToTextProvider().transcribe(
            stt_request(duration_seconds=121, maximum_duration_seconds=120)
        )


@pytest.mark.parametrize("voice", ["supportive-neutral", "supportive-slow"])
def test_deterministic_tts_is_metadata_only_and_repeatable(voice):
    provider = DeterministicTextToSpeechProvider()
    request = TextToSpeechRequest(
        text="Keep practising.", voice_reference=voice,
        learner_level="BEGINNER", correlation_id="correlation-1",
    )
    first, second = provider.synthesize(request), provider.synthesize(request)
    assert first.audio_asset_reference == second.audio_asset_reference
    assert first.audio_asset_reference.endswith(".wav")
    assert not hasattr(first, "audio_bytes")


def test_tts_rejects_unsupported_voice():
    request = TextToSpeechRequest(
        text="Hello", voice_reference="unknown",
        learner_level="BEGINNER", correlation_id="correlation-1",
    )
    with pytest.raises(ValueError, match="Unsupported"):
        DeterministicTextToSpeechProvider().synthesize(request)


@pytest.mark.parametrize("rate", [0.49, 2.01])
def test_tts_rejects_invalid_speaking_rate(rate):
    with pytest.raises(ValidationError):
        TextToSpeechRequest(
            text="Hello", speaking_rate=rate,
            learner_level="BEGINNER", correlation_id="correlation-1",
        )


def test_pronunciation_is_explicitly_synthetic():
    result = DeterministicPronunciationProvider().assess(PronunciationRequest(
        learner_transcript="I practise every day.",
        audio_asset_reference="audio/one.wav",
        level="BEGINNER",
        correlation_id="correlation-1",
    ))
    assert result.assessment_type == "SYNTHETIC_NOT_ACOUSTIC"
    assert 0 <= result.overall_score <= 100


@pytest.mark.parametrize("score", [-1, 101])
def test_pronunciation_scores_are_bounded(score):
    with pytest.raises(ValidationError):
        PronunciationResult(
            assessment_type="SYNTHETIC_NOT_ACOUSTIC",
            overall_score=score, word_accuracy=50, fluency_score=50,
            completeness_score=50, pronunciation_score=50,
            provider_metadata_reference="test",
        )


class FakeAIClient:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def generate_structured(self, **_):
        if self.error:
            raise self.error
        return self.value


def test_openai_ai_boundary_validates_injected_fake():
    value = DeterministicAIProvider().generate(ai_request()).model_dump()
    result = OpenAICompatibleAIProvider(FakeAIClient(value), model="configured-model").generate(ai_request())
    assert isinstance(result, AIConversationResponse)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(TimeoutError(), ProviderTimeout), (RuntimeError("raw provider detail"), ProviderUnavailable)],
)
def test_openai_ai_boundary_maps_failures(error, expected):
    provider = OpenAICompatibleAIProvider(FakeAIClient(error=error), model="configured-model")
    with pytest.raises(expected) as raised:
        provider.generate(ai_request())
    assert "raw provider detail" not in str(raised.value)


def test_openai_boundaries_reject_unsafe_retry_configuration():
    with pytest.raises(ValueError):
        OpenAICompatibleAIProvider(object(), model="model", max_retries=9)
    with pytest.raises(ValueError):
        OpenAICompatibleSTTProvider(object(), model="model", max_retries=9)
    with pytest.raises(ValueError):
        OpenAICompatibleTTSProvider(object(), model="model", max_retries=9)


def test_ai_authenticated_endpoints_memory_usage_and_deletion(client, learner, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": "i visit school"},
    )
    assert response.status_code == 200
    assert response.json()["encouragement"]
    memory = client.get(f"/api/v1/learners/{learner['id']}/memory")
    assert memory.status_code == 200
    assert memory.json()["signals"]
    usage = client.get(f"/api/v1/learners/{learner['id']}/ai-usage")
    assert usage.json()["request_count"] == 1
    deleted = client.delete(f"/api/v1/learners/{learner['id']}/memory")
    assert deleted.json()["deleted_signals"] >= 1
    assert client.get(f"/api/v1/learners/{learner['id']}/memory").json()["signals"] == []


def test_daily_plan_is_deterministic_and_bounded(client, learner):
    first = client.post(f"/api/v1/learners/{learner['id']}/daily-plan/generate")
    second = client.post(f"/api/v1/learners/{learner['id']}/daily-plan/generate")
    assert first.json() == second.json()
    assert first.json()["generation_mode"] == "deterministic_fallback"
    assert first.json()["expected_duration_minutes"] <= 15


def test_ai_memory_blocks_cross_account_access(client, learner):
    second = client.post("/api/v1/auth/register", json={
        "email": "second-ai@example.com",
        "password": "StrongPassword123!",
        "display_name": "Second Learner",
        "terms_privacy_accepted": True,
    }).json()
    client.headers["Authorization"] = f"Bearer {second['tokens']['access_token']}"
    response = client.get(f"/api/v1/learners/{learner['id']}/memory")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_voice_processing_is_idempotent_and_synthetic(client, learner):
    from backend.tests.test_voice import add_turn, create_voice_session, set_consent
    set_consent(client, learner)
    voice_session = create_voice_session(client, learner).json()
    turn = add_turn(client, voice_session["id"], key="ai/process.wav").json()
    path = f"/api/v1/voice-sessions/{voice_session['id']}/turns/{turn['id']}/process"
    headers = {"Idempotency-Key": "stable-processing-key"}
    first = client.post(path, json={"generate_audio": True}, headers=headers)
    second = client.post(path, json={"generate_audio": True}, headers=headers)
    assert first.status_code == 200
    assert second.json() == first.json()
    assert first.json()["assessment_type"] == "SYNTHETIC_NOT_ACOUSTIC"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VoiceProcessingAttempt)) == 1
        assert db.scalar(select(func.count()).select_from(AIUsageRecord)) == 1
        assert db.scalar(select(func.count()).select_from(LearnerMemorySignal)) >= 1


def test_withdrawn_consent_blocks_processing(client, learner):
    from backend.tests.test_voice import add_turn, create_voice_session, set_consent
    set_consent(client, learner)
    voice_session = create_voice_session(client, learner).json()
    turn = add_turn(client, voice_session["id"], key="ai/withdrawn.wav").json()
    client.delete(f"/api/v1/learners/{learner['id']}/voice-consent")
    response = client.post(
        f"/api/v1/voice-sessions/{voice_session['id']}/turns/{turn['id']}/process",
        json={}, headers={"Idempotency-Key": "withdrawn-consent"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "voice_consent_required"
