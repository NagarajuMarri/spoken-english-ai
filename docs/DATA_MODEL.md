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
## Authentication ownership

`UserAccount` stores normalized unique email, bcrypt hash, status, verification flag, timestamps, and last login. Each newly registered `Learner` has one unique `user_account_id`. `RefreshToken` stores only a SHA-256 token hash, family and unique-parent lineage, issue/expiry/revocation timestamps, replacement linkage, bounded user-agent data, and no raw IP address. `SecurityAuditEvent` is append-only application data used for critical refresh-reuse evidence.

Migration `0004_auth_ownership` preserves pre-authentication learners by creating a one-to-one `DISABLED` account with an unusable password marker for each legacy row, then makes ownership non-null. Operators may explicitly claim or retire those disabled development accounts; they cannot authenticate until a separate verified account-recovery process is implemented.
