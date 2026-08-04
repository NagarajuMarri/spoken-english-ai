from collections.abc import Callable

from .cache import TTSAudioCache, VersionedLessonCache
from .context import PromptBuilder
from .metrics import CostMetrics
from .models import CacheKind, CostEvent, EngineResult, PromptContext, RequestCategory
from .routing import ModelRouter, RequestClassifier


class IntelligentLearningEngine:
    def __init__(self, *, model_call: Callable[[str, str], tuple[str, int, float, str]] | None = None) -> None:
        self.classifier = RequestClassifier()
        self.router = ModelRouter()
        self.lesson_cache = VersionedLessonCache()
        self.tts_cache = TTSAudioCache()
        self.prompt_builder = PromptBuilder()
        self.metrics = CostMetrics()
        self.model_call = model_call

    def handle(self, *, message: str, context: PromptContext, learner_id: str, lesson_id: str, conversation_id: str, cache_version: int = 1) -> EngineResult:
        category = self.classifier.classify(message)
        decision = self.router.route(category, complexity=min(10, len(message) // 200))
        cache_kind = self._cache_kind(category)
        if cache_kind:
            cached = self.lesson_cache.get(lesson_id, cache_kind, version=cache_version)
            if cached:
                self._record(learner_id, lesson_id, conversation_id, 0, len(cached.content) // 4, 0, True, "cache")
                return EngineResult(decision, cached.content, cache_hit=True, metadata={"source": "lesson_cache", "cache_version": cache_version})
        if not decision.requires_llm:
            response = self._deterministic(category)
            self._record(learner_id, lesson_id, conversation_id, 0, len(response) // 4, 0, False, "deterministic")
            return EngineResult(decision, response, metadata={"source": "deterministic"})
        prompt = self.prompt_builder.build(context)
        if self.model_call is None:
            response, completion_tokens, latency_ms, model = ("Let us practise that step by step.", 9, 0.0, "deterministic-boundary")
        else:
            if decision.model_tier is None:
                raise RuntimeError("A reasoning route must include a model tier.")
            response, completion_tokens, latency_ms, model = self.model_call(prompt.text, decision.model_tier.value)
        cost = prompt.estimated_tokens * 0.00000015 + completion_tokens * 0.0000006
        self._record(learner_id, lesson_id, conversation_id, prompt.estimated_tokens, completion_tokens, latency_ms, False, model, cost)
        return EngineResult(decision, response, prompt, metadata={"source": "model_boundary", "model": model, "estimated_cost_usd": cost})

    @staticmethod
    def _cache_kind(category: RequestCategory) -> CacheKind | None:
        return {RequestCategory.LESSON_INTRODUCTION: CacheKind.LESSON_INTRODUCTION, RequestCategory.GRAMMAR_EXPLANATION: CacheKind.GRAMMAR_EXPLANATION, RequestCategory.VOCABULARY_EXPLANATION: CacheKind.VOCABULARY_EXPLANATION, RequestCategory.ASSESSMENT: CacheKind.ASSESSMENT_TEMPLATE}.get(category)

    @staticmethod
    def _deterministic(category: RequestCategory) -> str:
        return {RequestCategory.GREETING: "Hello! I am happy to practise English with you.", RequestCategory.SMALL_TALK: "I am doing well. Let us continue your practice.", RequestCategory.LESSON_NAVIGATION: "Your lesson navigation request is ready.", RequestCategory.PROGRESS: "Your progress is available on the Progress screen.", RequestCategory.SYSTEM: "The learning session is ready."}.get(category, "Let us begin this lesson together.")

    def _record(self, learner_id: str, lesson_id: str, conversation_id: str, prompt: int, completion: int, latency: float, hit: bool, model: str, cost: float = 0.0) -> None:
        self.metrics.record(CostEvent(learner_id, lesson_id, conversation_id, prompt, completion, cost, latency, hit, model))
