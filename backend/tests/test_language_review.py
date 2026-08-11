import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import (
    ProviderConfigurationError,
    ProviderIncompleteResponse,
    ProviderOutputInvalid,
    ProviderRefusal,
    ProviderTimeout,
)
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
from backend.app.language_review.service import (
    LanguageReviewService,
    build_review_request,
    protected_content_digest,
)
from backend.app.models import AITurnAttempt, AIUsageRecord, ConversationMessage
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider


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


def _provider_response(content, *, status="completed", output=None):
    content = dict(content)
    content.pop("source_content_digest", None)
    content.pop("preserved_learning_terms", None)
    return {
        "id": "resp_language_review",
        "model": "gpt-5-mini",
        "status": status,
        "output": output if output is not None else [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(content, ensure_ascii=False)}],
        }],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


def _call_provider(request, response):
    provider = OpenAILanguageReviewProvider(
        OpenAILanguageReviewHTTPClient("secret-key", lambda *_args, **_kwargs: _HTTPResponse(response)),
        model="gpt-5-mini", max_retries=0,
    )
    return provider.review(request)


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
        provider_content = _review_content(request)
        provider_content.pop("source_content_digest")
        provider_content.pop("preserved_learning_terms")
        return _HTTPResponse({
            "id": "resp_language_review",
            "model": "gpt-5-mini",
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(provider_content, ensure_ascii=False)}],
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
    assert request.source_content_digest not in outgoing.data.decode()
    assert "source_content_digest" not in body["text"]["format"]["schema"]["properties"]
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


def test_validated_non_correction_pass_through_avoids_telugu_provider_call():
    source = _source_response("That's correct.").model_copy(update={
        "correction_type": "VALID_SENTENCE",
        "corrected_learner_sentence": None,
        "correction_explanation": None,
        "grammar_feedback": [],
    })

    class NeverCalled:
        def review(self, _request):
            raise AssertionError("review provider must not run for a correction-free normal turn")

    reviewed, result = LanguageReviewService(NeverCalled()).accept_validated_pass_through(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-fast-path",
    )

    assert reviewed == source
    assert result.review_reason_code == ReviewReasonCode.NOT_REQUIRED
    assert result.usage.provider_requests == 0
    assert result.provider_metadata_reference == "language-review:validated-pass-through:v1"


def test_missing_live_reviewer_is_configuration_failure_without_fake_request_count():
    with pytest.raises(ProviderConfigurationError) as captured:
        LanguageReviewService(None).review(
            _source_response(), language_mode=LanguageMode.ENGLISH_TELUGU,
            learning_objective="Daily conversation", learner_level="BEGINNER",
            correlation_id="correlation-1",
        )
    assert captured.value.failure_code == "provider_configuration_error"
    assert captured.value.provider_requests == 0
    assert captured.value.schema_path == "provider"


@pytest.mark.parametrize(
    ("mode", "changed", "reason", "terms"),
    [
        ("ENGLISH", False, "NOT_REQUIRED", []),
        ("ENGLISH_TELUGU", True, "IMPROVED_CODE_SWITCHING", []),
        ("TELUGU_DOMINANT", True, "NATURALIZED_TELUGU", ["grammar", "sentence"]),
    ],
)
def test_live_provider_shapes_validate_for_every_language_mode(mode, changed, reason, terms):
    source = _source_response()
    request = build_review_request(
        source, language_mode=LanguageMode(mode), learning_objective="Daily conversation",
        learner_level="BEGINNER", correlation_id="correlation-1",
    )
    content = _review_content(
        request, language_mode=mode, review_changed=changed,
        review_reason_code=reason, preserved_learning_terms=terms,
    )
    result = _call_provider(request, _provider_response(content))
    assert result.language_mode == LanguageMode(mode)
    assert result.review_changed is changed
    assert result.source_content_digest == request.source_content_digest


@pytest.mark.parametrize(
    ("mutation", "path"),
    [
        ({"final_encouragement": None}, "final_encouragement"),
        ({"unexpected_wrapper": {}}, "unexpected.unexpected_wrapper"),
        ({"language_mode": "MIXED"}, "language_mode"),
        ({"review_changed": "true"}, "review_changed"),
        ({"expression_hint": None}, "expression_hint"),
    ],
)
def test_live_provider_shape_rejects_invalid_contract(mutation, path):
    source = _source_response()
    request = build_review_request(
        source, language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation", learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    content = _review_content(request)
    content.update(mutation)
    with pytest.raises(ProviderOutputInvalid) as captured:
        _call_provider(request, _provider_response(content))
    assert path in (captured.value.schema_path or "")


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "తెలుగు ఉంది, ಆದರೆ ಇದು ಕನ್ನಡ.",
        "తెలుగు ఉంది, но это русский текст.",
        "తెలుగు ఉంది\u202e hidden direction.",
        "తెలుగు క్ి malformed.",
    ],
)
def test_live_reviewer_rejects_unsupported_script_and_malformed_unicode(unsafe_text):
    source = _source_response()
    request = build_review_request(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    content = _review_content(request, final_text=unsafe_text)
    with pytest.raises(ProviderOutputInvalid):
        _call_provider(request, _provider_response(content))


def test_live_provider_shape_rejects_missing_field_refusal_and_incomplete():
    source = _source_response()
    request = build_review_request(
        source, language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation", learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    content = _review_content(request)
    content.pop("final_text")
    with pytest.raises(ProviderOutputInvalid) as missing:
        _call_provider(request, _provider_response(content))
    assert missing.value.schema_path == "missing.final_text"

    refusal = _provider_response({}, output=[{
        "type": "message", "content": [{"type": "refusal", "refusal": "cannot comply"}],
    }])
    with pytest.raises(ProviderRefusal):
        _call_provider(request, refusal)

    incomplete = _provider_response({}, status="incomplete", output=[])
    incomplete["incomplete_details"] = {"reason": "max_output_tokens"}
    with pytest.raises(ProviderIncompleteResponse):
        _call_provider(request, incomplete)


def test_live_provider_shape_extracts_text_across_multiple_output_items():
    source = _source_response()
    request = build_review_request(
        source, language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation", learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    content = _review_content(request)
    content.pop("source_content_digest")
    content.pop("preserved_learning_terms")
    encoded = json.dumps(content, ensure_ascii=False)
    response = _provider_response({}, output=[
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": encoded}]},
    ])
    assert _call_provider(request, response).final_text == content["final_text"]


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


def test_reviewer_rejects_digest_mismatch_and_canonicalizes_learning_terms():
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
    _, result = LanguageReviewService(InvalidProvider({"preserved_learning_terms": []})).review(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    assert result.preserved_learning_terms == request.required_learning_terms


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


@pytest.mark.parametrize("mutation", [
    {"review_changed": False},
    {"review_reason_code": "NOT_REQUIRED"},
])
def test_reviewer_canonicalizes_application_owned_change_metadata(mutation):
    source = _source_response("A clear source response without a required learning term.")
    request = build_review_request(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )

    class Provider:
        def review(self, _):
            return LanguageReviewResult(
                **_review_content(request, **mutation),
                provider_metadata_reference="language-review:canonicalized:test",
                usage=UsageInfo(input_units=10, output_units=10),
            )

    _, result = LanguageReviewService(Provider()).review(
        source,
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learning_objective="Daily conversation",
        learner_level="BEGINNER",
        correlation_id="correlation-1",
    )
    assert result.review_changed is True
    assert result.review_reason_code != ReviewReasonCode.NOT_REQUIRED


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
    forbidden_phrases = {"పేరు చెప్పే word", "తేడా గమనించారా"}
    for case in cases:
        assert any("\u0c00" <= character <= "\u0c7f" for character in case["response"])
        assert not forbidden.intersection(case["response"].split())
        assert not any(phrase in case["response"] for phrase in forbidden_phrases)
        for term in case["preserved_learning_terms"]:
            assert term.lower() in case["response"].lower()

    responses = {case["id"]: case["response"] for case in cases}
    assert "చిన్న correction మాత్రమే ఉంది" in responses["grammar-correction-beginner"]
    assert "మాట్లాడే practice" in responses["encouragement-after-hesitation"]
    assert "మీ update clear గా ఉంటుంది" in responses["workplace-update"]
    assert "ఇంకొంచెం natural English గా" in responses["intermediate-opinion"]
    assert "difference అర్థమైందా?" in responses["complex-perfect-tense"]
    assert "idea ని సూచించే word" in responses["technical-terms-code-switch"]


def test_presentation_revisions_preserve_protected_content_digest():
    source = _source_response()
    learning_objective = "Daily conversation"
    original_digest = protected_content_digest(
        source,
        learning_objective=learning_objective,
    )
    revised = source.model_copy(update={
        "tutor_message": "మాట్లాడే practice చేస్తే confidence పెరుగుతుంది.",
        "correction_explanation": "ఈ sentence ని ఇంకొంచెం natural English గా చెప్పండి.",
        "conversation_question": "difference అర్థమైందా?",
        "encouragement": "చాలా బాగా చేస్తున్నారు.",
    })

    assert protected_content_digest(
        revised,
        learning_objective=learning_objective,
    ) == original_digest


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
    assert "llm;dur=" in turn.headers["server-timing"]
    assert "review;dur=" in turn.headers["server-timing"]
    assert "I go office" not in turn.headers["server-timing"]
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

    speech = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns/{body['turn_id']}/speech"
    )
    assert speech.status_code == 200
    assert speech.headers["server-timing"].startswith("tts;dur=")


def test_tts_revalidates_stored_spoken_text_before_provider_dispatch(client, conversation):
    turn = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        headers={"Idempotency-Key": "unsafe-stored-speech"},
        json={"message": "I practise every morning."},
    )
    assert turn.status_code == 200
    with client.app.state.session_factory() as session:
        attempt = session.get(AITurnAttempt, turn.json()["turn_id"])
        checkpoint = dict(attempt.result_json)
        api_result = dict(checkpoint["api_result"])
        api_result["spoken_text"] = "Это русский текст"
        checkpoint["api_result"] = api_result
        attempt.result_json = checkpoint
        session.commit()

    provider = client.app.state.text_to_speech_provider
    calls_before = provider.calls
    speech = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns/{turn.json()['turn_id']}/speech"
    )
    assert speech.status_code == 422
    assert speech.json()["error"]["code"] == "tts_invalid_text"
    assert provider.calls == calls_before


def test_review_failure_degrades_without_regenerating_or_duplicate_persistence(client, conversation):
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
    assert first.status_code == 200
    assert first.json()["language_review_status"] == "DEGRADED"
    assert first.json()["language_review_failure_code"] == "provider_timeout"
    second = client.post(route, headers=headers, json=payload)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert content.calls == 1
    assert reviewer.calls == 1

    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 1
        attempt = session.get(AITurnAttempt, second.json()["turn_id"])
        assert attempt.status == "COMPLETED"
        assert attempt.provider_attempts == 2
        usages = list(session.scalars(select(AIUsageRecord).where(
            AIUsageRecord.ai_turn_attempt_id == attempt.id
        )))
        assert {usage.outcome for usage in usages} == {"DEGRADED", "SUCCESS"}


def test_five_turn_pipeline_keeps_tts_available_when_one_review_is_malformed(client, conversation):
    client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "ananya", "language_mode": "ENGLISH_TELUGU"},
    )

    class MalformedThirdReview:
        def __init__(self):
            self.calls = 0
            self.good = DeterministicLanguageReviewProvider()

        def review(self, request):
            self.calls += 1
            if self.calls == 3:
                raise ProviderOutputInvalid(
                    "Injected malformed presentation.", provider_requests=1,
                    schema_path="final_text",
                )
            return self.good.review(request)

    tts = DeterministicTextToSpeechProvider()
    client.app.state.language_review_provider = MalformedThirdReview()
    client.app.state.text_to_speech_provider = tts
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    turns = []
    for index in range(5):
        turn = client.post(
            route,
            headers={"Idempotency-Key": f"five-turn-reliability-{index}"},
            json={"message": f"I want English practice turn {index}."},
        )
        assert turn.status_code == 200
        turns.append(turn.json())
        speech = client.post(f"{route}/{turn.json()['turn_id']}/speech")
        assert speech.status_code == 200
        assert speech.headers["content-type"].startswith("audio/wav")

    assert [turn["language_review_status"] for turn in turns] == [
        "COMPLETED", "COMPLETED", "DEGRADED", "COMPLETED", "COMPLETED",
    ]
    assert turns[2]["language_review_failure_code"] == "provider_schema_validation_failed"
    assert tts.calls == 5
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 5


def test_foreign_script_voice_misrecognition_is_rejected_before_provider_or_history(client, conversation):
    class CapturingProvider(DeterministicAIProvider):
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            return super().generate(request)

    provider = CapturingProvider()
    client.app.state.llm_provider = provider
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    anomalous = client.post(
        route,
        headers={"Idempotency-Key": "foreign-script-stt-1"},
        json={"message": "آری", "input_source": "VOICE", "detected_language": "fa"},
    )
    assert anomalous.status_code == 422
    assert anomalous.json()["error"]["code"] == "unusable_transcript"
    assert provider.requests == []

    clear = client.post(
        route,
        headers={"Idempotency-Key": "foreign-script-stt-2"},
        json={"message": "Can we start English practice?"},
    )
    assert clear.status_code == 200
    assert provider.requests[0].current_learner_message == "Can we start English practice?"
    assert provider.requests[0].conversation_history == []
