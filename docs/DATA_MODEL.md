# Data Model

Milestone 2 implements four SQLAlchemy 2.x models with UUID strings and UTC timestamps:

- **Learner:** unique normalized email, display name, native language, proficiency level, learning goal, daily goal, and timestamps.
- **Conversation:** learner foreign key, deterministic scenario identifier, and creation time.
- **ConversationMessage:** conversation foreign key, unique per-conversation turn number, original learner text, tutor response, optional correction, and timestamp.
- **ProgressRecord:** learner and optional conversation references, completed-turn count, and timestamp.

The initial Alembic revision is `0001_learner_onboarding`. SQLite supports local development and isolated tests; model types and constraints remain PostgreSQL-compatible. Foreign keys express ownership and turn uniqueness protects transcript order.

Future models include lessons, richer feedback provenance, daily activity/streaks, progress snapshots, subscriptions, and entitlements. Audio remains object-storage metadata rather than a database blob.

Milestone 3 adds `LessonSession` and `ConversationEvaluation`, and extends `ProgressRecord` with lesson, UTC practice date, duration, score, scenario, and proficiency dimensions. Static curriculum remains a version-controlled domain catalogue because it is small and not runtime-administered. Revision `0002_curriculum_progress` applies these changes.

Milestone 4 adds append-only `ConsentRecord`, `VoiceSession`, `VoiceTurn`, and `AudioAsset` metadata in revision `0003_voice_foundation`. Assets store media type, safe logical key, lifecycle state, expiry, and deletion time—never raw bytes.
