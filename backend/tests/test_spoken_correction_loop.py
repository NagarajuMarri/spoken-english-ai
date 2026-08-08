from sqlalchemy import func, select

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.models import AIConversationResponse, AIConversationRequest
from backend.app.coaching import CoachingMode, CoachingState, build_coaching_outcome
from backend.app.domain.enums import LanguageMode
from backend.app.models import AICostMetricEvent, AIUsageRecord, ConversationMessage


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
