from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.app.models import AudioAsset, ConsentRecord
from backend.app.services.voice import VoiceService


def set_consent(client, learner, processing=True, storage=False):
    return client.put(f"/api/v1/learners/{learner['id']}/voice-consent", json={
        "voice_processing_consent": processing,
        "audio_storage_consent": storage,
        "consent_version": "2026-07-v1",
    })


def create_voice_session(client, learner):
    return client.post("/api/v1/voice-sessions", json={
        "learner_id": learner["id"], "scenario_id": "daily-conversation"
    })


def add_turn(client, session_id, key="simulated/audio-1.wav", transcript="I am go to office yesterday."):
    return client.post(f"/api/v1/voice-sessions/{session_id}/turns", json={
        "simulated_audio_reference": key,
        "fake_transcript": transcript,
        "media_type": "audio/wav",
    })


def test_consent_creation_update_and_audit(client, learner):
    initial = client.get(f"/api/v1/learners/{learner['id']}/voice-consent")
    assert initial.json()["active"] is False
    assert set_consent(client, learner).json()["active"] is True
    updated = set_consent(client, learner, processing=True, storage=True)
    assert updated.json()["audio_storage_consent"] is True
    with client.app.state.session_factory() as db:
        count = db.scalar(select(func.count(ConsentRecord.id)))
    assert count == 2


def test_storage_consent_is_independent(client, learner):
    response = set_consent(client, learner, processing=True, storage=False)
    assert response.status_code == 200
    assert response.json()["voice_processing_consent"] is True
    assert response.json()["audio_storage_consent"] is False


def test_processing_without_consent_is_privacy_error(client, learner):
    response = create_voice_session(client, learner)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "voice_consent_required"


def test_voice_session_fake_turn_and_transcript_persistence(client, learner):
    set_consent(client, learner)
    session = create_voice_session(client, learner)
    assert session.status_code == 201
    turn = add_turn(client, session.json()["id"])
    assert turn.status_code == 200
    body = turn.json()
    assert body["transcript"] == "I am go to office yesterday."
    assert body["tutor_text"] == "I see. What did you do at the office?"
    assert body["correction_summary"]
    assert body["synthetic_audio_reference"].startswith("fake-tts://")
    assert body["turn_number"] == 1
    retrieved = client.get(f"/api/v1/voice-sessions/{session.json()['id']}").json()
    assert retrieved["turns"][0]["transcript"] == body["transcript"]
    assert retrieved["audio_assets"][0]["status"] == "TEMPORARY"
    assert retrieved["audio_assets"][0]["expires_at"] is not None


def test_voice_turn_sequence_and_completion(client, learner):
    set_consent(client, learner)
    session_id = create_voice_session(client, learner).json()["id"]
    assert add_turn(client, session_id, "simulated/one.wav", "Hello.").json()["turn_number"] == 1
    assert add_turn(client, session_id, "simulated/two.wav", "How are you?").json()["turn_number"] == 2
    completed = client.post(f"/api/v1/voice-sessions/{session_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    rejected = add_turn(client, session_id, "simulated/three.wav")
    assert rejected.status_code == 409


def test_synthetic_pronunciation_boundary(client, learner):
    set_consent(client, learner)
    session_id = create_voice_session(client, learner).json()["id"]
    assessment = add_turn(client, session_id).json()["pronunciation_assessment"]
    assert assessment["assessment_type"] == "synthetic_test_double"
    assert "not a real" in assessment["note"]


def test_retained_asset_and_withdrawal_marks_deletion(client, learner):
    set_consent(client, learner, storage=True)
    session_id = create_voice_session(client, learner).json()["id"]
    add_turn(client, session_id)
    assert client.get(f"/api/v1/voice-sessions/{session_id}").json()["audio_assets"][0]["status"] == "RETAINED"
    withdrawn = client.delete(f"/api/v1/learners/{learner['id']}/voice-consent")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["active"] is False
    assert client.get(f"/api/v1/voice-sessions/{session_id}").json()["audio_assets"][0]["status"] == "PENDING_DELETION"
    assert create_voice_session(client, learner).status_code == 403


def test_cleanup_service_deletes_expired_and_pending(client, learner):
    set_consent(client, learner)
    session_id = create_voice_session(client, learner).json()["id"]
    add_turn(client, session_id)
    with client.app.state.session_factory() as db:
        asset = db.scalar(select(AudioAsset))
        asset.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        assert VoiceService(db).cleanup(datetime.now(timezone.utc)) == 1
    asset_body = client.get(f"/api/v1/voice-sessions/{session_id}").json()["audio_assets"][0]
    assert asset_body["status"] == "DELETED"
    assert asset_body["deleted_at"] is not None


def test_media_type_and_storage_key_validation(client, learner):
    set_consent(client, learner)
    session_id = create_voice_session(client, learner).json()["id"]
    bad_media = client.post(f"/api/v1/voice-sessions/{session_id}/turns", json={
        "simulated_audio_reference": "safe.wav", "media_type": "application/octet-stream"
    })
    unsafe_key = client.post(f"/api/v1/voice-sessions/{session_id}/turns", json={
        "simulated_audio_reference": "../secret.wav", "media_type": "audio/wav"
    })
    assert bad_media.json()["error"]["code"] == "unsupported_media_type"
    assert unsafe_key.json()["error"]["code"] == "unsafe_storage_key"


def test_daily_plan_consent_flags(client, learner):
    without = client.get(f"/api/v1/learners/{learner['id']}/daily-plan")
    assert without.status_code == 200
    assert without.json()["voice_availability"] is False
    assert without.json()["consent_required"] is True
    assert without.json()["selected_lesson"]["id"]
    set_consent(client, learner)
    with_consent = client.get(f"/api/v1/learners/{learner['id']}/daily-plan").json()
    assert with_consent["voice_availability"] is True
    assert with_consent["consent_required"] is False
