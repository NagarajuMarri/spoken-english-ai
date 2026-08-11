import json


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
