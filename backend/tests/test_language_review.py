import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import ProviderOutputInvalid, ProviderTimeout
from backend.app.ai.models import AIConversationRequest, UsageInfo
from backend.app.domain.enums import LanguageMode
from backend.app.language_review.deterministic import DeterministicLanguageReviewProvider
from backend.app.language_review.models import (
    ExpressionHint,
    LanguageReviewResult,
    ReviewReasonCode,
)
from backend.app.language_review.openai_boundary import (
    LANGUAGE_REVIEW_SCHEMA,
    OpenAILanguageReviewHTTPClient,
    OpenAILanguageReviewProvider,
)
from backend.app.language_review.service import LanguageReviewService, build_review_request
from backend.app.models import AITurnAttempt, AIUsageRecord, ConversationMessage


def _source_response(message="Your sentence has a small grammar change."):
    request = AIConversationRequest(
        learner_id="learner-1",
        conversation_id="conversation-1",
        learner_level="BEGINNER",
        scenario="daily-conversation",
        topic="Daily conversation",
        current_learner_message="I go office yesterday.",
        correlation_id="correlation-1",
    )
    response = DeterministicAIProvider().generate(request)
    return response.model_copy(update={"tutor_message": message})


class _HTTPResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.value, ensure_ascii=False).encode()


def _review_content(review_request, **overrides):
    content = {
        "final_text": "Good try! ఈ sentence లో grammar మాత్రమే కొంచెం మార్చాలి.",
        "final_correction_explanation": "ఈ sentence లో చిన్న correction చాలు.",
        "final_conversation_question": "ఇప్పుడు ఇదే sentence ని ఇంకోసారి చెబుతారా?",
        "final_encouragement": "బాగా చేస్తున్నారు—ఇలాగే practice కొనసాగించండి.",
        "language_mode": "ENGLISH_TELUGU",
        "review_changed": True,
        "review_reason_code": "IMPROVED_CODE_SWITCHING",
        "preserved_learning_terms": review_request.required_learning_terms,
        "expression_hint": "CORRECTIVE",
        "source_content_digest": review_request.source_content_digest,
    }
    content.update(overrides)
    return content


def test_openai_language_reviewer_uses_strict_schema_and_privacy_safe_payload():
    captured = {}
    source = _source_response()
    request = build_review_request(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="private-correlation",
    )

    def opener(outgoing, timeout):
        captured["request"] = outgoing
        captured["timeout"] = timeout
        return _HTTPResponse({
            "id": "resp_language_review",
            "model": "gpt-5-mini",
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(_review_content(request), ensure_ascii=False)}],
            }],
            "usage": {"input_tokens": 120, "output_tokens": 80},
        })

    provider = OpenAILanguageReviewProvider(
        OpenAILanguageReviewHTTPClient("secret-key", opener),
        model="gpt-5-mini",
        timeout_seconds=9,
        max_retries=0,
    )
    result = provider.review(request)

    outgoing = captured["request"]
    body = json.loads(outgoing.data)
    assert captured["timeout"] == 9
    assert outgoing.full_url == "https://api.openai.com/v1/responses"
    assert outgoing.get_header("Authorization") == "Bearer secret-key"
    assert "secret-key" not in outgoing.data.decode()
    assert "private-correlation" not in outgoing.data.decode()
    assert body["store"] is False
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "speakmate_native_telugu_review",
        "strict": True,
        "schema": LANGUAGE_REVIEW_SCHEMA,
    }
    assert set(LANGUAGE_REVIEW_SCHEMA["required"]) == set(LANGUAGE_REVIEW_SCHEMA["properties"])
    assert LANGUAGE_REVIEW_SCHEMA["additionalProperties"] is False
    assert result.language_mode == LanguageMode.ENGLISH_TELUGU
    assert result.usage == UsageInfo(input_units=120, output_units=80, provider_requests=1)


def test_english_mode_is_exact_pass_through_without_provider_call():
    class NeverCalled:
        def review(self, _):
            raise AssertionError("English mode must not make a paid review call")

    source = _source_response()
    reviewed, result = LanguageReviewService(NeverCalled()).review(
        source,
        language_mode=LanguageMode.ENGLISH,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )

    assert reviewed == source
    assert result.review_changed is False
    assert result.review_reason_code == ReviewReasonCode.NOT_REQUIRED
    assert result.usage.provider_requests == 0


@pytest.mark.parametrize("mode", [LanguageMode.ENGLISH_TELUGU, LanguageMode.TELUGU_DOMINANT])
def test_telugu_modes_preserve_protected_content(mode):
    source = _source_response()
    reviewed, result = LanguageReviewService(DeterministicLanguageReviewProvider()).review(
        source,
        language_mode=mode,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )

    assert reviewed.corrected_learner_sentence == source.corrected_learner_sentence
    assert reviewed.grammar_feedback == source.grammar_feedback
    assert reviewed.vocabulary_suggestions == source.vocabulary_suggestions
    assert reviewed.learning_signals == source.learning_signals
    assert reviewed.detected_level == source.detected_level
    assert reviewed.recommended_next_difficulty == source.recommended_next_difficulty
    assert result.language_mode == mode
    assert result.review_changed is True
    assert any("\u0c00" <= character <= "\u0c7f" for character in reviewed.tutor_message)


def test_reviewer_rejects_digest_mismatch_and_dropped_learning_term():
    source = _source_response()
    request = build_review_request(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )

    class InvalidProvider:
        def __init__(self, mutation):
            self.mutation = mutation

        def review(self, _):
            values = _review_content(request)
            values.update(self.mutation)
            return LanguageReviewResult(
                **values,
                provider_metadata_reference="language-review:invalid:test",
                usage=UsageInfo(input_units=10, output_units=10),
            )

    with pytest.raises(ProviderOutputInvalid, match="protected content binding"):
        LanguageReviewService(InvalidProvider({"source_content_digest": "0" * 64})).review(
            source,
            language_mode=LanguageMode.ENGLISH_TELUGU,
            learning_objective="Daily conversation",
            learner_level="BEGINNER",
            correlation_id="correlation-1",
        )
    with pytest.raises(ProviderOutputInvalid, match="dropped a required learning term"):
        LanguageReviewService(InvalidProvider({"preserved_learning_terms": []})).review(
            source,
            language_mode=LanguageMode.ENGLISH_TELUGU,
            learning_objective="Daily conversation",
            learner_level="BEGINNER",
            correlation_id="correlation-1",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            {
                "final_text": "Only English grammar and sentence output.",
                "final_correction_explanation": "Make a small sentence correction.",
                "final_conversation_question": "Will you say the sentence again?",
                "final_encouragement": "Keep up the practice.",
            },
            "did not contain Telugu",
        ),
        ({"review_changed": False}, "inconsistent change status"),
        ({"review_reason_code": "NOT_REQUIRED"}, "inconsistent reason code"),
    ],
)
def test_reviewer_rejects_wrong_language_and_inconsistent_review_metadata(mutation, message):
    source = _source_response("A clear source response without a required learning term.")
    request = build_review_request(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )

    class InvalidProvider:
        def review(self, _):
            return LanguageReviewResult(
                **_review_content(request, **mutation),
                provider_metadata_reference="language-review:invalid:test",
                usage=UsageInfo(input_units=10, output_units=10),
            )

    with pytest.raises(ProviderOutputInvalid, match=message):
        LanguageReviewService(InvalidProvider()).review(
            source,
            language_mode=LanguageMode.ENGLISH_TELUGU,
            learning_objective="Daily conversation",
            learner_level="BEGINNER",
            correlation_id="correlation-1",
        )


def test_telugu_quality_evaluation_set_covers_release_scenarios():
    path = Path(__file__).parents[1] / "evals" / "telugu_quality.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    categories = {case["category"] for case in cases}
    assert len(cases) >= 10
    assert categories == {
        "grammar correction",
        "pronunciation explanation",
        "encouragement",
        "mistake correction",
        "workplace English",
        "daily conversation",
        "beginner learner",
        "intermediate learner",
        "complex explanation",
        "positive feedback",
        "Telugu-dominant response",
        "Telugu + English technical terms",
    }
    forbidden = {"యొక్క", "చేయబడింది", "ఉపయోగించబడుతుంది", "ప్రయత్నము", "సంభాషణము"}
    for case in cases:
        assert any("\u0c00" <= character <= "\u0c7f" for character in case["response"])
        assert not forbidden.intersection(case["response"].split())
        for term in case["preserved_learning_terms"]:
            assert term.lower() in case["response"].lower()


def test_api_checkpoints_review_before_tts_and_exposes_customer_capability(client, conversation):
    preference = client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "ananya", "language_mode": "TELUGU_DOMINANT"},
    )
    assert preference.status_code == 200
    assert preference.json()["language_mode"] == "TELUGU_DOMINANT"

    turn = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        headers={"Idempotency-Key": "native-telugu-turn-1"},
        json={"message": "I go office yesterday."},
    )
    assert turn.status_code == 200
    body = turn.json()
    assert body["language_mode"] == "TELUGU_DOMINANT"
    assert body["review_changed"] is True
    assert body["review_reason_code"] == "NATURALIZED_TELUGU"
    assert body["expression_hint"] == "CORRECTIVE"
    assert any("\u0c00" <= character <= "\u0c7f" for character in body["tutor_message"])

    with client.app.state.session_factory() as session:
        attempt = session.get(AITurnAttempt, body["turn_id"])
        assert attempt.status == "COMPLETED"
        assert attempt.result_json["provider_response"]["tutor_message"].startswith("Thanks for sharing")
        assert attempt.result_json["reviewed_response"]["tutor_message"] == body["tutor_message"]
        message = session.scalar(select(ConversationMessage).where(
            ConversationMessage.ai_turn_attempt_id == attempt.id
        ))
        assert message.tutor_response == body["tutor_message"]


def test_review_retry_does_not_regenerate_content_or_duplicate_persistence(client, conversation):
    client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "ananya", "language_mode": "ENGLISH_TELUGU"},
    )

    class CountingContentProvider(DeterministicAIProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            return super().generate(request)

    class FailOnceReviewer:
        def __init__(self):
            self.calls = 0
            self.good = DeterministicLanguageReviewProvider()

        def review(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderTimeout("Review timed out.", provider_requests=1)
            return self.good.review(request)

    content = CountingContentProvider()
    reviewer = FailOnceReviewer()
    client.app.state.llm_provider = content
    client.app.state.language_review_provider = reviewer
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    headers = {"Idempotency-Key": "native-review-retry-1"}
    payload = {"message": "I go office yesterday."}

    first = client.post(route, headers=headers, json=payload)
    assert first.status_code == 504
    assert first.json()["error"]["code"] == "language_review_timeout"
    second = client.post(route, headers=headers, json=payload)
    assert second.status_code == 200
    third = client.post(route, headers=headers, json=payload)
    assert third.json() == second.json()
    assert content.calls == 1
    assert reviewer.calls == 2

    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 1
        attempt = session.get(AITurnAttempt, second.json()["turn_id"])
        assert attempt.status == "COMPLETED"
        assert attempt.provider_attempts == 3
        usages = list(session.scalars(select(AIUsageRecord).where(
            AIUsageRecord.ai_turn_attempt_id == attempt.id
        )))
        assert {usage.outcome for usage in usages} == {"FAILURE", "SUCCESS"}
