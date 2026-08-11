import pytest
from fastapi.testclient import TestClient
import hashlib

from backend.app.core.config import Settings
from backend.app.main import create_app


class AuthCompatibleTestClient(TestClient):
    """Keep legacy fixtures valid while the production registration API requires mobile."""

    def post(self, url, *args, **kwargs):
        body = kwargs.get("json")
        if url == "/api/v1/auth/register" and isinstance(body, dict) and "mobile_number" not in body:
            body = dict(body)
            suffix = int(hashlib.sha256(str(body.get("email", "test")).encode()).hexdigest()[:8], 16) % 10_000_000_000
            body["mobile_number"] = f"+91{suffix:010d}"[:3] + "9" + f"{suffix:010d}"[1:]
            kwargs["json"] = body
        return super().post(url, *args, **kwargs)


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        environment="test",
        jwt_secret="test-signing-secret-at-least-32-bytes-long",
        auto_create_tables=True,
        closed_beta_enabled=False,
        llm_provider="fake",
        speech_to_text_provider="fake",
        text_to_speech_provider="fake",
        language_review_provider="fake",
        password_reset_delivery_provider="memory",
        password_reset_minimum_response_milliseconds=0,
        _env_file=None,
    )
    app = create_app(settings)
    with AuthCompatibleTestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


@pytest.fixture
def learner(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "learner@example.com",
        "password": "StrongPassword123!",
        "display_name": "Anusha",
        "terms_privacy_accepted": True,
    })
    assert response.status_code == 201
    body = response.json()
    client.headers["Authorization"] = f"Bearer {body['tokens']['access_token']}"
    return client.get(f"/api/v1/learners/{body['learner_id']}").json()


@pytest.fixture
def conversation(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "daily-conversation"},
    )
    assert response.status_code == 201
    return response.json()
