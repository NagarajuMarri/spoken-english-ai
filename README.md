# Spoken English AI

Spoken English AI is a voice-first learning product for Indian learners, initially Telugu-speaking adults and students who know some English but lack speaking confidence. It is designed around realistic practice, supportive delayed corrections, and a structured path from Starter to Intermediate.

## Milestone 1 boundary

Milestone 1 defined the foundation; Milestone 2 added onboarding and persisted text conversations. Milestone 3 adds a five-level curriculum, deterministic daily lessons, evaluation, progress and UTC streaks, plus provider-neutral AI/voice interfaces with local doubles. Authentication, frontends, and paid providers remain excluded.

## Architecture

The backend starts as a modular monolith. API routes delegate to domain and service layers; repositories isolate persistence; and provider-specific LLM, speech-to-text, and text-to-speech code belongs behind integration interfaces. This supports future web and mobile clients without the operational cost of premature microservices. See [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md).

## Local setup

Requires Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Run the API:

```powershell
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/health`.

Apply database migrations:

```powershell
alembic upgrade head
```

The default local database is SQLite. Set `SPOKEN_ENGLISH_DATABASE_URL` to a PostgreSQL SQLAlchemy URL for a PostgreSQL deployment. Automatic table creation is convenient for local development and tests; deployed environments should set `SPOKEN_ENGLISH_AUTO_CREATE_TABLES=false` and use Alembic.

Run tests:

```powershell
pytest
```

## Roadmap

Milestone 3 implements curriculum, progress, evaluation, and local provider boundaries. Next comes evaluation calibration and consent-aware audio lifecycle work before any paid integration. See [ROADMAP.md](docs/ROADMAP.md).
