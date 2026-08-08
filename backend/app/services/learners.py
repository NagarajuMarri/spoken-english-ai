from fastapi import status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.repositories.learners import DuplicateEmailError, LearnerRepository
from backend.app.schemas.learners import LearnerCreate, OnboardingUpdate
from backend.app.tutors import get_tutor
from backend.app.domain.enums import LanguageMode


class LearnerService:
    def __init__(self, session: Session) -> None:
        self.repository = LearnerRepository(session)

    def create(self, data: LearnerCreate):
        try:
            return self.repository.create(data.email, data.display_name)
        except DuplicateEmailError as exc:
            raise AppError(status.HTTP_409_CONFLICT, "duplicate_email", "A learner with this email exists.") from exc

    def get(self, learner_id: str):
        learner = self.repository.get(learner_id)
        if learner is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "learner_not_found", "Learner not found.")
        return learner

    def update_onboarding(self, learner_id: str, data: OnboardingUpdate):
        try:
            get_tutor(data.preferred_tutor_id)
        except KeyError as error:
            raise AppError(422, "unknown_tutor", "Select an enabled tutor.") from error
        learner = self.get(learner_id)
        values = data.model_dump(mode="json")
        language_mode = data.language_mode or LanguageMode.ENGLISH
        values["telugu_explanations_enabled"] = language_mode != LanguageMode.ENGLISH
        values["language_mode"] = language_mode.value
        return self.repository.update_onboarding(learner, **values)
