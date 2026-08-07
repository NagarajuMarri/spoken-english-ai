import json
from urllib import error

import pytest
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.ai.models import AIConversationRequest, ConversationHistoryTurn, UsageInfo
from backend.app.core.config import Settings
from backend.app.models import AICostMetricEvent, AIUsageRecord, ConversationMessage
from backend.app.providers.llm import build_llm_provider
from backend.app.providers.llm.openai_boundary import OpenAICompatibleAIProvider, OpenAIResponsesHTTPClient


def _request(**overrides):
    values = {
        "learner_id": "learner-1",
        "conversation_id": "conversation-1",
        "learner_level": "BEGINNER",
        "scenario": "daily-conversation",
        "topic": "Daily conversation",
        "current_learner_message": "What should I say next?",
        "correlation_id": "correlation-1",
    }
    values.update(overrides)
    return AIConversationRequest(**values)


def _content(message="That is a clear sentence."):
    value = DeterministicAIProvider().generate(_request()).model_dump()
    value.update({
        "tutor_message": message,
        "provider_metadata_reference": "openai:gpt-5-mini:resp_test",
        "usage": UsageInfo(
            input_units=100,
            cached_input_units=20,
            output_units=50,
            provider_requests=1,
        ).model_dump(),
    })
    return value


class _HTTPResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.value).encode()


def test_responses_client_sends_three_complete_turns_and_uses_provider_usage():
    captured = {}
    content = _content()
    content.pop("provider_metadata_reference")
    content.pop("usage")

    def opener(outgoing, timeout):
        captured["request"] = outgoing
        captured["timeout"] = timeout
        return _HTTPResponse({
            "id": "resp_live_test",
            "model": "gpt-5-mini-2025-08-07",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(content)}],
            }],
            "usage": {
                "input_tokens": 123,
                "input_tokens_details": {"cached_tokens": 23},
                "output_tokens": 45,
            },
        })

    history = [
        ConversationHistoryTurn(learner_message=f"learner-{number}", tutor_message=f"tutor-{number}")
        for number in range(1, 4)
    ]
    provider = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient("secret-key", opener),
        model="gpt-5-mini",
        timeout_seconds=7,
        max_retries=0,
    )
    result = provider.generate(_request(conversation_history=history))

    outgoing = captured["request"]
    body = json.loads(outgoing.data)
    assert captured["timeout"] == 7
    assert outgoing.full_url == "https://api.openai.com/v1/responses"
    assert outgoing.get_header("Authorization") == "Bearer secret-key"
    assert "secret-key" not in outgoing.data.decode()
    assert body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert [item["role"] for item in body["input"]] == [
        "user", "assistant", "user", "assistant", "user", "assistant", "user",
    ]
    assert body["input"][0]["content"] == "learner-1"
    assert body["input"][-1]["content"] == "What should I say next?"
    assert result.usage.input_units == 123
    assert result.usage.cached_input_units == 23
    assert result.usage.output_units == 45
    assert result.provider_metadata_reference.startswith("openai:gpt-5-mini-2025-08-07:resp_live_test")


def test_openai_provider_failure_does_not_log_key_or_learner_content(caplog):
    secret = "test-secret-that-must-not-appear"
    learner_content = "private learner sentence"

    def unavailable(*_args, **_kwargs):
        raise error.URLError("network unavailable")

    provider = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient(secret, unavailable),
        model="gpt-5-mini",
        max_retries=0,
    )
    with pytest.raises(ProviderUnavailable):
        provider.generate(_request(current_learner_message=learner_content))
    captured = caplog.text
    assert secret not in captured
    assert learner_content not in captured


class _RecordingProvider:
    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return _content(f"Contextual reply to: {request.current_learner_message}")


def test_ai_turn_uses_provider_for_greetings_carries_three_turns_and_persists_usage(
    client, learner, conversation,
):
    provider = _RecordingProvider()
    client.app.state.llm_provider = provider
    messages = [
        "Hello Ananya.",
        "My name is Anusha.",
        "I live in Hyderabad.",
        "What should I describe next?",
    ]
    for message in messages:
        response = client.post(
            f"/api/v1/conversations/{conversation['id']}/ai-turns",
            json={"message": message},
        )
        assert response.status_code == 200
        assert response.json()["tutor_message"] == f"Contextual reply to: {message}"

    assert provider.requests[0].conversation_history == []
    assert [turn.learner_message for turn in provider.requests[-1].conversation_history] == messages[:3]
    assert [turn.tutor_message for turn in provider.requests[-1].conversation_history] == [
        f"Contextual reply to: {message}" for message in messages[:3]
    ]
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 4
        cost_rows = list(db.scalars(select(AICostMetricEvent).order_by(AICostMetricEvent.occurred_at)))
        usage_rows = list(db.scalars(select(AIUsageRecord).order_by(AIUsageRecord.occurred_at)))
        assert len(cost_rows) == 4
        assert len(usage_rows) == 4
        assert all(row.model_used == "openai:gpt-5-mini:resp_test" for row in cost_rows)
        assert all(row.cost_classification == "ESTIMATE_FROM_PROVIDER_REPORTED_USAGE" for row in cost_rows)
        assert all(row.cached_tokens == 20 for row in cost_rows)
        assert cost_rows[0].estimated_cost_usd == pytest.approx(0.0001205)
        assert all(row.input_units == 100 and row.output_units == 50 for row in usage_rows)


@pytest.mark.parametrize(
    ("provider_error", "status_code", "error_code"),
    [
        (ProviderTimeout("raw timeout detail"), 504, "llm_timeout"),
        (ProviderUnavailable("raw provider detail"), 503, "llm_unavailable"),
    ],
)
def test_ai_turn_maps_provider_failures_without_persisting_a_message(
    client, learner, conversation, provider_error, status_code, error_code,
):
    class FailedProvider:
        def generate(self, _):
            raise provider_error

    client.app.state.llm_provider = FailedProvider()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": "Please help me practise."},
    )
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code
    assert "raw" not in response.text
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        usage = db.scalar(select(AIUsageRecord))
        assert usage.failed is True


def test_llm_provider_configuration_fails_closed_outside_tests():
    with pytest.raises(ValueError, match="test-only"):
        build_llm_provider(Settings(environment="development", llm_provider="fake", _env_file=None))
    with pytest.raises(ValueError, match="llm_provider"):
        Settings(environment="production", llm_provider="disabled", _env_file=None)
    provider = build_llm_provider(Settings(
        environment="test",
        llm_provider="openai",
        openai_api_key="test-key",
        _env_file=None,
    ))
    assert provider.name == "openai-compatible"
