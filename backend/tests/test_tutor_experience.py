from datetime import date, timedelta
import re

from sqlalchemy.orm import Session

from backend.app.models import ProgressRecord
from backend.app.tutors import TUTORS


def test_public_tutor_catalog_is_configuration_driven(client):
    response = client.get("/api/v1/tutors")
    assert response.status_code == 200
    assert [item["tutor_id"] for item in response.json()] == ["ananya", "arjun"]
    assert all(item["accent"] == "Indian English" for item in response.json())
    assert {item.gender for item in TUTORS} == {"female", "male"}
    assert all(item.enabled for item in TUTORS)


def test_learner_selects_and_changes_tutor(client, learner):
    initial = client.get("/api/v1/tutors/preference")
    assert initial.status_code == 200
    assert initial.json()["tutor"]["tutor_id"] == "ananya"

    updated = client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "arjun", "telugu_explanations_enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json()["tutor"]["voice_profile"] == "indian-english-male-confident"
    assert updated.json()["telugu_explanations_enabled"] is True
    assert client.get("/api/v1/tutors/preference").json() == updated.json()


def test_unknown_or_disabled_tutor_is_rejected(client, learner):
    response = client.put(
        "/api/v1/tutors/preference",
        json={"tutor_id": "unknown", "telugu_explanations_enabled": False},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_tutor"


def test_tutor_preference_requires_authentication(client):
    assert client.get("/api/v1/tutors/preference").status_code == 401
    assert client.get("/api/v1/tutors/dashboard").status_code == 401


def test_dashboard_reports_progress_streak_and_subscription_boundary(client, learner):
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        session: Session
        today = date.today()
        session.add_all([
            ProgressRecord(learner_id=learner["id"], practice_date=today, duration_seconds=600),
            ProgressRecord(learner_id=learner["id"], practice_date=today - timedelta(days=1), duration_seconds=300),
        ])
        session.commit()
    dashboard = client.get("/api/v1/tutors/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json() == {
        "learner_id": learner["id"],
        "completed_sessions": 2,
        "current_streak_days": 2,
        "total_practice_minutes": 15,
        "preferred_tutor_id": "ananya",
        "subscription_tier": "FREE",
        "subscription_status": "READY_FOR_PROVIDER_INTEGRATION",
    }


def test_onboarding_persists_tutor_and_optional_telugu(client, learner):
    response = client.patch(
        f"/api/v1/learners/{learner['id']}/onboarding",
        json={
            "proficiency_level": "BEGINNER",
            "learning_goal": "GENERAL_FLUENCY",
            "daily_goal_minutes": 15,
            "native_language": "Telugu",
            "preferred_tutor_id": "arjun",
            "telugu_explanations_enabled": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["preferred_tutor_id"] == "arjun"
    assert response.json()["telugu_explanations_enabled"] is True


def test_learner_frontend_and_tutor_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "SpeakMate" in page.text
    assert client.get("/tutors/ananya.jpg").status_code == 200
    assert client.get("/tutors/arjun.jpg").status_code == 200
    script = re.search(r'src="([^"]+\.js)"', page.text)
    assert script is not None
    javascript = client.get(script.group(1))
    assert "Your English" in javascript.text
    assert "SpeechRecognition" in javascript.text
    assert "speechSynthesis" in javascript.text
