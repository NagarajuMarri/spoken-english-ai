# Spoken English AI

Spoken English AI is a voice-first learning product for Indian learners, initially Telugu-speaking adults and students who know some English but lack speaking confidence. It is designed around realistic practice, supportive delayed corrections, and a structured path from Starter to Intermediate.

## Milestone 1 boundary

This milestone defines the product and establishes a small executable backend. It includes product, learning, conversation, correction, architecture, data, API, privacy, subscription, roadmap, and acceptance documentation plus a FastAPI health endpoint. It deliberately excludes authentication, persistence models, frontends, paid AI/speech/payment services, and production infrastructure.

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

Run tests:

```powershell
pytest
```

## Roadmap

Milestone 2 should implement learner identity, proficiency onboarding, conversation session domain models, and a deterministic text-only lesson loop. Later milestones add provider-backed voice, progress intelligence, subscriptions, and client applications. See [ROADMAP.md](docs/ROADMAP.md).

