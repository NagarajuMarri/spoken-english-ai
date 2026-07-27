def test_learner_creation(client):
    response = client.post(
        "/api/v1/learners",
        json={"email": "RAVI@EXAMPLE.COM", "display_name": "Ravi"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ravi@example.com"
    assert body["proficiency_level"] == "STARTER"
    assert body["learning_goal"] == "GENERAL_FLUENCY"
    assert body["native_language"] == "Telugu"
    assert body["daily_goal_minutes"] == 10


def test_duplicate_email_prevention(client, learner):
    response = client.post(
        "/api/v1/learners",
        json={"email": learner["email"].upper(), "display_name": "Duplicate"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_email"


def test_learner_retrieval(client, learner):
    response = client.get(f"/api/v1/learners/{learner['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == learner["id"]


def test_missing_learner(client):
    response = client.get("/api/v1/learners/not-a-real-id")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "learner_not_found"


def test_onboarding_update(client, learner):
    response = client.patch(
        f"/api/v1/learners/{learner['id']}/onboarding",
        json={
            "proficiency_level": "PRE_INTERMEDIATE",
            "learning_goal": "JOB_INTERVIEW",
            "daily_goal_minutes": 25,
            "native_language": "English",
        },
    )

    assert response.status_code == 200
    assert response.json()["proficiency_level"] == "PRE_INTERMEDIATE"
    assert response.json()["learning_goal"] == "JOB_INTERVIEW"
    assert response.json()["daily_goal_minutes"] == 25
    assert response.json()["native_language"] == "English"


def test_invalid_onboarding_values_are_structured(client, learner):
    cases = [
        ("proficiency_level", "ADVANCED", "invalid_proficiency_level"),
        ("learning_goal", "ACADEMIC", "invalid_learning_goal"),
        ("daily_goal_minutes", 0, "invalid_daily_goal"),
        ("native_language", "Hindi", "unsupported_native_language"),
    ]
    valid = {
        "proficiency_level": "BEGINNER",
        "learning_goal": "TRAVEL",
        "daily_goal_minutes": 15,
        "native_language": "Telugu",
    }
    for field, value, expected_code in cases:
        response = client.patch(
            f"/api/v1/learners/{learner['id']}/onboarding",
            json={**valid, field: value},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == expected_code


def test_learner_persists_across_clients(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.core.config import Settings
    from backend.app.main import create_app

    url = f"sqlite:///{(tmp_path / 'persistent.db').as_posix()}"
    first_app = create_app(Settings(database_url=url, _env_file=None))
    with TestClient(first_app) as first:
        learner = first.post(
            "/api/v1/learners",
            json={"email": "persist@example.com", "display_name": "Persistent"},
        ).json()
    first_app.state.engine.dispose()

    second_app = create_app(Settings(database_url=url, _env_file=None))
    with TestClient(second_app) as second:
        response = second.get(f"/api/v1/learners/{learner['id']}")
    second_app.state.engine.dispose()

    assert response.status_code == 200
    assert response.json()["email"] == "persist@example.com"
