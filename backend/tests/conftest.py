import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        environment="test",
        jwt_secret="test-signing-secret-at-least-32-bytes-long",
        auto_create_tables=True,
        closed_beta_enabled=False,
        password_reset_delivery_provider="memory",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
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
