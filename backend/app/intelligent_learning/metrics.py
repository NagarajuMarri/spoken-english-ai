from collections import defaultdict

from .models import CostEvent


class CostMetrics:
    def __init__(self) -> None:
        self._events: list[CostEvent] = []

    def record(self, event: CostEvent) -> None:
        self._events.append(event)

    def dashboard(self, *, learner_id: str | None = None) -> dict:
        events = [event for event in self._events if learner_id is None or event.learner_id == learner_id]
        count = len(events)
        by_learner: defaultdict[str, float] = defaultdict(float)
        by_lesson: defaultdict[str, float] = defaultdict(float)
        by_conversation: defaultdict[str, float] = defaultdict(float)
        for event in events:
            by_learner[event.learner_id] += event.estimated_cost_usd
            by_lesson[event.lesson_id] += event.estimated_cost_usd
            by_conversation[event.conversation_id] += event.estimated_cost_usd
        total_cost = sum(event.estimated_cost_usd for event in events)
        return {"requests": count, "cache_effectiveness": sum(event.cache_hit for event in events) / count if count else 0.0, "average_prompt_size": sum(event.prompt_tokens for event in events) / count if count else 0.0, "average_response_size": sum(event.completion_tokens for event in events) / count if count else 0.0, "average_latency_ms": sum(event.response_latency_ms for event in events) / count if count else 0.0, "total_cost_usd": round(total_cost, 6), "cost_per_learner": dict(by_learner), "cost_per_lesson": dict(by_lesson), "cost_per_conversation": dict(by_conversation), "estimated_monthly_cost_usd": round(total_cost * 30, 6), "models_used": sorted({event.model_used for event in events})}
