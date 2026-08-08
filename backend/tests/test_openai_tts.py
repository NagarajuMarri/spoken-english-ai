import json
import logging

import pytest
from sqlalchemy import select

from backend.app.ai.exceptions import ProviderMalformedResponse, ProviderTimeout
from backend.app.core.config import Settings
from backend.app.models import TTSSynthesisAttempt
from backend.app.providers.tts.contracts import TextToSpeechRequest
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.providers.tts.openai_boundary import OpenAICompatibleTTSProvider, OpenAISpeechHTTPClient
from backend.app.providers.tts.factory import build_text_to_speech_provider


def create_turn(client, conversation, key="feature-5-turn-1", message="Please help me practise English."):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": message},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200
    assert response.json()["turn_id"]
    return response.json()


class Headers:
    def get_content_type(self):
        return "audio/mpeg"


class BinaryResponse:
    headers = Headers()

    def __init__(self, audio=b"ID3" + b"\x00" * 128):
        self.audio = audio

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.audio


def request_for(voice="marin"):
    return TextToSpeechRequest(
        text="You are improving. What did you do today?",
        language="en-IN",
        voice_reference=voice,
        speaking_rate=1,
        instructions="Speak warmly with an Indian English accent.",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )


def test_openai_tts_builds_exact_speech_payload_and_returns_valid_mp3():
    captured = {}

    def opener(outgoing, timeout):
        captured["request"] = outgoing
        captured["timeout"] = timeout
        return BinaryResponse()

    provider = OpenAICompatibleTTSProvider(
        OpenAISpeechHTTPClient("secret-key", opener),
        model="gpt-4o-mini-tts",
        timeout_seconds=27,
        max_retries=0,
        response_format="mp3",
    )
    result = provider.synthesize(request_for())
    outgoing = captured["request"]
    payload = json.loads(outgoing.data)
    assert outgoing.full_url == "https://api.openai.com/v1/audio/speech"
    assert outgoing.get_header("Authorization") == "Bearer secret-key"
    assert captured["timeout"] == 27
    assert payload == {
        "model": "gpt-4o-mini-tts",
        "input": "You are improving. What did you do today?",
        "voice": "marin",
        "instructions": "Speak warmly with an Indian English accent.",
        "response_format": "mp3",
        "speed": 1.0,
    }
    assert result.audio_bytes.startswith(b"ID3")
    assert result.content_type == "audio/mpeg"
    assert result.model_reference == "gpt-4o-mini-tts"
    assert result.voice_reference == "marin"
    assert result.provider_requests == 1


def test_openai_tts_rejects_empty_or_non_audio_provider_response():
    provider = OpenAICompatibleTTSProvider(
        OpenAISpeechHTTPClient("secret-key", lambda *_args, **_kwargs: BinaryResponse(b"not audio")),
        model="gpt-4o-mini-tts",
    )
    try:
        provider.synthesize(request_for())
    except ProviderMalformedResponse as exc:
        assert exc.failure_code == "provider_malformed_response"
    else:
        raise AssertionError("invalid audio must be rejected")


def test_production_requires_openai_tts_and_factory_wires_the_locked_provider():
    base = dict(
        environment="production", database_url="postgresql://db/app", auto_create_tables=False,
        jwt_secret="x" * 48, force_https=True, secure_cookies=True,
        cors_origins="https://app.example.com", trusted_hosts="app.example.com",
        object_storage_backend="s3", object_storage_bucket="private",
        password_reset_delivery_provider="smtp", smtp_host="smtp.example.com",
        llm_provider="openai", speech_to_text_provider="openai", openai_api_key="test-key", _env_file=None,
    )
    with pytest.raises(ValueError, match="text_to_speech_provider"):
        Settings(**base, text_to_speech_provider="disabled")
    configured = Settings(**base, text_to_speech_provider="openai")
    provider = build_text_to_speech_provider(configured)
    assert isinstance(provider, OpenAICompatibleTTSProvider)
    assert provider.model == "gpt-4o-mini-tts"
    assert provider.max_retries == 0


def test_tts_route_returns_audio_once_then_replays_cached_bytes(client, conversation):
    turn = create_turn(client, conversation)
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns/{turn['turn_id']}/speech"
    first = client.post(route)
    second = client.post(route)
    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"].startswith("audio/wav")
    assert first.content.startswith(b"RIFF") and first.content == second.content
    assert first.headers["x-tts-provider"] == "test-only-fake"
    assert first.headers["x-tts-model"] == "deterministic-tts"
    assert first.headers["x-tts-voice"] == "marin"
    assert first.headers["x-tts-cache"] == "MISS"
    assert second.headers["x-tts-cache"] == "HIT"
    assert first.headers["x-tts-provider-requests"] == second.headers["x-tts-provider-requests"] == "1"
    assert client.app.state.text_to_speech_provider.calls == 1
    with client.app.state.session_factory() as session:
        attempts = list(session.scalars(select(TTSSynthesisAttempt)))
        assert len(attempts) == 1
        assert attempts[0].status == "SUCCEEDED"
        assert attempts[0].audio_size_bytes == len(first.content)
        assert attempts[0].input_characters > 0
        assert attempts[0].usage_classification == "CHARACTERS_AND_BYTES_PROVIDER_TOKEN_USAGE_UNAVAILABLE"


def test_second_consecutive_tutor_response_gets_one_distinct_audio_generation(client, conversation):
    first = create_turn(client, conversation, "feature-5-consecutive-1", "I studied Python today.")
    second = create_turn(client, conversation, "feature-5-consecutive-2", "Then I practised English.")
    first_route = f"/api/v1/conversations/{conversation['id']}/ai-turns/{first['turn_id']}/speech"
    second_route = f"/api/v1/conversations/{conversation['id']}/ai-turns/{second['turn_id']}/speech"
    assert client.post(first_route).status_code == 200
    assert client.post(second_route).status_code == 200
    assert client.post(first_route).headers["x-tts-cache"] == "HIT"
    assert client.post(second_route).headers["x-tts-cache"] == "HIT"
    assert client.app.state.text_to_speech_provider.calls == 2
    with client.app.state.session_factory() as session:
        assert len(list(session.scalars(select(TTSSynthesisAttempt)))) == 2


def test_ananya_and_arjun_map_to_distinct_configured_voices(client, learner):
    ananya_conversation = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "daily-conversation"},
    ).json()
    ananya = create_turn(client, ananya_conversation, "ananya-feature-5")
    ananya_audio = client.post(
        f"/api/v1/conversations/{ananya_conversation['id']}/ai-turns/{ananya['turn_id']}/speech"
    )
    assert ananya_audio.headers["x-tts-voice"] == "marin"

    changed = client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "arjun", "telugu_explanations_enabled": False},
    )
    assert changed.status_code == 200
    arjun_conversation = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "daily-conversation"},
    ).json()
    arjun = create_turn(client, arjun_conversation, "arjun-feature-5")
    arjun_audio = client.post(
        f"/api/v1/conversations/{arjun_conversation['id']}/ai-turns/{arjun['turn_id']}/speech"
    )
    assert arjun_audio.headers["x-tts-voice"] == "cedar"


def test_tts_timeout_is_visible_and_manual_recovery_is_safe(client, conversation):
    class TimeoutProvider:
        calls = 0

        def synthesize(self, _request):
            self.calls += 1
            raise ProviderTimeout("private provider detail")

    timeout = TimeoutProvider()
    client.app.state.text_to_speech_provider = timeout
    turn = create_turn(client, conversation, "tts-timeout-turn")
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns/{turn['turn_id']}/speech"
    failed = client.post(route)
    assert failed.status_code == 504
    assert failed.json()["error"] == {
        "code": "tts_timeout",
        "message": "Tutor voice timed out. Try audio again.",
        "request_id": failed.json()["error"]["request_id"],
        "retryable": True,
    }
    assert "private provider detail" not in failed.text
    assert timeout.calls == 1

    recovered_provider = DeterministicTextToSpeechProvider()
    client.app.state.text_to_speech_provider = recovered_provider
    recovered = client.post(route)
    replay = client.post(route)
    assert recovered.status_code == replay.status_code == 200
    assert recovered_provider.calls == 1
    assert replay.headers["x-tts-cache"] == "HIT"


def test_tts_logs_shape_only_and_never_speech_or_credentials(client, conversation, caplog):
    secret_text = "never-log-this-learner-phrase"
    turn = create_turn(client, conversation, "tts-private-log", secret_text)
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns/{turn['turn_id']}/speech"
    with caplog.at_level(logging.INFO):
        response = client.post(route)
    assert response.status_code == 200
    logs = caplog.text
    assert secret_text not in logs
    assert "secret-key" not in logs
    assert "tts_generation_completed" in logs
