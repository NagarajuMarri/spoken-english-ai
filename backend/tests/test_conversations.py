import pytest
from sqlalchemy import func, select

from backend.app.models import (
    AIUsageRecord,
    AITurnAttempt,
    Conversation,
    ConversationMessage,
    ProgressRecord,
    ProviderCallEvent,
    TTSSynthesisAttempt,
)
from backend.app.repositories.ai_turns import AITurnAttemptRepository
from backend.app.services.conversations import ConversationService
from backend.app.domain.tutor import TutorTurn
from backend.app.integrations.llm import RuleBasedLLMProvider


def test_scenario_listing(client):
    response = client.get("/api/v1/scenarios")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "Daily Conversation",
        "Workplace English",
        "Job Interview",
        "Travel",
        "Shopping",
        "Doctor Visit",
        "Telephone Conversation",
        "Free Talk",
    ]


def test_conversation_creation(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "travel"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scenario_id"] == "travel"
    assert body["messages"] == []
    assert body["opening_prompt"] == "Where would you like to travel, and why?"
    assert body["opening_turn_id"]


def test_conversation_creation_persists_one_opening_without_transcript_or_progress(
    client, learner
):
    created = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "travel"},
    )
    assert created.status_code == 201
    body = created.json()

    retrieved = client.get(f"/api/v1/conversations/{body['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["opening_prompt"] == body["opening_prompt"]
    assert retrieved.json()["opening_turn_id"] == body["opening_turn_id"]
    assert retrieved.json()["messages"] == []

    with client.app.state.session_factory() as session:
        openings = list(session.scalars(select(AITurnAttempt).where(
            AITurnAttempt.conversation_id == body["id"]
        )))
        assert len(openings) == 1
        opening = openings[0]
        assert opening.id == body["opening_turn_id"]
        assert opening.turn_kind == "OPENING"
        assert opening.status == "COMPLETED"
        assert opening.learner_text == ""
        assert opening.provider_attempts == 0
        assert opening.result_json["api_result"]["turn_id"] == opening.id
        assert opening.result_json["api_result"]["spoken_text"] == (
            "Where would you like to travel, and why?"
        )
        assert AITurnAttemptRepository(session).latest_completed(body["id"]) is None
        assert session.scalar(select(func.count()).select_from(ConversationMessage).where(
            ConversationMessage.conversation_id == body["id"]
        )) == 0
        assert session.scalar(select(func.count()).select_from(ProgressRecord).where(
            ProgressRecord.conversation_id == body["id"]
        )) == 0


def test_legacy_conversation_without_opening_identity_remains_readable(client, learner):
    with client.app.state.session_factory() as session:
        legacy = Conversation(learner_id=learner["id"], scenario_id="travel")
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id

    response = client.get(f"/api/v1/conversations/{legacy_id}")

    assert response.status_code == 200
    assert response.json()["opening_prompt"] == "Where would you like to travel, and why?"
    assert response.json()["opening_turn_id"] is None
    assert response.json()["messages"] == []


def test_conversation_and_opening_identity_are_created_atomically(
    client, learner, monkeypatch
):
    def fail_opening(*_args, **_kwargs):
        raise RuntimeError("simulated opening persistence failure")

    monkeypatch.setattr(AITurnAttemptRepository, "create_opening", fail_opening)
    with client.app.state.session_factory() as session:
        with pytest.raises(RuntimeError, match="simulated opening persistence failure"):
            ConversationService(session).create(learner["id"], "travel")
        assert session.scalar(select(func.count()).select_from(Conversation)) == 0
        assert session.scalar(select(func.count()).select_from(AITurnAttempt)) == 0


def test_opening_speech_preserves_ownership_cache_and_metering(client, learner):
    created = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "daily-conversation"},
    ).json()
    route = (
        f"/api/v1/conversations/{created['id']}"
        f"/ai-turns/{created['opening_turn_id']}/speech"
    )
    owner_authorization = client.headers["Authorization"]
    attacker = client.post("/api/v1/auth/register", json={
        "email": "opening-attacker@example.com",
        "password": "StrongPassword123!",
        "display_name": "Opening Attacker",
        "terms_privacy_accepted": True,
    }).json()
    client.headers["Authorization"] = f"Bearer {attacker['tokens']['access_token']}"

    denied = client.post(route)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "resource_not_found"
    assert client.app.state.text_to_speech_provider.calls == 0

    client.headers["Authorization"] = owner_authorization
    first = client.post(route)
    replay = client.post(route)
    assert first.status_code == replay.status_code == 200
    assert first.content == replay.content
    assert first.headers["x-tts-cache"] == "MISS"
    assert replay.headers["x-tts-cache"] == "HIT"
    assert client.app.state.text_to_speech_provider.calls == 1

    with client.app.state.session_factory() as session:
        syntheses = list(session.scalars(select(TTSSynthesisAttempt).where(
            TTSSynthesisAttempt.ai_turn_attempt_id == created["opening_turn_id"]
        )))
        assert len(syntheses) == 1
        assert session.scalar(select(func.count()).select_from(ProviderCallEvent).where(
            ProviderCallEvent.operation_kind == "tts",
            ProviderCallEvent.attempt_reference == syntheses[0].id,
        )) == 1
        assert session.scalar(select(func.count()).select_from(AIUsageRecord).where(
            AIUsageRecord.provider_kind == "tts",
            AIUsageRecord.voice_session_id == created["id"],
        )) == 1


def test_conversation_creation_rejects_missing_learner(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": "missing", "scenario_id": "travel"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_conversation_creation_rejects_invalid_scenario(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "unknown"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "scenario_not_found"


def test_deterministic_message_and_correction(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "I am go to office yesterday."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["turn_number"] == 1
    assert body["tutor_response"] == "I see. What did you do at the office?"
    assert body["correction_summary"] == 'You can say: “I went to the office yesterday.”'
    assert body["transcript_entry"]["learner_text"] == "I am go to office yesterday."


def test_normal_message_continues_without_forced_correction(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "I enjoy reading books."},
    )

    assert response.status_code == 200
    assert response.json()["correction_summary"] is None
    assert response.json()["tutor_response"].startswith("Thanks")


def test_telugu_explanation_flag(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "I am go to office yesterday.",
            "include_telugu_explanation": True,
        },
    )

    assert response.status_code == 200
    assert "తెలుగు:" in response.json()["correction_summary"]


def test_empty_message_is_structured_error(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_message"


@pytest.mark.parametrize("unsafe", ["a\u1037", "Wait.\u0301", "Это русский текст"])
def test_legacy_message_rejects_unsafe_input_before_persistence(
    client, conversation, unsafe,
):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": unsafe},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_learner_message"
    assert unsafe not in response.text
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert session.scalar(select(func.count()).select_from(ProgressRecord)) == 0


def test_legacy_message_normalizes_nfc_before_provider_and_persistence(
    client, conversation,
):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Cafe\u0301 is useful."},
    )

    assert response.status_code == 200
    assert response.json()["transcript_entry"]["learner_text"] == "Café is useful."
    with client.app.state.session_factory() as session:
        message = session.scalar(select(ConversationMessage))
        assert message.learner_text == "Café is useful."


def test_legacy_message_rejects_unsafe_tutor_output_before_persistence(
    client, conversation, monkeypatch,
):
    monkeypatch.setattr(
        RuleBasedLLMProvider,
        "generate_tutor_response",
        lambda *_args, **_kwargs: TutorTurn(response="a\u1037"),
    )

    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Please help me practise."},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_tutor_output"
    assert "a\u1037" not in response.text
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 0
        assert session.scalar(select(func.count()).select_from(ProgressRecord)) == 0


def test_conversation_get_quarantines_unsafe_legacy_output(client, conversation):
    with client.app.state.session_factory() as session:
        session.add(ConversationMessage(
            conversation_id=conversation["id"],
            turn_number=1,
            learner_text="Safe learner text.",
            tutor_response="a\u1037",
            correction_summary=None,
        ))
        session.commit()

    response = client.get(f"/api/v1/conversations/{conversation['id']}")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "conversation_output_invalid"
    assert "a\u1037" not in response.text


def test_missing_conversation(client, learner):
    response = client.get("/api/v1/conversations/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_transcript_retrieval_preserves_turns(client, conversation):
    for text in ["Hello there.", "I am go to office yesterday."]:
        response = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"text": text},
        )
        assert response.status_code == 200

    response = client.get(f"/api/v1/conversations/{conversation['id']}")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["turn_number"] for item in messages] == [1, 2]
    assert [item["learner_text"] for item in messages] == [
        "Hello there.",
        "I am go to office yesterday.",
    ]
