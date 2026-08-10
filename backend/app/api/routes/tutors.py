from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.core.security import Principal, current_principal
from backend.app.db.session import get_db
from backend.app.schemas.tutors import (
    LearnerDashboardRead, TutorPreferenceRead, TutorPreferenceUpdate, TutorRead,
)
from backend.app.services.tutors import TutorExperienceService
from backend.app.domain.enums import LanguageMode

router = APIRouter(prefix="/api/v1/tutors", tags=["tutors"])


@router.get("", response_model=list[TutorRead])
def list_tutors():
    return TutorExperienceService.catalogue()


@router.get("/preference", response_model=TutorPreferenceRead)
def get_preference(principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    return TutorExperienceService(session).preference(principal.learner)


@router.put("/preference", response_model=TutorPreferenceRead)
def update_preference(data: TutorPreferenceUpdate, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    return TutorExperienceService(session).update_preference(
        principal.learner, data.tutor_id, data.language_mode or LanguageMode.ENGLISH
    )


@router.get("/dashboard", response_model=LearnerDashboardRead)
def dashboard(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    subscription = RuntimeEntitlementService(
        session,
        request.app.state.commercial_service.config,
    ).view(principal.learner.id, payment_mode=request.app.state.settings.razorpay_mode)
    return TutorExperienceService(session).dashboard(
        principal.learner,
        subscription_tier=subscription["plan_id"],
        subscription_status=subscription["status"],
    )
