"""Run with: python examples/deterministic_intelligent_learning.py"""

from backend.app.intelligent_learning import IntelligentLearningEngine
from backend.app.intelligent_learning.models import CacheKind, LearnerSummary, PromptContext


engine = IntelligentLearningEngine()
engine.lesson_cache.put("daily-routine", CacheKind.LESSON_INTRODUCTION, "Today we will describe a daily routine.")
context = PromptContext("Ananya, supportive Indian-English tutor", LearnerSummary(weaknesses=("articles",), confidence=62), "daily-routine", "Use the present simple", tuple(f"turn {index}" for index in range(9)))
cached = engine.handle(message="Introduce lesson", context=context, learner_id="learner-demo", lesson_id="daily-routine", conversation_id="conversation-demo")
reasoned = engine.handle(message="Explain this grammar", context=context, learner_id="learner-demo", lesson_id="daily-routine", conversation_id="conversation-demo")
assert cached.cache_hit and not cached.decision.requires_llm
assert reasoned.decision.requires_llm and reasoned.prompt.included_turns == 6
print({"cached_route": cached.decision.category, "reasoning_tier": reasoned.decision.model_tier, "metrics": engine.metrics.dashboard()})
