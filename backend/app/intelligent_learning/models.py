from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RequestCategory(StrEnum):
    GREETING = "GREETING"
    SMALL_TALK = "SMALL_TALK"
    LESSON_NAVIGATION = "LESSON_NAVIGATION"
    LESSON_INTRODUCTION = "LESSON_INTRODUCTION"
    GRAMMAR_EXPLANATION = "GRAMMAR_EXPLANATION"
    VOCABULARY_EXPLANATION = "VOCABULARY_EXPLANATION"
    PRONUNCIATION_COACHING = "PRONUNCIATION_COACHING"
    CONVERSATION_PRACTICE = "CONVERSATION_PRACTICE"
    ASSESSMENT = "ASSESSMENT"
    PROGRESS = "PROGRESS"
    SYSTEM = "SYSTEM"


class ModelTier(StrEnum):
    LOW_COST = "LOW_COST"
    STANDARD = "STANDARD"
    HIGH_REASONING = "HIGH_REASONING"


class CacheKind(StrEnum):
    LESSON_INTRODUCTION = "lesson_introduction"
    GRAMMAR_EXPLANATION = "grammar_explanation"
    VOCABULARY_EXPLANATION = "vocabulary_explanation"
    DIALOGUE_TEMPLATE = "dialogue_template"
    EXERCISE = "exercise"
    ASSESSMENT_TEMPLATE = "assessment_template"


@dataclass(frozen=True)
class RouteDecision:
    category: RequestCategory
    requires_llm: bool
    model_tier: ModelTier | None
    reason: str


@dataclass(frozen=True)
class LearnerSummary:
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    current_lesson: str = ""
    completed_lessons: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    confidence: int = 50


@dataclass(frozen=True)
class PromptContext:
    tutor_persona: str
    learner_summary: LearnerSummary
    current_lesson: str
    current_objective: str
    recent_conversation: tuple[str, ...]
    retrieved_context: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuiltPrompt:
    text: str
    estimated_tokens: int
    included_turns: int
    included_context_items: int


@dataclass(frozen=True)
class CostEvent:
    learner_id: str
    lesson_id: str
    conversation_id: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    response_latency_ms: float
    cache_hit: bool
    model_used: str
    cached_tokens: int = 0
    cost_classification: str = "ESTIMATE_NOT_PROVIDER_BILLING"


@dataclass
class EngineResult:
    decision: RouteDecision
    response: str
    prompt: BuiltPrompt | None = None
    cache_hit: bool = False
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
