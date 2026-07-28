from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import AudioAsset, ConsentRecord, VoiceSession, VoiceTurn


class VoiceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_consent(self, learner_id):
        return self.session.scalar(
            select(ConsentRecord).where(ConsentRecord.learner_id == learner_id)
            .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc()).limit(1)
        )

    def record_consent(self, **values):
        record = ConsentRecord(**values)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def withdraw(self, learner_id, consent_version):
        now = datetime.now(timezone.utc)
        record = self.record_consent(
            learner_id=learner_id, voice_processing_consent=False,
            audio_storage_consent=False, consent_version=consent_version,
            consent_withdrawn_at=now,
        )
        assets = list(self.session.scalars(select(AudioAsset).where(
            AudioAsset.learner_id == learner_id,
            AudioAsset.status.in_(["TEMPORARY", "RETAINED"]),
        )))
        for asset in assets:
            asset.status = "PENDING_DELETION"
        self.session.commit()
        return record

    def create_session(self, learner_id, scenario_id):
        item = VoiceSession(learner_id=learner_id, scenario_id=scenario_id)
        self.session.add(item)
        self.session.commit()
        return self.get_session(item.id)

    def get_session(self, session_id):
        return self.session.scalar(select(VoiceSession).options(
            selectinload(VoiceSession.turns), selectinload(VoiceSession.assets)
        ).where(VoiceSession.id == session_id))

    def add_turn(self, voice_session, asset, transcript, tutor_turn):
        turn_number = len(voice_session.turns) + 1
        self.session.add(asset)
        self.session.flush()
        turn = VoiceTurn(
            voice_session_id=voice_session.id, turn_number=turn_number,
            audio_asset_id=asset.id, transcript=transcript,
            tutor_text=tutor_turn.response, correction_summary=tutor_turn.correction,
            synthetic_audio_reference=f"fake-tts://{voice_session.id}/{turn_number}",
        )
        voice_session.status = "IN_PROGRESS"
        self.session.add(turn)
        self.session.commit()
        self.session.refresh(turn)
        return turn

    def complete(self, item):
        if item.status != "COMPLETED":
            item.status = "COMPLETED"
            item.completed_at = datetime.now(timezone.utc)
            self.session.commit()
        return self.get_session(item.id)

    def cleanup(self, now):
        assets = list(self.session.scalars(select(AudioAsset).where(
            (AudioAsset.status == "PENDING_DELETION")
            | ((AudioAsset.status == "TEMPORARY") & (AudioAsset.expires_at <= now))
        )))
        for asset in assets:
            asset.status = "DELETED"
            asset.deleted_at = now
        self.session.commit()
        return len(assets)
