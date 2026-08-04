from fastapi import APIRouter, Depends, Request

from backend.app.core.security import Principal, current_principal, ensure_owner

router = APIRouter(prefix="/api/v1", tags=["intelligent-learning"])


@router.get("/learners/{learner_id}/ai-cost-metrics")
def learner_cost_metrics(learner_id: str, request: Request, principal: Principal = Depends(current_principal)):
    ensure_owner(learner_id, principal)
    return request.app.state.learning_engine.metrics.dashboard(learner_id=learner_id)


@router.get("/learners/{learner_id}/cache-metrics")
def learner_cache_metrics(learner_id: str, request: Request, principal: Principal = Depends(current_principal)):
    ensure_owner(learner_id, principal)
    engine = request.app.state.learning_engine
    lesson = engine.lesson_cache.statistics()
    tts_total = engine.tts_cache.hits + engine.tts_cache.misses
    return {"lesson_cache": lesson, "tts_cache": {"hits": engine.tts_cache.hits, "misses": engine.tts_cache.misses, "hit_rate": engine.tts_cache.hits / tts_total if tts_total else 0.0}}
