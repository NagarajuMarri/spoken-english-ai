from __future__ import annotations

from .models import BuiltPrompt, LearnerSummary, PromptContext


class ConversationSummarizer:
    def summarize(self, *, messages: list[str], current_lesson: str, completed_lessons: list[str], strengths: list[str], weaknesses: list[str], common_mistakes: list[str], confidence: int) -> LearnerSummary:
        # Message text is intentionally not retained: only bounded pedagogical signals survive.
        _ = messages
        return LearnerSummary(tuple(strengths[:5]), tuple(weaknesses[:5]), current_lesson, tuple(completed_lessons[-10:]), tuple(common_mistakes[:5]), max(0, min(100, confidence)))


class PromptBuilder:
    def __init__(self, *, max_recent_turns: int = 6, max_context_items: int = 4, max_chars: int = 6000) -> None:
        self.max_recent_turns = max_recent_turns
        self.max_context_items = max_context_items
        self.max_chars = max_chars

    def build(self, context: PromptContext) -> BuiltPrompt:
        recent = context.recent_conversation[-self.max_recent_turns:]
        retrieved = context.retrieved_context[:self.max_context_items]
        summary = context.learner_summary
        sections = [f"Tutor persona: {context.tutor_persona}", f"Learner summary: strengths={list(summary.strengths)}; weaknesses={list(summary.weaknesses)}; confidence={summary.confidence}", f"Current lesson: {context.current_lesson}", f"Current objective: {context.current_objective}", "Recent conversation:\n" + "\n".join(recent), "Bounded retrieved context:\n" + "\n".join(retrieved)]
        text = "\n\n".join(sections)[: self.max_chars]
        return BuiltPrompt(text, max(1, (len(text) + 3) // 4), len(recent), len(retrieved))


class KnowledgeBoundary:
    """Future Vedha-compatible retrieval contract; no storage or retrieval implementation."""

    def retrieve(self, *, query: str, lesson_id: str, limit: int) -> tuple[str, ...]:
        raise NotImplementedError


class EmptyKnowledgeBoundary(KnowledgeBoundary):
    def retrieve(self, *, query: str, lesson_id: str, limit: int) -> tuple[str, ...]:
        return ()
