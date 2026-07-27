from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.learners import LearnerCreate, LearnerRead, OnboardingUpdate
from backend.app.services.learners import LearnerService

router = APIRouter(prefix="/api/v1/learners", tags=["learners"])


@router.post("", response_model=LearnerRead, status_code=status.HTTP_201_CREATED)
def create_learner(data: LearnerCreate, session: Session = Depends(get_db)):
    return LearnerService(session).create(data)


@router.get("/{learner_id}", response_model=LearnerRead)
def get_learner(learner_id: str, session: Session = Depends(get_db)):
    return LearnerService(session).get(learner_id)


@router.patch("/{learner_id}/onboarding", response_model=LearnerRead)
def update_onboarding(
    learner_id: str, data: OnboardingUpdate, session: Session = Depends(get_db)
):
    return LearnerService(session).update_onboarding(learner_id, data)
