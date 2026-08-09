import pytest
from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.models import AIConversationResponse, AIConversationRequest
from backend.app.coaching import (
    CoachingMode,
    CoachingState,
    LearnerIntent,
    build_coaching_outcome,
    classify_learner_intent,
    protect_learner_facts,
    retry_matches,
    smallest_useful_error_span,
)
from backend.app.domain.enums import LanguageMode
from backend.app.explanation_language import (
    ExplanationLanguage,
    ExplanationLanguageState,
    resolve_explanation_language,
)
from backend.app.models import AICostMetricEvent, AITurnAttempt, AIUsageRecord, ConversationMessage


def test_self_introduction_uses_smallest_useful_span():
    assert smallest_useful_error_span(
        "Hi, myself Nagaraj.", "Hi, I'm Nagaraj.",
    ) == ("myself Nagaraj", "I'm Nagaraj")


def test_self_introduction_explanation_is_grammatically_accurate():
    outcome = build_coaching_outcome(
        _response(
            corrected_learner_sentence="Hi, I'm Nagaraj.",
            correction_explanation="Use a different phrase.", grammar_feedback=["introduction"],
        ),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        learner_text="Hi, myself Nagaraj.",
    )
    assert outcome.incorrect_span == "myself Nagaraj"
    explanation = outcome.response.correction_explanation
    assert explanation is not None
    assert "reflexive or intensive pronoun, not a noun" in explanation
    assert "I'm Nagaraj" in explanation
    assert "My name is Nagaraj" in explanation


def test_unusable_voice_ai_turn_creates_no_attempt_or_message(client, conversation):
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    response = client.post(
        route, json={"message": "...", "input_source": "VOICE"},
        headers={"Idempotency-Key": "unsafe-voice-turn"},
    )
    assert response.status_code == 422
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AITurnAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 0


def test_new_telugu_help_intent_preserves_pending_correction():
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "I'm Nagaraj.",
        "incorrect_span": "myself Nagaraj",
        "corrected_form": "I'm Nagaraj",
        "correction_explanation": "Use I'm for a self-introduction.",
    }
    message = "myself అనేది noun ఎందుకు కాదు? grammar చెప్పండి"
    intent = classify_learner_intent(message, prior)
    assert intent == LearnerIntent.GRAMMAR_HELP
    outcome = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH_TELUGU,
        previous_result=prior, previous_turn_id="original", learner_text=message,
        learner_intent=intent,
    )
    assert outcome.state == CoachingState.EXPLAINING_CORRECTION
    assert outcome.retry_of_turn_id == "original"
    assert outcome.response.corrected_learner_sentence == "I'm Nagaraj."


def test_semantically_equivalent_self_introduction_closes_retry_without_optional_words():
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "Hi, I'm Nagaraj.",
        "correction_explanation": "Use I am or I'm for an introduction.",
    }
    assert retry_matches("I am Nagaraj.", prior["corrected_sentence"])
    outcome = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        previous_result=prior, previous_turn_id="original", learner_text="I am Nagaraj.",
        learner_intent=classify_learner_intent("I am Nagaraj.", prior),
    )
    assert outcome.state == CoachingState.RETRY_ACCEPTED
    assert outcome.retry_of_turn_id == "original"
    assert "once more" not in outcome.spoken_text


@pytest.mark.parametrize("message", [
    "Na peru Nagaraju.",
    "Let's talk about my hometown.",
])
def test_new_conversation_intent_exits_old_retry_without_repeating_it(message):
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "Hi, I'm Nagaraj.",
        "correction_explanation": "Use I am or I'm for an introduction.",
    }
    intent = classify_learner_intent(message, prior)
    assert intent == LearnerIntent.NORMAL_CONVERSATION
    response = _response(corrected_learner_sentence=None, correction_explanation=None)
    outcome = build_coaching_outcome(
        response, learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        previous_result=prior, previous_turn_id="original", learner_text=message,
        learner_intent=intent,
    )
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert outcome.retry_of_turn_id is None
    assert prior["correction_explanation"] not in outcome.spoken_text
    assert prior["corrected_sentence"] not in outcome.spoken_text


def test_nonmatching_attempt_does_not_repeat_the_full_old_explanation():
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "I have been working here for five years.",
        "correction_explanation": "A long explanation that should not repeat.",
    }
    message = "I have working here for five years."
    intent = classify_learner_intent(message, prior)
    assert intent == LearnerIntent.NORMAL_CONVERSATION
    outcome = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        previous_result=prior, previous_turn_id="original", learner_text=message,
        learner_intent=intent,
    )
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert prior["correction_explanation"] not in outcome.spoken_text


def test_unrelated_grammar_question_does_not_inherit_pending_correction():
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "I'm Nagaraj.",
        "incorrect_span": "myself Nagaraj",
        "corrected_form": "I'm Nagaraj",
        "correction_explanation": "Use I am for a self-introduction.",
    }
    message = "What is present perfect tense?"
    intent = classify_learner_intent(message, prior)
    assert intent == LearnerIntent.GRAMMAR_HELP
    outcome = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        previous_result=prior, previous_turn_id="original", learner_text=message,
        learner_intent=intent,
    )
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert outcome.retry_of_turn_id is None
    assert prior["correction_explanation"] not in outcome.spoken_text


def test_guided_market_lesson_intent_exits_old_retry():
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": "Hi, I'm Nagaraj.",
        "correction_explanation": "Use I am for an introduction.",
    }
    message = "మార్కెట్‌లో మాట్లాడటం step by step నేర్పించండి"
    intent = classify_learner_intent(message, prior)
    assert intent == LearnerIntent.GUIDED_ROLEPLAY
    outcome = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH_TELUGU,
        previous_result=prior, previous_turn_id="original", learner_text=message,
        learner_intent=intent,
    )
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert outcome.retry_of_turn_id is None
    assert prior["correction_explanation"] not in outcome.spoken_text


@pytest.mark.parametrize(("learner_text", "provider_correction"), [
    ("My hometown is Kanpur.", "My hometown is Guntur."),
    ("My name is Nagaraju.", "My name is Nagaraj."),
    ("The price is 500 rupees.", "The price is 50 rupees."),
    ("I work as a teacher.", "I work as an engineer."),
    ("I live in Kanpur.", "I live in Guntur."),
    ("My name is నాగరాజు.", "My name is రవి."),
])
def test_provider_cannot_overwrite_learner_factual_slots(learner_text, provider_correction):
    unsafe = _response(
        tutor_message=f"The correct fact is {provider_correction}",
        corrected_learner_sentence=provider_correction,
        correction_explanation="Use the earlier value.",
        grammar_feedback=["fact replacement"],
    )
    protected = protect_learner_facts(unsafe, learner_text)
    assert protected.corrected_learner_sentence is None
    assert protected.correction_explanation is None
    assert protected.grammar_feedback == []
    assert learner_text.rstrip(".") in protected.tutor_message
    assert "The correct fact" not in protected.tutor_message


@pytest.mark.parametrize(("learner", "suggestion"), [
    ("I am Nagaraj.", "Hi, I'm Nagaraj."),
    ("How much is this?", "Excuse me, how much is this?"),
    ("Yes, my hometown is Kanpur.", "My hometown is Kanpur."),
])
def test_style_only_suggestion_is_not_a_mandatory_correction(learner, suggestion):
    response = protect_learner_facts(_response(
        corrected_learner_sentence=suggestion,
        correction_explanation="This sounds more natural.",
        grammar_feedback=["style"],
    ), learner)
    outcome = build_coaching_outcome(
        response, learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
        learner_text=learner,
    )
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert outcome.response.corrected_learner_sentence is None


@pytest.mark.parametrize("bad_explanation", [
    "'అండి' అనేది informal form.",
    "'అండి' అనేది అనౌపచారికమైనది.",
    "How much is this? అనేది సబ్జెక్ట్-వర్బ్-ఓబ్జెక్ట్ structure.",
])
def test_exact_runtime_pedagogy_misclaims_are_repaired(bad_explanation):
    from backend.app.coaching import apply_pedagogy_guardrails

    guarded = apply_pedagogy_guardrails(_response(correction_explanation=bad_explanation))
    explanation = guarded.correction_explanation or ""
    assert "అనౌపచారిక" not in explanation
    assert "సబ్జెక్ట్-వర్బ్-ఓబ్జెక్ట్" not in explanation
    assert "polite and respectful" in explanation or "wh-question" in explanation


def test_api_semantic_retry_closes_state_and_next_intent_stays_fresh(client, conversation):
    assert client.put(
        "/api/v1/tutors/preference", json={"tutor_id": "ananya", "language_mode": "ENGLISH"},
    ).status_code == 200

    class RuntimeProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            base = DeterministicAIProvider().generate(request)
            if self.calls == 1:
                return base.model_copy(update={
                    "tutor_message": "Let us make that introduction natural.",
                    "corrected_learner_sentence": "Hi, I'm Nagaraj.",
                    "correction_explanation": "Use I am or I'm for a self-introduction.",
                    "grammar_feedback": ["self-introduction", "subject pronoun"],
                })
            return base.model_copy(update={
                "tutor_message": "Thanks, let us continue with your new answer.",
                "corrected_learner_sentence": None,
                "correction_explanation": None,
                "grammar_feedback": [],
            })

    client.app.state.llm_provider = RuntimeProvider()
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    first = client.post(route, json={"message": "Hey, myself Nagaraj."}).json()
    assert first["coaching_state"] == "WAITING_FOR_RETRY"

    accepted = client.post(route, json={"message": "I am Nagaraj."}).json()
    assert accepted["learner_intent"] == "RETRY"
    assert accepted["coaching_state"] == "RETRY_ACCEPTED"
    assert accepted["retry_of_turn_id"] == first["turn_id"]
    assert first["correction_explanation"] not in accepted["spoken_text"]

    fresh = client.post(route, json={"message": "Na peru Nagaraju."}).json()
    assert fresh["learner_intent"] == "NORMAL_CONVERSATION"
    assert fresh["coaching_state"] == "NORMAL_CONVERSATION"
    assert fresh["retry_of_turn_id"] is None
    assert first["correction_explanation"] not in fresh["spoken_text"]


def test_api_explanation_then_retry_keeps_original_correction_identity(client, conversation):
    assert client.put(
        "/api/v1/tutors/preference", json={"tutor_id": "ananya", "language_mode": "ENGLISH"},
    ).status_code == 200

    class ExplanationProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            base = DeterministicAIProvider().generate(request)
            if self.calls == 1:
                return base.model_copy(update={
                    "corrected_learner_sentence": "I'm Nagaraj.",
                    "correction_explanation": "Use I am or I'm, not myself, for this introduction.",
                    "grammar_feedback": ["self-introduction", "pronoun"],
                })
            return base.model_copy(update={
                "tutor_message": "Here is the requested help.",
                "corrected_learner_sentence": None,
                "correction_explanation": None,
                "grammar_feedback": [],
            })

    client.app.state.llm_provider = ExplanationProvider()
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    correction = client.post(route, json={"message": "Myself Nagaraj."}).json()
    explanation = client.post(route, json={"message": "Why is myself wrong?"}).json()
    assert explanation["coaching_state"] == "EXPLAINING_CORRECTION"
    assert explanation["retry_of_turn_id"] == correction["turn_id"]

    accepted = client.post(route, json={"message": "I am Nagaraj."}).json()
    assert accepted["coaching_state"] == "RETRY_ACCEPTED"
    assert accepted["retry_of_turn_id"] == correction["turn_id"]
    assert accepted["correction_explanation_default"] is None


def test_api_new_fact_and_guided_lesson_do_not_replay_old_correction(client, conversation):
    assert client.put(
        "/api/v1/tutors/preference", json={"tutor_id": "ananya", "language_mode": "ENGLISH"},
    ).status_code == 200

    class TopicProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            base = DeterministicAIProvider().generate(request)
            if len(self.requests) == 1:
                return base.model_copy(update={
                    "corrected_learner_sentence": "My hometown is Guntur.",
                    "correction_explanation": "Add 'is' to complete the sentence.",
                    "grammar_feedback": ["missing verb", "sentence structure"],
                })
            return base.model_copy(update={
                "tutor_message": "Let us practise the market conversation step by step.",
                "corrected_learner_sentence": None,
                "correction_explanation": None,
                "grammar_feedback": [],
            })

    provider = TopicProvider()
    client.app.state.llm_provider = provider
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    first = client.post(route, json={"message": "My hometown Guntur."}).json()
    assert first["coaching_state"] == "WAITING_FOR_RETRY"

    guided = client.post(
        route, json={"message": "మార్కెట్‌లో మాట్లాడటం step by step నేర్పించండి"},
    ).json()
    assert guided["learner_intent"] == "GUIDED_ROLEPLAY"
    assert guided["coaching_state"] == "NORMAL_CONVERSATION"
    assert guided["retry_of_turn_id"] is None
    assert "Guntur" not in guided["spoken_text"]
    assert "guided, interactive scenario lesson" in provider.requests[-1].current_learner_message


def test_api_provider_cannot_change_kanpur_to_guntur_anywhere(client, conversation):
    assert client.put(
        "/api/v1/tutors/preference", json={"tutor_id": "ananya", "language_mode": "ENGLISH"},
    ).status_code == 200

    class UnsafeFactProvider:
        def generate(self, request):
            base = DeterministicAIProvider().generate(request)
            return base.model_copy(update={
                "tutor_message": "Your hometown is Guntur.",
                "corrected_learner_sentence": "My hometown is Guntur.",
                "correction_explanation": "Change Kanpur to Guntur.",
                "grammar_feedback": ["Use Guntur"],
                "vocabulary_suggestions": ["Guntur"],
                "conversation_question": "What do you like about Guntur?",
                "encouragement": "Guntur is correct.",
            })

    client.app.state.llm_provider = UnsafeFactProvider()
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"
    body = client.post(route, json={"message": "My hometown is Kanpur."}).json()
    serialized = str(body)
    assert body["corrected_sentence"] is None
    assert "Kanpur" in body["tutor_message"]
    assert "Guntur" not in serialized
    with client.app.state.session_factory() as db:
        stored = db.scalar(select(ConversationMessage))
        assert stored is not None
        assert stored.learner_text == "My hometown is Kanpur."
        assert "Guntur" not in stored.tutor_response


def _response(**updates) -> AIConversationResponse:
    request = AIConversationRequest(
        learner_id="learner-1",
        conversation_id="conversation-1",
        learner_level="BEGINNER",
        scenario="daily-conversation",
        topic="Daily conversation",
        current_learner_message="I work here since five years",
        correlation_id="correlation-1",
    )
    return DeterministicAIProvider().generate(request).model_copy(update=updates)


def test_no_correction_continues_naturally():
    response = _response(corrected_learner_sentence=None, correction_explanation=None)
    outcome = build_coaching_outcome(
        response, learner_level="BEGINNER", language_mode=LanguageMode.ENGLISH,
    )
    assert outcome.mode == CoachingMode.NO_CORRECTION
    assert outcome.state == CoachingState.NORMAL_CONVERSATION
    assert outcome.spoken_text == f"{response.tutor_message} {response.conversation_question}"


@pytest.mark.parametrize(("learner", "corrected", "wrong", "right"), [
    ("She don't like coffee.", "She doesn't like coffee.", "She don't like coffee", "She doesn't like coffee"),
    ("I didn't went there.", "I didn't go there.", "didn't went", "didn't go"),
    ("My brother have two cars.", "My brother has two cars.", "My brother have two cars", "My brother has two cars"),
    ("I have seen him yesterday.", "I saw him yesterday.", "I have seen him yesterday", "I saw him yesterday"),
])
def test_short_error_span_keeps_useful_sentence_context(learner, corrected, wrong, right):
    assert smallest_useful_error_span(learner, corrected) == (wrong, right)


def test_long_utterance_uses_compact_clause_and_never_replays_full_answer():
    learner = "Yesterday after finishing my work I go to my friend house because he called me in the evening."
    corrected = "Yesterday after finishing my work I went to my friend's house because he called me in the evening."
    wrong, right = smallest_useful_error_span(learner, corrected)
    assert wrong == "I go to my friend house"
    assert right == "I went to my friend's house"
    assert wrong != learner.rstrip(".")


def test_spoken_order_and_shared_evidence_for_meaningful_telugu_correction():
    learner = "Yesterday after finishing my work I go to my friend house because he called me in the evening."
    explanation = "ఇక్కడ yesterday past time కాబట్టి go కాకుండా went వాడాలి."
    outcome = build_coaching_outcome(
        _response(
            corrected_learner_sentence="Yesterday after finishing my work I went to my friend's house because he called me in the evening.",
            correction_explanation=explanation,
            grammar_feedback=["past tense", "possessive"],
        ),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learner_text=learner,
    )
    assert outcome.state == CoachingState.WAITING_FOR_RETRY
    assert outcome.incorrect_span and outcome.corrected_form
    wrong_at = outcome.spoken_text.index(outcome.incorrect_span)
    right_at = outcome.spoken_text.index(outcome.corrected_form)
    explanation_at = outcome.spoken_text.index(explanation)
    retry_at = outcome.spoken_text.index("ఒకసారి చెప్పండి")
    assert wrong_at < right_at < explanation_at < retry_at
    assert learner.rstrip(".") not in outcome.spoken_text


def test_light_correction_uses_the_same_evidence_and_continues():
    response = _response(
        corrected_learner_sentence="I have been working here for five years.",
        correction_explanation="Use 'for' with a duration.",
        grammar_feedback=["duration"],
    )
    outcome = build_coaching_outcome(
        response, learner_level="ADVANCED", language_mode=LanguageMode.ENGLISH,
    )
    assert outcome.mode == CoachingMode.LIGHT_CORRECTION
    assert outcome.state == CoachingState.CORRECTION_PRESENTED
    assert response.corrected_learner_sentence in outcome.spoken_text
    assert response.correction_explanation in outcome.spoken_text
    assert response.conversation_question in outcome.spoken_text


def test_telugu_meaningful_correction_waits_for_retry_then_accepts_it():
    corrected = "I have been working here for five years."
    explanation = "ఇక్కడ duration కోసం 'for' వాడాలి."
    first = build_coaching_outcome(
        _response(
            corrected_learner_sentence=corrected,
            correction_explanation=explanation,
            grammar_feedback=["present perfect continuous"],
        ),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH_TELUGU,
    )
    assert first.mode == CoachingMode.RETRY_REQUIRED
    assert first.state == CoachingState.WAITING_FOR_RETRY
    assert corrected in first.spoken_text
    assert explanation in first.spoken_text
    assert "ఒకసారి చెప్పండి" in first.spoken_text
    assert first.response.conversation_question not in first.spoken_text

    accepted = build_coaching_outcome(
        _response(corrected_learner_sentence=None, correction_explanation=None),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH_TELUGU,
        previous_result={
            "coaching_state": "WAITING_FOR_RETRY",
            "corrected_sentence": corrected,
            "correction_explanation": explanation,
        },
        previous_turn_id="first-turn",
        learner_text="I have been working here for five years",
    )
    assert accepted.state == CoachingState.RETRY_ACCEPTED
    assert accepted.retry_of_turn_id == "first-turn"
    assert "సరైంది" in accepted.spoken_text
    assert accepted.response.conversation_question in accepted.spoken_text


def test_api_live_coaching_spoken_tts_retry_and_accounting_are_aligned(
    client, learner, conversation,
):
    corrected = "I have been working here for five years."

    class CorrectionProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            base = DeterministicAIProvider().generate(request)
            if self.calls == 1:
                return base.model_copy(update={
                    "corrected_learner_sentence": corrected,
                    "correction_explanation": "Use present perfect continuous for an action that is still continuing.",
                    "grammar_feedback": ["present perfect continuous", "for with duration"],
                    "conversation_question": "What do you enjoy about your work?",
                })
            return base.model_copy(update={
                "corrected_learner_sentence": None,
                "correction_explanation": None,
                "grammar_feedback": [],
                "tutor_message": "Your retry is correct.",
            })

    class RecordingTTS:
        name = "recording-tts"

        def __init__(self):
            self.texts = []

        def synthesize(self, request):
            self.texts.append(request.text)
            from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
            return DeterministicTextToSpeechProvider().synthesize(request)

    client.app.state.llm_provider = CorrectionProvider()
    tts = RecordingTTS()
    client.app.state.text_to_speech_provider = tts
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"

    first = client.post(
        route,
        json={"message": "I work here since five years"},
        headers={"Idempotency-Key": "spoken-coaching-first"},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["corrected_sentence"] == corrected
    assert first_body["coaching_mode"] == "RETRY_REQUIRED"
    assert first_body["coaching_state"] == "WAITING_FOR_RETRY"
    assert first_body["correction_explanation"] in first_body["spoken_text"]
    assert corrected in first_body["spoken_text"]
    assert first_body["next_question"] not in first_body["spoken_text"]

    first_speech = client.post(f"{route}/{first_body['turn_id']}/speech")
    assert first_speech.status_code == 200
    assert tts.texts == [first_body["spoken_text"]]

    retry = client.post(
        route,
        json={"message": corrected},
        headers={"Idempotency-Key": "spoken-coaching-retry"},
    )
    assert retry.status_code == 200
    retry_body = retry.json()
    assert retry_body["coaching_state"] == "RETRY_ACCEPTED"
    assert retry_body["retry_of_turn_id"] == first_body["turn_id"]
    assert retry_body["next_question"] in retry_body["spoken_text"]
    assert client.post(f"{route}/{retry_body['turn_id']}/speech").status_code == 200
    assert tts.texts == [first_body["spoken_text"], retry_body["spoken_text"]]

    replay = client.post(
        route,
        json={"message": corrected},
        headers={"Idempotency-Key": "spoken-coaching-retry"},
    )
    assert replay.json() == retry_body
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 2
        assert db.scalar(select(func.count()).select_from(AICostMetricEvent)) == 2
        assert db.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.provider_kind == "llm"
        )) == 2


def test_explanation_language_intent_requires_explicit_request():
    ordinary = resolve_explanation_language(
        "I am working here since five years.", LanguageMode.ENGLISH_TELUGU,
    )
    assert ordinary.state == ExplanationLanguageState.DEFAULT_PREFERENCE
    assert ordinary.language == ExplanationLanguage.TELUGU
    assert ordinary.effective_mode == LanguageMode.ENGLISH_TELUGU

    one_turn = resolve_explanation_language("Explain in English.", LanguageMode.ENGLISH_TELUGU)
    assert one_turn.state == ExplanationLanguageState.ONE_TURN_OVERRIDE
    assert one_turn.language == ExplanationLanguage.ENGLISH
    assert one_turn.persist_mode is None

    persistent = resolve_explanation_language(
        "From now on explain everything in English.", LanguageMode.ENGLISH_TELUGU,
    )
    assert persistent.state == ExplanationLanguageState.PERSISTENT_PREFERENCE_CHANGE
    assert persistent.persist_mode == LanguageMode.ENGLISH


def test_telugu_default_coaching_keeps_english_sentence_and_telugu_retry():
    corrected = "She doesn't like coffee."
    explanation = "ఇక్కడ 'She' third-person singular కాబట్టి 'don't' బదులు 'doesn't' వాడాలి."
    outcome = build_coaching_outcome(
        _response(
            corrected_learner_sentence=corrected,
            correction_explanation=explanation,
            grammar_feedback=["third-person singular"],
        ),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH_TELUGU,
    )
    assert explanation in outcome.spoken_text
    assert f'Correct sentence: "{corrected}"' in outcome.spoken_text
    assert "corrected sentence ని ఒకసారి చెప్పండి" in outcome.spoken_text
    assert outcome.state == CoachingState.WAITING_FOR_RETRY


def test_one_turn_english_reexplanation_uses_current_evidence_then_default_can_return():
    corrected = "I have been working here for five years."
    prior = {
        "coaching_state": "WAITING_FOR_RETRY",
        "corrected_sentence": corrected,
        "correction_explanation": "Duration కోసం 'for' వాడాలి.",
    }
    english = build_coaching_outcome(
        _response(
            corrected_learner_sentence=corrected,
            correction_explanation="Use 'for' for a duration and 'since' for a starting point.",
        ),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH,
        previous_result=prior,
        learner_text="Explain in English.",
        explanation_language_state=ExplanationLanguageState.ONE_TURN_OVERRIDE,
    )
    assert "Use 'for' for a duration" in english.spoken_text
    assert "Please say the corrected sentence once more" in english.spoken_text
    assert english.state == CoachingState.WAITING_FOR_RETRY

    returned = resolve_explanation_language(
        "Yesterday I go to office.", LanguageMode.ENGLISH_TELUGU,
    )
    assert returned.language == ExplanationLanguage.TELUGU
    assert returned.state == ExplanationLanguageState.DEFAULT_PREFERENCE


def test_api_default_override_return_and_persistent_preference_with_tts(client, learner, conversation):
    corrected = "I have been working here for five years."

    class PolicyProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            base = DeterministicAIProvider().generate(request)
            english = request.preferred_language == "ENGLISH"
            return base.model_copy(update={
                "corrected_learner_sentence": corrected,
                "correction_explanation": (
                    "Use 'for' for duration and 'since' for a starting point."
                    if english else
                    "Duration చెప్పేటప్పుడు 'for' వాడాలి; starting point కోసం 'since' వాడాలి."
                ),
                "grammar_feedback": ["for with duration", "present perfect continuous"],
            })

    class RecordingTTS:
        name = "recording-tts"

        def __init__(self):
            self.requests = []

        def synthesize(self, request):
            self.requests.append(request)
            from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
            return DeterministicTextToSpeechProvider().synthesize(request)

    assert client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "ananya", "language_mode": "ENGLISH_TELUGU"},
    ).status_code == 200
    provider = PolicyProvider()
    tts = RecordingTTS()
    client.app.state.llm_provider = provider
    client.app.state.text_to_speech_provider = tts
    route = f"/api/v1/conversations/{conversation['id']}/ai-turns"

    telugu = client.post(
        route,
        json={"message": "I am working here since five years."},
        headers={"Idempotency-Key": "policy-telugu-default"},
    ).json()
    assert telugu["explanation_language"] == "TELUGU"
    assert telugu["explanation_language_state"] == "DEFAULT_PREFERENCE"
    assert telugu["coaching_state"] == "WAITING_FOR_RETRY"
    assert corrected in telugu["spoken_text"]
    assert "sentence" in telugu["correction_explanation"]
    assert client.post(f"{route}/{telugu['turn_id']}/speech").status_code == 200
    assert tts.requests[-1].text == telugu["spoken_text"]
    assert "Andhra/Telangana Telugu" in tts.requests[-1].instructions
    assert "neutral Indian English" in tts.requests[-1].instructions

    override = client.post(
        route,
        json={"message": "Explain in English."},
        headers={"Idempotency-Key": "policy-english-one-turn"},
    ).json()
    assert override["explanation_language"] == "ENGLISH"
    assert override["explanation_language_state"] == "ONE_TURN_OVERRIDE"
    assert "Use 'for' for duration" in override["correction_explanation"]
    assert override["correction_explanation"] in override["spoken_text"]
    assert client.post(f"{route}/{override['turn_id']}/speech").status_code == 200
    assert "neutral Indian English" in tts.requests[-1].instructions

    back_to_telugu = client.post(
        route,
        json={"message": "Yesterday I go to office."},
        headers={"Idempotency-Key": "policy-return-telugu"},
    ).json()
    assert back_to_telugu["explanation_language"] == "TELUGU"
    assert back_to_telugu["explanation_language_state"] == "DEFAULT_PREFERENCE"
    assert back_to_telugu["correction_explanation"] == telugu["correction_explanation_default"]
    assert back_to_telugu["next_question"] not in back_to_telugu["spoken_text"]

    persistent = client.post(
        route,
        json={"message": "From now on explain everything in English."},
        headers={"Idempotency-Key": "policy-english-persistent"},
    ).json()
    assert persistent["explanation_language_state"] == "PERSISTENT_PREFERENCE_CHANGE"
    assert persistent["explanation_language"] == "ENGLISH"
    preference = client.get("/api/v1/tutors/preference").json()
    assert preference["language_mode"] == "ENGLISH"

    later = client.post(
        route,
        json={"message": "She don't like coffee."},
        headers={"Idempotency-Key": "policy-stays-english"},
    ).json()
    assert later["explanation_language"] == "ENGLISH"
    assert later["explanation_language_state"] == "DEFAULT_PREFERENCE"


@pytest.mark.parametrize(("learner_sentence", "corrected", "explanation"), [
    (
        "I am working here since five years.",
        "I have been working here for five years.",
        "Duration చెప్పేటప్పుడు 'since five years' కాకుండా 'for five years' వాడాలి. Action ఇప్పటికీ continue అవుతోంది కాబట్టి 'have been working' natural.",
    ),
    (
        "She don't like coffee.",
        "She doesn't like coffee.",
        "'She' third-person singular కాబట్టి 'don't' బదులు 'doesn't' వాడాలి.",
    ),
    (
        "Yesterday I go to office.",
        "Yesterday I went to the office.",
        "'Yesterday' past time చూపిస్తోంది కాబట్టి 'go' బదులు past tense 'went' వాడాలి.",
    ),
    (
        "I didn't went there.",
        "I didn't go there.",
        "'didn't' లోనే past tense ఉంది కాబట్టి main verb base form 'go' లో ఉండాలి; 'went' కాదు.",
    ),
])
def test_founder_mistakes_use_native_telugu_evidence_and_require_retry(
    learner_sentence, corrected, explanation,
):
    outcome = build_coaching_outcome(
        _response(
            corrected_learner_sentence=corrected,
            correction_explanation=explanation,
            grammar_feedback=["meaningful grammar correction"],
        ),
        learner_level="BEGINNER",
        language_mode=LanguageMode.ENGLISH_TELUGU,
        learner_text=learner_sentence,
    )
    assert explanation in outcome.spoken_text
    assert corrected in outcome.spoken_text
    assert "ఒకసారి చెప్పండి" in outcome.spoken_text
    assert outcome.state == CoachingState.WAITING_FOR_RETRY
    assert outcome.response.conversation_question not in outcome.spoken_text
