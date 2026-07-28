from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.db.base import Base
from backend.app.models import AudioAsset, ConsentRecord, Learner, UserAccount, VoiceSession, VoiceTurn
from backend.app.providers.pronunciation.deterministic import DeterministicPronunciationProvider
from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.voice.orchestration import VoiceTutorOrchestrationService


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = UserAccount(email="voice-demo@example.invalid", password_hash="not-a-real-password-hash")
        session.add(user)
        session.flush()
        learner = Learner(user_account_id=user.id, email=user.email, display_name="Voice Demo")
        session.add(learner)
        session.flush()
        session.add(ConsentRecord(
            learner_id=learner.id, voice_processing_consent=True,
            audio_storage_consent=False, consent_version="example-v1",
        ))
        voice_session = VoiceSession(learner_id=learner.id, scenario_id="daily-routine")
        session.add(voice_session)
        session.flush()
        asset = AudioAsset(
            learner_id=learner.id, voice_session_id=voice_session.id,
            media_type="audio/wav", storage_key="examples/input.wav", status="TEMPORARY",
        )
        session.add(asset)
        session.flush()
        turn = VoiceTurn(
            voice_session_id=voice_session.id, turn_number=1, audio_asset_id=asset.id,
            transcript="pending", tutor_text="pending", synthetic_audio_reference="pending",
        )
        session.add(turn)
        session.commit()
        result = VoiceTutorOrchestrationService(
            session,
            stt=DeterministicSpeechToTextProvider(),
            ai=DeterministicAIProvider(),
            pronunciation=DeterministicPronunciationProvider(),
            tts=DeterministicTextToSpeechProvider(),
        ).process(
            turn_id=turn.id, learner=learner, user=user,
            idempotency_key="example-stable-key", correlation_id="example-voice",
        )
        print(result.model_dump_json(indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
