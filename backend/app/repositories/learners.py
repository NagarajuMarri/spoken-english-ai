from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Learner


class DuplicateEmailError(Exception):
    pass


class LearnerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, email: str, display_name: str) -> Learner:
        learner = Learner(email=email.lower(), display_name=display_name.strip())
        self.session.add(learner)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEmailError from exc
        self.session.refresh(learner)
        return learner

    def get(self, learner_id: str) -> Learner | None:
        return self.session.get(Learner, learner_id)

    def update_onboarding(self, learner: Learner, **values: object) -> Learner:
        for field, value in values.items():
            setattr(learner, field, value)
        self.session.commit()
        self.session.refresh(learner)
        return learner
