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
        auto_create_tables=True,
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


@pytest.fixture
def learner(client):
    response = client.post(
        "/api/v1/learners",
        json={"email": "learner@example.com", "display_name": "Anusha"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def conversation(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "daily-conversation"},
    )
    assert response.status_code == 201
    return response.json()
