# Intelligent Learning Engine

Milestone 9.5 implements the locked PRD v1.0 cost-optimization boundary. It does not implement Vedha, embeddings, vector search, PDF processing, payments, or deployment.

The deterministic classifier routes greetings, small talk, navigation, lesson introductions, progress, and system requests without an LLM. Vocabulary and pronunciation use `LOW_COST`; grammar and conversation use `STANDARD`; assessments and unusually complex requests use `HIGH_REASONING`. Provider choice stays behind the Milestone 9 boundary, with OpenAI as the current production configuration rather than a domain dependency.

Lesson content is versioned, invalidatable, size-bounded, and expires after a configured retention window. The TTS cache keys privacy scope, normalized text, and tutor voice so learners and voices cannot receive another scope's artifact. It stores only completed, consented, non-cancelled audio references and expires them on a bounded lifecycle. Prompt construction admits only persona, pedagogical learner summary, current lesson/objective, six recent turns, and four retrieved items. Summaries discard raw older conversation text and retain only bounded strengths, weaknesses, lesson state, common mistakes, and confidence; persisted summaries remain learner-owned and replaceable by version.

Cost events measure prompt, completion, and cached tokens, estimated cost, latency, cache hit/miss, and model. Authenticated learner-scoped APIs expose aggregate cost and cache dashboards. Every dashboard labels cost as `ESTIMATE_NOT_PROVIDER_BILLING`; the persistent schema is append-friendly and supports learner, lesson, and conversation aggregation.

## Deterministic reduction model

For a representative 100-turn learning session, the conservative model assumes 30 deterministic turns, 25 reusable content/TTS cache hits, and 45 reasoning turns. Compared with calling the standard LLM and regenerating TTS for all 100 turns, this avoids 55% of LLM requests. Bounded prompts further reduce prompt tokens on the remaining requests. This `ARCHITECTURAL_ESTIMATE` is **55% fewer LLM calls**, not a guaranteed invoice reduction; realized savings require production telemetry and provider billing evidence.
