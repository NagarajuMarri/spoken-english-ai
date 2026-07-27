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
