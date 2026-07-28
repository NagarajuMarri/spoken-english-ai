from datetime import datetime, timedelta, timezone
import re

from fastapi import status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.integrations.llm import RuleBasedLLMProvider
from backend.app.integrations.pronunciation import FakePronunciationAssessmentProvider
from backend.app.integrations.speech_to_text import FakeSpeechToTextProvider
from backend.app.integrations.text_to_speech import FakeTextToSpeechProvider
from backend.app.models import AudioAsset
from backend.app.repositories.learners import LearnerRepository
from backend.app.repositories.voice import VoiceRepository

ALLOWED_MEDIA_TYPES = {"audio/wav", "audio/mpeg", "audio/webm"}
SAFE_STORAGE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class VoiceService:
    def __init__(self, session: Session, expiration_hours: int = 24) -> None:
        self.session = session
        self.repository = VoiceRepository(session)
        self.learners = LearnerRepository(session)
        self.expiration_hours = expiration_hours
        self.llm = RuleBasedLLMProvider()
        self.tts = FakeTextToSpeechProvider()
        self.pronunciation = FakePronunciationAssessmentProvider()

    def _learner(self, learner_id):
        learner = self.learners.get(learner_id)
        if learner is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "learner_not_found", "Learner not found.")
        return learner

    def consent(self, learner_id):
        self._learner(learner_id)
        record = self.repository.latest_consent(learner_id)
        if record is None:
            return {
                "voice_processing_consent": False, "audio_storage_consent": False,
                "consent_version": "unaccepted", "consented_at": None,
                "consent_withdrawn_at": None, "active": False,
            }
        return {**record.__dict__, "active": bool(
            record.voice_processing_consent and not record.consent_withdrawn_at
        )}

    def update_consent(self, learner_id, data):
        self._learner(learner_id)
        now = datetime.now(timezone.utc)
        record = self.repository.record_consent(
            learner_id=learner_id,
            voice_processing_consent=data.voice_processing_consent,
            audio_storage_consent=data.audio_storage_consent,
            consent_version=data.consent_version,
            consented_at=now if data.voice_processing_consent else None,
        )
        return {**record.__dict__, "active": data.voice_processing_consent}

    def withdraw(self, learner_id):
        current = self.consent(learner_id)
        if current["consent_withdrawn_at"] is not None:
            return current
        record = self.repository.withdraw(learner_id, current["consent_version"])
        return {**record.__dict__, "active": False}

    def _require_consent(self, learner_id):
        consent = self.consent(learner_id)
        if not consent["active"]:
            raise AppError(status.HTTP_403_FORBIDDEN, "voice_consent_required", "Active voice processing consent is required.")
        return consent

    def create_session(self, learner_id, scenario_id):
        self._require_consent(learner_id)
        if scenario_id not in SCENARIOS_BY_ID:
            raise AppError(status.HTTP_404_NOT_FOUND, "scenario_not_found", "Scenario not found.")
        return self.repository.create_session(learner_id, scenario_id)

    def get_session(self, session_id):
        item = self.repository.get_session(session_id)
        if item is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "voice_session_not_found", "Voice session not found.")
        return item

    def add_turn(self, session_id, data):
        voice_session = self.get_session(session_id)
        consent = self._require_consent(voice_session.learner_id)
        if voice_session.status == "COMPLETED":
            raise AppError(status.HTTP_409_CONFLICT, "voice_session_completed", "Voice session is complete.")
        if data.media_type not in ALLOWED_MEDIA_TYPES:
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported_media_type", "Unsupported audio media type.")
        key = data.simulated_audio_reference
        if (
            not SAFE_STORAGE_KEY.fullmatch(key)
            or ".." in key
            or key.startswith("/")
            or "\\" in key
            or ":" in key
            or "//" in key
        ):
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsafe_storage_key", "Unsafe simulated audio reference.")
        transcript = FakeSpeechToTextProvider(data.fake_transcript or "Local test transcript.").transcribe(b"")
        tutor_turn = self.llm.generate_tutor_response(transcript, data.include_telugu_explanation)
        self.tts.synthesize(tutor_turn.response)
        now = datetime.now(timezone.utc)
        retained = consent["audio_storage_consent"]
        asset = AudioAsset(
            learner_id=voice_session.learner_id, voice_session_id=voice_session.id,
            media_type=data.media_type, storage_key=key,
            status="RETAINED" if retained else "TEMPORARY",
            expires_at=None if retained else now + timedelta(hours=self.expiration_hours),
        )
        turn = self.repository.add_turn(voice_session, asset, transcript, tutor_turn)
        assessment = self.pronunciation.assess(transcript)
        return turn, assessment

    def complete(self, session_id):
        return self.repository.complete(self.get_session(session_id))

    def cleanup(self, now=None):
        return self.repository.cleanup(now or datetime.now(timezone.utc))
