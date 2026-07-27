from datetime import date, timedelta

from backend.app.domain.curriculum import LESSONS
from backend.app.domain.evaluation import evaluate
from backend.app.integrations.llm import RuleBasedLLMProvider
from backend.app.integrations.speech_to_text import FakeSpeechToTextProvider
from backend.app.integrations.text_to_speech import FakeTextToSpeechProvider
from backend.app.models import ProgressRecord
from backend.app.services.learning import LearningService


def test_curriculum_levels_and_filtering(client):
    levels = client.get("/api/v1/curriculum/levels")
    lessons = client.get("/api/v1/curriculum/lessons?proficiency_level=STARTER")
    assert levels.status_code == 200
    assert len(levels.json()) == 5
    assert lessons.status_code == 200
    assert len(lessons.json()) == 2
    assert {item["proficiency_level"] for item in lessons.json()} == {"STARTER"}


def test_lesson_retrieval(client):
    response = client.get("/api/v1/curriculum/lessons/starter-introductions")
    assert response.status_code == 200
    assert response.json()["completion_criteria"]


def test_daily_lesson_is_deterministic_and_matches_level(client, learner):
    first = client.get(f"/api/v1/learners/{learner['id']}/daily-lesson")
    second = client.get(f"/api/v1/learners/{learner['id']}/daily-lesson")
    assert first.json() == second.json()
    assert first.json()["proficiency_level"] == "STARTER"


def test_lesson_session_creation_and_completion(client, learner, conversation):
    created = client.post("/api/v1/lesson-sessions", json={
        "learner_id": learner["id"],
        "lesson_id": "starter-introductions",
        "conversation_id": conversation["id"],
    })
    assert created.status_code == 201
    assert created.json()["status"] == "STARTED"

    completed = client.post(
        f"/api/v1/lesson-sessions/{created.json()['id']}/complete",
        json={"duration_seconds": 600},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "COMPLETED"
    assert body["evaluation"] is not None
    assert all(0 <= body["evaluation"][key] <= 100 for key in (
        "grammar_score", "vocabulary_score", "fluency_score",
        "task_completion_score", "confidence_score", "overall_score",
    ))


def test_deterministic_evaluation():
    class Message:
        learner_text = "I enjoy reading useful English books."
        correction_summary = None

    assert evaluate([Message()]) == evaluate([Message()])
    assert "pronunciation" not in evaluate([Message()]).__dict__
    assert isinstance(evaluate([Message()]).strengths, tuple)


def test_curriculum_ids_are_unique():
    ids = [lesson.id for lesson in LESSONS]
    assert len(ids) == len(set(ids))


def test_progress_and_same_day_streak(client, learner):
    for lesson_id in ("starter-introductions", "starter-shopping"):
        session = client.post("/api/v1/lesson-sessions", json={
            "learner_id": learner["id"], "lesson_id": lesson_id
        }).json()
        assert client.post(
            f"/api/v1/lesson-sessions/{session['id']}/complete",
            json={"duration_seconds": 300},
        ).status_code == 200

    progress = client.get(f"/api/v1/learners/{learner['id']}/progress").json()
    streak = client.get(f"/api/v1/learners/{learner['id']}/streak").json()
    assert progress["completed_lessons"] == 2
    assert progress["total_practice_minutes"] == 10
    assert streak["current_streak"] == 1
    assert streak["longest_streak"] == 1
    assert streak["timezone"] == "UTC"


def test_completion_is_idempotent_and_progress_not_double_counted(client, learner):
    created = client.post("/api/v1/lesson-sessions", json={
        "learner_id": learner["id"], "lesson_id": "starter-introductions"
    }).json()
    endpoint = f"/api/v1/lesson-sessions/{created['id']}/complete"
    first = client.post(endpoint, json={"duration_seconds": 300})
    second = client.post(endpoint, json={"duration_seconds": 900})
    assert first.status_code == second.status_code == 200
    assert second.json()["duration_seconds"] == 300
    progress = client.get(f"/api/v1/learners/{learner['id']}/progress").json()
    assert progress["completed_lessons"] == 1
    assert progress["total_practice_minutes"] == 5


def test_streak_increment_reset_and_longest(client, learner):
    with client.app.state.session_factory() as db:
        for day in (date.today() - timedelta(days=4), date.today() - timedelta(days=3), date.today()):
            db.add(ProgressRecord(
                learner_id=learner["id"], lesson_id="starter-introductions",
                practice_date=day, duration_seconds=60, score=70,
                scenario_id="daily-conversation", proficiency_level="STARTER",
            ))
        db.commit()
    streak = client.get(f"/api/v1/learners/{learner['id']}/streak").json()
    assert streak["current_streak"] == 1
    assert streak["longest_streak"] == 2


def test_provider_interfaces_and_local_doubles():
    llm = RuleBasedLLMProvider()
    assert llm.generate_tutor_response("Hello.").response
    assert FakeSpeechToTextProvider("hello").transcribe(b"bytes") == "hello"
    assert FakeTextToSpeechProvider().synthesize("hello") == b"FAKE_AUDIO:hello"


def test_unique_turn_sequence(client, conversation):
    for index in range(5):
        response = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"text": f"Message {index}"},
        )
        assert response.status_code == 200
        assert response.json()["turn_number"] == index + 1


def test_invalid_completion_rolls_back(client, learner):
    created = client.post("/api/v1/lesson-sessions", json={
        "learner_id": learner["id"], "lesson_id": "starter-introductions"
    }).json()
    rejected = client.post(
        f"/api/v1/lesson-sessions/{created['id']}/complete",
        json={"duration_seconds": -1},
    )
    assert rejected.status_code == 422
    current = client.get(f"/api/v1/lesson-sessions/{created['id']}").json()
    assert current["status"] == "STARTED"
    assert current["evaluation"] is None
