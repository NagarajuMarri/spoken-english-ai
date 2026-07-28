# Product Acceptance Criteria

## Product definition

- All fourteen requested documents exist and consistently target Telugu-speaking learners.
- MVP inclusions, exclusions, eight conversation modes, five levels, correction behavior, Telugu support, subscription boundary, and roadmap are explicit.
- Architecture is a modular monolith with future web/mobile clients and provider-neutral LLM, speech, payment, and storage boundaries.
- Planned data is documented without implementing authentication or persistence models.

## Repository and behavior

- The requested backend package structure, README, ignore file, environment example, project metadata, and MIT license exist.
- Python 3.12+, FastAPI, Pydantic settings, SQLAlchemy, Alembic, pytest, TestClient, PostgreSQL readiness, and local SQLite are represented.
- `GET /health` returns HTTP 200 and exactly the documented status, service, and version fields.
- Configuration loads from environment variables and contains no secrets.
- Importing/starting the application calls no database, AI, speech, payment, or storage service.

## Verification

From a clean Python 3.12 environment:

```powershell
python -m pip install -e ".[dev]"
pytest
```

All tests must pass. The work is committed on `product/milestone-1-mvp-foundation` with the requested commit message and proposed as a draft pull request to `main`.

## Milestone 2

- Learners can be created, retrieved, and onboarded using the five levels, five learning goals, 5–120 minute daily target, and Telugu/English native language.
- Duplicate email and invalid inputs return structured errors.
- All eight scenarios are listed deterministically.
- A persisted conversation requires an existing learner and scenario.
- Messages preserve original text and produce a positive natural reply; only clear high-value errors produce at most one deterministic correction.
- Telugu explanation is added only when requested.
- Learner, Conversation, ConversationMessage, and ProgressRecord use SQLAlchemy 2.x UUID-string models.
- Alembic can apply the initial schema; tests use separate temporary SQLite files.
- No route owns business rules and no external integration is called.
- `python -m pytest` passes without the former TestClient compatibility warning.

## Milestone 3

- Five-level lessons contain all required teaching metadata and deterministic selection considers level, goal, completion, recent history, and UTC date.
- Lesson sessions persist completion and bounded text-only evaluations.
- Progress and UTC streaks deduplicate same-day practice, reset across gaps, and retain the longest run.
- Provider protocols and local doubles make no network calls and never claim pronunciation accuracy.
- PostgreSQL message sequencing uses parent-row locking, uniqueness, and bounded retry.
- Revision `0002_curriculum_progress`, isolated tests, compilation, and diff checks pass.

## Milestone 4

- Versioned processing/storage consent is auditable; withdrawal blocks processing and queues metadata deletion.
- Voice sessions persist fake transcription, tutor/correction text, fake synthesis references, and ordered turns without raw audio.
- Media/reference validation returns structured privacy errors.
- Lifecycle cleanup and retained/temporary behavior are tested.
- Pronunciation is explicitly synthetic and excluded from progress.
- Daily plan combines lesson, scenario, minutes, streak, progress, and consent-aware voice availability.
## Milestone 5

- Registration normalizes unique email, enforces password length, hashes passwords, and creates one learner foundation.
- Login returns generic credential failures and blocks inactive accounts.
- Access tokens are short lived and validate issuer, audience, signature, expiry, and type.
- Refresh tokens are hashed at rest, rotate on use, reject reuse/expiry, and support logout and logout-all.
- Learner-specific resources require authentication and enforce a consistent privacy-safe `404` ownership policy.
- Responses and example configuration expose no password hashes, raw refresh tokens at rest, or deployed secrets.
- Production limitations and the legacy development-data ownership migration are documented.

## Milestone 6

- Every response has a request ID; validated correlation IDs propagate.
- Structured logs and errors exclude credentials, tokens, hashes, secrets, raw IPs, and audio.
- Security audit events are durable, append-only through application boundaries, and metadata allow-listed.
- Liveness, readiness, and version probes expose no sensitive dependency details.
- Provider-neutral metrics and rate-limit interfaces have deterministic in-memory implementations and a Redis adapter boundary.
- JWT active/previous key IDs support rotation while rejecting unknown keys and unexpected algorithms.
- Audio cleanup is deterministic, batched, repeat-safe, scheduled-job compatible, and indexed.
- Administrative account, session, audit, and pending-deletion operations remain outside learner HTTP APIs.
