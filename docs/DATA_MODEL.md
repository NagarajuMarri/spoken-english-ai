# Planned Data Model

No database models are implemented in Milestone 1. The planned relational model is:

- **Learner:** id, email/identity reference, locale, timezone, status, created_at.
- **LearnerProfile:** learner_id, selected_level, Telugu-explanation preference, goals.
- **Lesson:** id, level, mode, objective, content version, active state.
- **ConversationSession:** id, learner_id, lesson_id/mode, status, started_at, completed_at.
- **ConversationTurn:** id, session_id, sequence, speaker, input modality, text, provider confidence, created_at.
- **FeedbackItem:** id, session_id, source turn(s), category, priority, original text, corrected text, explanation, explanation locale, confidence.
- **ProgressSnapshot:** id, learner_id, period, level, grammar/vocabulary/fluency measures, evidence version.
- **DailyActivity:** learner_id, local date, qualifying activity count, streak contribution.
- **Subscription:** learner_id, plan, status, period boundaries, external reference.
- **Entitlement:** subscription/plan, feature key, allowance, reset period.

Use UUID identifiers, UTC timestamps, explicit content/policy versions, and immutable event timestamps. Unique constraints protect turn sequence and one daily activity record per learner/date. Foreign keys keep ownership explicit. Sensitive identity data is separated from learning content, and deletion can cascade or anonymize according to retention policy.

Audio is object storage metadata, not a database blob, and is absent unless consent and retention rules allow it. Transcript edits and derived feedback retain provenance.

