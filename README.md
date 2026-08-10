# Spoken English AI

Spoken English AI is a voice-first learning product for Indian learners, initially Telugu-speaking adults and students who know some English but lack speaking confidence. It is designed around realistic practice, supportive delayed corrections, and a structured path from Starter to Intermediate.

## RC1 feature gates

- Feature 5 — OpenAI TTS / audible tutor speech: **ACCEPTED** by the founder in Windows Chrome.
- Feature 6 — Native Telugu review and spoken correction safety: **ENGINEERING_ACCEPTED_WITH_DEFERRED_DEVICE_GATE**.
- Feature 7 — Real 3D Ananya / audio synchronization: **ENGINEERING_REMEDIATED_WITH_DEFERRED_DEVICE_GATE**.

The current RC remediation adds a rigged, web-native 3D Ananya and retains explicit weak-device,
reduced-motion, and WebGL-failure fallbacks. Speaking starts only from real HTML audio playback
events, and mouth motion follows measured playback amplitude from a browser audio analyser.
Conversation and TTS lifecycle events now flow through a reusable, provider-neutral multimedia
runtime that owns tutor state, lip-sync strategy, animation timing, and renderer fallback contracts.
Automated checks do not claim audible output, subjective visual quality, or founder physical-device
acceptance. Final RC regression and one consolidated founder device review remain required before
release approval. See `docs/FEATURE_7_AVATAR_AUDIO_SYNC.md`.

Native Telugu quality review is a first-class learner capability. Learners choose English,
English with Telugu explanation, or Telugu-dominant explanation. Telugu modes pass through a
separate structured review stage before persistence, TTS, and presentation; review cannot edit
correction results, evaluation signals, difficulty, or learning objectives. See
`docs/TELUGU_QUALITY_FOUNDER_REVIEW.md` and `docs/REUSABLE_REVIEW_PIPELINE.md`.

## Milestone 1 boundary

Milestones 1–3 established the product, onboarding, conversations, curriculum, and progress. Milestone 4 adds consent-aware simulated voice practice, auditable consent, metadata-only audio lifecycle management, and an explicitly synthetic pronunciation double. Authentication, real audio, frontends, object storage, and paid providers remain excluded.

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
python -m pytest
```

## Roadmap

The RC now includes the voice/privacy foundation, authentication, provider boundaries, upload controls, and durable worker jobs. The next product milestone is structured curriculum work after founder acceptance of the final RC runtime. See [ROADMAP.md](docs/ROADMAP.md).
## Authentication

Milestone 5 adds email/password registration, bcrypt password hashing, short-lived JWT access tokens, rotated opaque refresh tokens stored only as SHA-256 hashes, and owner-scoped learner APIs. Configure every `SPOKEN_ENGLISH_JWT_*` setting in deployment; the `.env.example` values are placeholders, not production secrets.

Register with `POST /api/v1/auth/register`, then send `Authorization: Bearer <access_token>`. Refresh tokens rotate through `/api/v1/auth/refresh` and can be revoked individually or account-wide. Password recovery uses `/api/v1/auth/password-reset/request`, `/validate`, and `/confirm`; reset tokens are short-lived, hashed, single-use, and revoke existing sessions.

## Operations

Every request receives `X-Request-ID` and a validated/generated `X-Correlation-ID`. JSON-compatible completion logs exclude request bodies and credentials. Operational probes are `/health/live`, `/health/ready`, and `/health/version`. Run scheduled simulated-audio cleanup with `python -m backend.app.cli.cleanup_audio`.

## Deterministic AI tutor

Milestone 7 adds provider-neutral AI conversation, STT, TTS, synthetic pronunciation, learner memory, usage controls, and idempotent voice orchestration. No external key is required:

```powershell
python examples/deterministic_ai_conversation.py
python examples/deterministic_voice_tutor.py
```

See `docs/PROVIDER_ARCHITECTURE.md` and `docs/VOICE_TUTOR_PIPELINE.md`. The learner-facing React frontend consumes these authenticated APIs in the current RC.

## Interactive avatar tutors

Milestone 8 serves the typed React learner experience at `/`, with Ananya and Arjun as configuration-driven Indian-English tutors. The RC remediation gives Ananya a rigged Three.js tutor rendered in live-class framing, with analyser-driven mouth movement and accessible fallbacks; Arjun retains his configured portrait. The experience also includes guarded routes, session refresh/logout, consent-aware bounded browser microphone input, conversation coaching, optional Telugu preferences, progress and streaks, and a subscription-ready boundary. This engineering candidate does not authorize payment, deployment, or production release. Run `python examples/deterministic_tutor_experience.py` for the offline tutor-catalogue example. See `docs/AVATAR_TUTOR_EXPERIENCE.md`.

## Production infrastructure

Milestone 11 adds deterministic container builds, migration-gated PostgreSQL startup, Redis-backed distributed controls and jobs, private S3-compatible object storage, dependency-aware readiness, a same-origin PWA deployment, CI supply-chain checks, staging manifests, and operational runbooks. Start the local stack with `docker compose up --build`; registration is admitted only after the migration service completes. See `docs/PRODUCTION_READINESS.md`, `docs/STAGING_DEPLOYMENT.md`, and `docs/RUNBOOKS.md`.
