import json
from sqlalchemy import select

from backend.app.models import ConversationMessage, RealtimeTurn


class _RealtimeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _limit):
        return b"v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n"


def test_realtime_call_proxies_sdp_without_exposing_standard_key(client, learner, conversation, monkeypatch):
    settings = client.app.state.settings
    settings.realtime_voice_enabled = True
    settings.openai_api_key = "sk-standard-secret-never-return"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _RealtimeResponse()

    monkeypatch.setattr("backend.app.api.routes.realtime.urllib.request.urlopen", fake_urlopen)
    response = client.post(
        f"/api/v1/realtime/calls?conversation_id={conversation['id']}&language_mode=ENGLISH_TELUGU&lesson_id=lesson-01",
        content=b"v=0\r\no=- 7 7 IN IP4 127.0.0.1\r\n",
        headers={"Content-Type": "application/sdp"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/sdp")
    assert response.headers["cache-control"] == "no-store"
    assert response.text.startswith("v=0")
    assert "sk-standard-secret" not in response.text
    outgoing = captured["request"]
    assert outgoing.full_url == "https://api.openai.com/v1/realtime/calls"
    assert outgoing.headers["Authorization"] == "Bearer sk-standard-secret-never-return"
    assert len(outgoing.headers["Openai-safety-identifier"]) == 64
    payload = outgoing.data.decode()
    assert '"type":"server_vad"' in payload
    assert '"silence_duration_ms":500' in payload
    assert '"interrupt_response":true' in payload
    assert "lesson-01" in payload
    assert "natural Telugu help" in payload
    assert "sk-standard-secret-never-return" not in payload


def test_realtime_call_fails_closed_without_provider_configuration(client, conversation):
    response = client.post(
        f"/api/v1/realtime/calls?conversation_id={conversation['id']}",
        content=b"v=0\r\no=- 7 7 IN IP4 127.0.0.1\r\n",
        headers={"Content-Type": "application/sdp"},
    )
    assert response.status_code == 503
    body = json.dumps(response.json())
    assert "OpenAI" not in body
    assert "realtime_unavailable" in body


def test_realtime_call_requires_authentication(client):
    client.headers.pop("Authorization", None)
    response = client.post(
        "/api/v1/realtime/calls?conversation_id=unknown",
        content=b"v=0\r\n",
        headers={"Content-Type": "application/sdp"},
    )
    assert response.status_code == 401


def test_realtime_capability_exposes_only_availability(client, learner):
    assert client.get("/api/v1/realtime/capability").json() == {"enabled": False}
    client.app.state.settings.realtime_voice_enabled = True
    client.app.state.settings.openai_api_key = "sk-never-expose-this"
    response = client.get("/api/v1/realtime/capability")
    assert response.json() == {"enabled": True}
    assert "sk-never" not in response.text


def test_realtime_transcripts_are_exactly_once_and_feed_conversation_history(client, conversation):
    endpoint = f"/api/v1/realtime/events?conversation_id={conversation['id']}"
    learner_event = {
        "event_type": "learner_transcript",
        "learner_item_id": "item-1",
        "transcript": "I goes to work every day.",
    }
    first = client.post(endpoint, json=learner_event)
    duplicate = client.post(endpoint, json=learner_event)
    assert first.status_code == duplicate.status_code == 202

    tutor_event = {
        "event_type": "tutor_transcript",
        "learner_item_id": "item-1",
        "response_id": "response-1",
        "transcript": "Say: I go to work every day.",
    }
    assert client.post(endpoint, json=tutor_event).status_code == 202
    assert client.post(endpoint, json=tutor_event).status_code == 202

    with client.app.state.session_factory() as db:
        turns = list(db.scalars(select(RealtimeTurn)))
        messages = list(db.scalars(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation["id"]
        )))
    assert len(turns) == 1
    assert turns[0].analysis_status == "COMPLETED"
    assert turns[0].tutor_status == "COMPLETED"
    assert len(messages) == 1
    assert messages[0].learner_text == learner_event["transcript"]


def test_interrupted_realtime_output_is_not_counted_even_if_stale_done_arrives(client, conversation):
    endpoint = f"/api/v1/realtime/events?conversation_id={conversation['id']}"
    assert client.post(endpoint, json={
        "event_type": "learner_transcript", "learner_item_id": "item-2", "transcript": "Please help me."
    }).status_code == 202
    assert client.post(endpoint, json={
        "event_type": "tutor_interrupted", "learner_item_id": "item-2", "response_id": "response-2"
    }).status_code == 202
    assert client.post(endpoint, json={
        "event_type": "tutor_transcript", "learner_item_id": "item-2", "response_id": "response-2", "transcript": "Stale partial answer."
    }).status_code == 202
    with client.app.state.session_factory() as db:
        turn = db.scalar(select(RealtimeTurn).where(RealtimeTurn.learner_item_id == "item-2"))
        count = len(list(db.scalars(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation["id"]
        ))))
    assert turn is not None and turn.tutor_status == "INTERRUPTED"
    assert count == 0
