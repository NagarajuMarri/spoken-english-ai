from __future__ import annotations

import re

from .models import ModelTier, RequestCategory, RouteDecision


class RequestClassifier:
    """Deterministic, ordered classifier; no model call is needed to route a turn."""

    _rules: tuple[tuple[RequestCategory, tuple[str, ...]], ...] = (
        (RequestCategory.SYSTEM, ("system:", "health check", "reset session")),
        (RequestCategory.LESSON_NAVIGATION, ("next lesson", "previous lesson", "start lesson", "go back")),
        (RequestCategory.LESSON_INTRODUCTION, ("introduce lesson", "what will we learn", "lesson overview")),
        (RequestCategory.GRAMMAR_EXPLANATION, ("grammar", "tense", "why is", "correct this sentence")),
        (RequestCategory.VOCABULARY_EXPLANATION, ("meaning of", "vocabulary", "synonym", "use the word")),
        (RequestCategory.PRONUNCIATION_COACHING, ("pronounce", "pronunciation", "say this", "stress")),
        (RequestCategory.ASSESSMENT, ("assess", "test me", "score my", "evaluate")),
        (RequestCategory.PROGRESS, ("my progress", "my streak", "completed lessons", "how am i doing")),
        (RequestCategory.GREETING, ("hello", "hi", "hey", "good morning", "good evening")),
        (RequestCategory.SMALL_TALK, ("how are you", "thank you", "thanks", "nice to meet")),
    )

    def classify(self, text: str) -> RequestCategory:
        normalised = re.sub(r"\s+", " ", text.strip().lower())
        for category, markers in self._rules:
            if any(self._matches(normalised, marker) for marker in markers):
                return category
        return RequestCategory.CONVERSATION_PRACTICE

    @staticmethod
    def _matches(text: str, marker: str) -> bool:
        if marker.endswith(":"):
            return text.startswith(marker)
        return re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text) is not None


class ModelRouter:
    _deterministic = {RequestCategory.GREETING, RequestCategory.SMALL_TALK, RequestCategory.LESSON_NAVIGATION, RequestCategory.LESSON_INTRODUCTION, RequestCategory.PROGRESS, RequestCategory.SYSTEM}

    def route(self, category: RequestCategory, *, complexity: int = 0) -> RouteDecision:
        if category in self._deterministic:
            return RouteDecision(category, False, None, "deterministic_or_cached_content")
        if category in {RequestCategory.VOCABULARY_EXPLANATION, RequestCategory.PRONUNCIATION_COACHING}:
            tier = ModelTier.LOW_COST
        elif category is RequestCategory.ASSESSMENT or complexity >= 8:
            tier = ModelTier.HIGH_REASONING
        else:
            tier = ModelTier.STANDARD
        return RouteDecision(category, True, tier, "reasoning_required")
