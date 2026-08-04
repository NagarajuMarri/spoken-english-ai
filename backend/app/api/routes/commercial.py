from fastapi import APIRouter, Depends, Request

from backend.app.core.security import Principal, current_principal, ensure_owner

router = APIRouter(prefix="/api/v1/commercial", tags=["commercial"])


@router.get("/plans")
def plans(request: Request):
    settings = request.app.state.settings
    return {
        "currency": "INR",
        "prices_are_configuration": True,
        "plans": [
            {"plan_id": "FREE", "price": 0},
            {"plan_id": "PREMIUM_MONTHLY", "price": settings.commercial_monthly_price_inr},
            {"plan_id": "PREMIUM_YEARLY", "price": settings.commercial_yearly_price_inr},
        ],
        "trial_days": settings.commercial_trial_days,
    }


@router.get("/learners/{learner_id}/founder-metrics")
def founder_metrics(learner_id: str, request: Request, principal: Principal = Depends(current_principal)):
    ensure_owner(learner_id, principal)
    ai = request.app.state.learning_engine.metrics.dashboard(learner_id=learner_id)
    result = request.app.state.commercial_service.founder_metrics(
        ai_cost_usd=ai["estimated_total_cost_usd"],
        conversation_costs=ai["cost_per_conversation"],
    )
    return {"scope": "learner_owner_scoped", **result}
