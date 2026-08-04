from datetime import UTC, datetime, timedelta

import pytest

from backend.app.intelligent_learning.cache import TTSAudioCache, VersionedLessonCache
from backend.app.intelligent_learning.context import ConversationSummarizer, EmptyKnowledgeBoundary, PromptBuilder
from backend.app.intelligent_learning.engine import IntelligentLearningEngine
from backend.app.intelligent_learning.models import CacheKind, LearnerSummary, ModelTier, PromptContext, RequestCategory
from backend.app.intelligent_learning.routing import ModelRouter, RequestClassifier


@pytest.mark.parametrize(("text", "expected"), [
    ("Hello", RequestCategory.GREETING), ("How are you?", RequestCategory.SMALL_TALK),
    ("Start lesson", RequestCategory.LESSON_NAVIGATION), ("Introduce lesson", RequestCategory.LESSON_INTRODUCTION),
    ("Explain this grammar", RequestCategory.GRAMMAR_EXPLANATION), ("What is the meaning of concise?", RequestCategory.VOCABULARY_EXPLANATION),
    ("How do I pronounce this?", RequestCategory.PRONUNCIATION_COACHING), ("Let us discuss Hyderabad", RequestCategory.CONVERSATION_PRACTICE),
    ("Assess my answer", RequestCategory.ASSESSMENT), ("Show my progress", RequestCategory.PROGRESS), ("system: status", RequestCategory.SYSTEM),
])
def test_all_locked_request_categories(text, expected):
    assert RequestClassifier().classify(text) is expected


def test_classifier_uses_word_boundaries_not_substrings():
    assert RequestClassifier().classify("Is this grammar correct?") is RequestCategory.GRAMMAR_EXPLANATION


def test_only_reasoning_categories_use_model():
    router = ModelRouter()
    assert not router.route(RequestCategory.GREETING).requires_llm
    assert router.route(RequestCategory.GRAMMAR_EXPLANATION).model_tier is ModelTier.STANDARD
    assert router.route(RequestCategory.VOCABULARY_EXPLANATION).model_tier is ModelTier.LOW_COST
    assert router.route(RequestCategory.ASSESSMENT).model_tier is ModelTier.HIGH_REASONING


def test_versioned_lesson_cache_invalidation_and_statistics():
    cache = VersionedLessonCache()
    cache.put("lesson-1", CacheKind.EXERCISE, "v1", version=1)
    cache.put("lesson-1", CacheKind.EXERCISE, "v2", version=2)
    assert cache.get("lesson-1", CacheKind.EXERCISE, version=2).content == "v2"
    assert cache.get("missing", CacheKind.EXERCISE) is None
    assert cache.invalidate("lesson-1", CacheKind.EXERCISE, before_version=2) == 1
    assert cache.statistics() == {"entries": 1, "hits": 1, "misses": 1, "invalidations": 1, "hit_rate": 0.5}


def test_tts_cache_reuses_normalized_text_for_same_voice():
    cache = TTSAudioCache()
    cache.store("Welcome   learner", "ananya-en-in", "audio://one")
    assert cache.resolve("Welcome learner", "ANANYA-EN-IN") == "audio://one"
    assert cache.resolve("Welcome learner", "arjun-en-in") is None


def test_caches_expire_and_are_bounded():
    now = [datetime(2026, 8, 4, tzinfo=UTC)]
    cache = VersionedLessonCache(max_entries=1, ttl=timedelta(minutes=5), clock=lambda: now[0])
    cache.put("one", CacheKind.EXERCISE, "first")
    cache.put("two", CacheKind.EXERCISE, "second")
    assert cache.get("one", CacheKind.EXERCISE) is None
    now[0] += timedelta(minutes=6)
    assert cache.get("two", CacheKind.EXERCISE) is None


def test_tts_cache_is_privacy_scoped_and_only_caches_success():
    cache = TTSAudioCache()
    assert cache.store("Private feedback", "ananya", "audio://one", privacy_scope="learner-1")
    assert cache.resolve("Private feedback", "ananya", privacy_scope="learner-2") is None
    assert not cache.store("Failed", "ananya", "audio://failed", completed=False)
    assert not cache.store("Cancelled", "ananya", "audio://cancelled", cancelled=True)
    assert not cache.store("No consent", "ananya", "audio://private", consent=False)


def test_prompt_is_bounded_and_excludes_complete_history():
    prompt = PromptBuilder(max_recent_turns=2, max_context_items=1, max_chars=500).build(PromptContext("Indian-English tutor", LearnerSummary(strengths=("clarity",), weaknesses=("articles",)), "lesson-1", "Use present tense", tuple(f"turn-{i}" for i in range(10)), ("approved item", "must not appear")))
    assert prompt.included_turns == 2
    assert "turn-9" in prompt.text and "turn-0" not in prompt.text
    assert "approved item" in prompt.text and "must not appear" not in prompt.text


def test_summary_retains_only_pedagogical_signals():
    summary = ConversationSummarizer().summarize(messages=["private full conversation"], current_lesson="lesson-2", completed_lessons=["lesson-1"], strengths=["fluency"], weaknesses=["articles"], common_mistakes=["a/an"], confidence=110)
    assert summary.current_lesson == "lesson-2"
    assert summary.confidence == 100
    assert "private" not in repr(summary)


def test_empty_knowledge_boundary_does_no_retrieval():
    assert EmptyKnowledgeBoundary().retrieve(query="anything", lesson_id="lesson-1", limit=3) == ()


def test_engine_serves_cached_lesson_without_model_call():
    calls = []
    engine = IntelligentLearningEngine(model_call=lambda prompt, tier: calls.append(prompt))
    engine.lesson_cache.put("lesson-1", CacheKind.LESSON_INTRODUCTION, "Cached introduction")
    result = engine.handle(message="Introduce lesson", context=_context(), learner_id="l1", lesson_id="lesson-1", conversation_id="c1")
    assert result.response == "Cached introduction" and result.cache_hit
    assert calls == []


def test_engine_routes_reasoning_and_records_cost_metrics():
    engine = IntelligentLearningEngine(model_call=lambda prompt, tier: (f"{tier} response", 20, 125.0, "openai-low-cost"))
    result = engine.handle(message="Explain this grammar", context=_context(), learner_id="l1", lesson_id="lesson-1", conversation_id="c1")
    assert result.decision.requires_llm
    dashboard = engine.metrics.dashboard(learner_id="l1")
    assert dashboard["requests"] == 1
    assert dashboard["estimated_total_cost_usd"] > 0
    assert dashboard["cost_classification"] == "ESTIMATE_NOT_PROVIDER_BILLING"
    assert dashboard["average_latency_ms"] == 125.0


def test_engine_avoids_model_for_greeting():
    engine = IntelligentLearningEngine(model_call=lambda *_: pytest.fail("model must not be called"))
    result = engine.handle(message="Hello", context=_context(), learner_id="l1", lesson_id="lesson-1", conversation_id="c1")
    assert result.metadata["source"] == "deterministic"
    assert engine.metrics.dashboard()["estimated_total_cost_usd"] == 0


def _context():
    return PromptContext("Ananya Indian-English tutor", LearnerSummary(), "lesson-1", "Speak clearly", ("recent turn",))
