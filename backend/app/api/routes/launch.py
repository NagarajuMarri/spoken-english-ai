from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.app.core.security import Principal, current_principal

router = APIRouter(prefix="/api/v1/launch", tags=["launch-readiness"])


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: str = Field(pattern="^(onboarding|lesson|voice|support|other)$")
    message: str = Field(min_length=3, max_length=1000)


@router.get("/config")
def launch_config(request: Request):
    settings = request.app.state.settings
    return {"product_name": settings.product_name, "version": settings.release_version,
            "closed_beta": settings.closed_beta_enabled, "razorpay_mode": settings.razorpay_mode,
            "payments_enabled": settings.razorpay_enabled, "support_email": settings.support_email,
            "provider_policy": "OPENAI_FIRST", "release_state": "RELEASE_CANDIDATE_NOT_PUBLIC"}


@router.post("/feedback", status_code=202)
def feedback(data: Feedback, request: Request, principal: Principal = Depends(current_principal)):
    request.app.state.metrics.increment("beta_feedback")
    return {"accepted": True, "category": data.category, "learner_id": principal.learner.id}
