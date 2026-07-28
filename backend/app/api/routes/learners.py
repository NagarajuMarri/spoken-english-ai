from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.learners import LearnerCreate, LearnerRead, OnboardingUpdate
from backend.app.services.learners import LearnerService
from backend.app.core.security import Principal, current_principal, require_learner_owner
from backend.app.core.errors import AppError

router = APIRouter(prefix="/api/v1/learners", tags=["learners"])


@router.post("", response_model=LearnerRead, status_code=status.HTTP_201_CREATED)
def create_learner(
    data: LearnerCreate,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    raise AppError(
        status.HTTP_409_CONFLICT,
        "registration_required",
        "Create learner profiles through the registration endpoint.",
    )


@router.get("/{learner_id}", response_model=LearnerRead)
def get_learner(
    learner_id: str,
    _: Principal = Depends(require_learner_owner),
    session: Session = Depends(get_db),
):
    return LearnerService(session).get(learner_id)


@router.patch("/{learner_id}/onboarding", response_model=LearnerRead)
def update_onboarding(
    learner_id: str, data: OnboardingUpdate, session: Session = Depends(get_db)
    , _: Principal = Depends(require_learner_owner)
):
    return LearnerService(session).update_onboarding(learner_id, data)
