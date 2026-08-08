import json
from io import BytesIO
from urllib import error

import pytest
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import (
    ProviderConnectionError,
    ProviderContextLimit,
    ProviderIncompleteResponse,
    ProviderMalformedResponse,
    ProviderOutputInvalid,
    ProviderRateLimited,
    ProviderServiceError,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.ai.models import AIConversationRequest, ConversationHistoryTurn, UsageInfo
from backend.app.core.config import Settings
from backend.app.models import AICostMetricEvent, AITurnAttempt, AIUsageRecord, ConversationMessage
from backend.app.providers.llm import build_llm_provider
from backend.app.providers.llm.openai_boundary import OpenAICompatibleAIProvider, OpenAIResponsesHTTPClient
from backend.app.repositories.conversations import ConversationRepository, TurnSequenceConflict


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
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["max_output_tokens"] == 4096
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
    with pytest.raises(ProviderConnectionError):
        provider.generate(_request(current_learner_message=learner_content))
    captured = caplog.text
    assert secret not in captured
    assert learner_content not in captured


def test_responses_client_retries_one_transient_failure_and_reports_actual_requests():
    calls = []
    sleeps = []
    content = _content()
    content.pop("provider_metadata_reference")
    content.pop("usage")

    def intermittent(outgoing, timeout):
        calls.append((outgoing, timeout))
        if len(calls) == 1:
            raise error.URLError("temporary network failure")
        return _HTTPResponse({
            "id": "resp_recovered",
            "model": "gpt-5-mini",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(content)}],
            }],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    provider = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient("secret-key", intermittent, sleeps.append),
        model="gpt-5-mini",
        max_retries=1,
    )
    result = provider.generate(_request())

    assert len(calls) == 2
    assert sleeps == [0.25]
    assert result.usage.provider_requests == 2


def test_responses_client_classifies_incomplete_and_does_not_retry_malformed_output():
    calls = 0

    def context_failure(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise error.HTTPError(
            "https://api.openai.com/v1/responses",
            400,
            "bad request",
            {},
            BytesIO(json.dumps({"error": {"code": "context_length_exceeded"}}).encode()),
        )

    provider = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient("secret-key", context_failure, lambda _: None),
        model="gpt-5-mini",
        max_retries=1,
    )
    with pytest.raises(ProviderContextLimit):
        provider.generate(_request())
    assert calls == 1

    incomplete = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient(
            "secret-key",
            lambda *_args, **_kwargs: _HTTPResponse({
                "id": "resp_incomplete",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
                "usage": {"input_tokens": 120, "output_tokens": 900},
            }),
        ),
        model="gpt-5-mini",
        max_retries=1,
    )
    with pytest.raises(ProviderIncompleteResponse) as captured:
        incomplete.generate(_request())
    assert captured.value.provider_requests == 1
    assert captured.value.input_units == 120
    assert captured.value.output_units == 900

    malformed = OpenAICompatibleAIProvider(
        OpenAIResponsesHTTPClient(
            "secret-key",
            lambda *_args, **_kwargs: _HTTPResponse({
                "id": "resp_malformed",
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "not-json"}],
                }],
            }),
        ),
        model="gpt-5-mini",
        max_retries=1,
    )
    with pytest.raises(ProviderMalformedResponse):
        malformed.generate(_request())


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
    ("provider_error", "status_code", "error_code", "retryable"),
    [
        (ProviderTimeout("raw timeout detail"), 504, "llm_timeout", True),
        (ProviderConnectionError("raw connection detail"), 503, "llm_connection_error", True),
        (ProviderRateLimited("raw limit detail"), 429, "llm_rate_limited", True),
        (ProviderServiceError("raw service detail"), 502, "llm_provider_error", True),
        (ProviderContextLimit("raw context detail"), 422, "llm_context_limit", False),
        (
            ProviderIncompleteResponse(
                "raw incomplete detail", input_units=120, output_units=900,
            ),
            502,
            "llm_incomplete_response",
            True,
        ),
        (ProviderMalformedResponse("raw malformed detail"), 502, "llm_malformed_response", False),
        (ProviderOutputInvalid("raw schema detail"), 502, "llm_schema_validation_failed", False),
        (ProviderUnavailable("raw provider detail"), 503, "llm_unavailable", False),
    ],
)
def test_ai_turn_maps_provider_failures_without_persisting_a_message(
    client, learner, conversation, provider_error, status_code, error_code, retryable, caplog,
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
    assert response.json()["error"]["retryable"] is retryable
    assert "raw" not in response.text
    assert "raw" not in caplog.text
    assert provider_error.failure_code in caplog.text
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 0
        usage = db.scalar(select(AIUsageRecord).where(AIUsageRecord.outcome == "FAILURE"))
        assert usage.failed is True
        assert usage.input_units == provider_error.input_units
        assert usage.output_units == provider_error.output_units
        assert db.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.outcome == "SUCCESS"
        )) == 0


def test_transient_failure_retries_with_same_identity_and_persists_exactly_once(
    client, learner, conversation,
):
    class IntermittentProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ProviderConnectionError("temporary failure", provider_requests=2)
            return _content("Recovered tutor response.")

    provider = IntermittentProvider()
    client.app.state.llm_provider = provider
    headers = {"Idempotency-Key": "turn-recovery-0001"}
    payload = {"message": "I want to practise this sentence."}

    failed = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )
    recovered = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )
    replayed = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "llm_connection_error"
    assert recovered.status_code == 200
    assert replayed.json() == recovered.json()
    assert len(provider.requests) == 2
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 1
        assert db.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.outcome == "SUCCESS"
        )) == 1
        failure = db.scalar(select(AIUsageRecord).where(AIUsageRecord.outcome == "FAILURE"))
        assert failure.request_count == 2
        attempt = db.scalar(select(AITurnAttempt))
        assert attempt.status == "COMPLETED"
        assert attempt.provider_attempts == 3
        message = db.scalar(select(ConversationMessage))
        assert message.learner_text == payload["message"]
        assert message.ai_turn_attempt_id == attempt.id

    continued = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": "Can we continue now?"},
        headers={"Idempotency-Key": "turn-recovery-0002"},
    )
    assert continued.status_code == 200
    assert provider.requests[-1].conversation_history[-1].learner_message == payload["message"]


def test_incomplete_openai_turn_can_be_retried_safely_and_is_persisted_once(
    client, learner, conversation,
):
    class IncompleteOnceProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ProviderIncompleteResponse(
                    "max output tokens reached",
                    input_units=160,
                    output_units=900,
                )
            return _content("Recovered after an incomplete OpenAI response.")

    provider = IncompleteOnceProvider()
    client.app.state.llm_provider = provider
    headers = {"Idempotency-Key": "turn-incomplete-0001"}
    payload = {"message": "Please continue our conversation."}

    failed = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )
    recovered = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )
    replayed = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "llm_incomplete_response"
    assert failed.json()["error"]["retryable"] is True
    assert recovered.status_code == 200
    assert replayed.json() == recovered.json()
    assert len(provider.requests) == 2
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 1
        assert db.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.outcome == "SUCCESS"
        )) == 1
        failure = db.scalar(select(AIUsageRecord).where(AIUsageRecord.outcome == "FAILURE"))
        assert failure.request_count == 1
        assert failure.input_units == 160
        assert failure.output_units == 900


def test_persistence_retry_reuses_checkpoint_without_second_provider_call(
    client, learner, conversation, monkeypatch,
):
    provider = _RecordingProvider()
    client.app.state.llm_provider = provider
    original = ConversationRepository.add_message
    failures = 0

    def fail_once(self, *args, **kwargs):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise TurnSequenceConflict
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ConversationRepository, "add_message", fail_once)
    headers = {"Idempotency-Key": "turn-persistence-0001"}
    payload = {"message": "Please preserve my turn."}
    failed = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )
    recovered = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json=payload,
        headers=headers,
    )

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "llm_persistence_failed"
    assert recovered.status_code == 200
    assert len(provider.requests) == 1
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 1
        assert db.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.outcome == "SUCCESS"
        )) == 1


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
    assert provider.reasoning_effort == "minimal"
    assert provider.max_output_tokens == 4096
