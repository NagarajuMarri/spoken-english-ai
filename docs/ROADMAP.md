# Roadmap

## Milestone 1 — MVP foundation

Product decisions, modular-monolith architecture, provider boundaries, repository layout, configuration, health endpoint, and automated tests.

## Milestone 2 — Text learning loop

Implemented: learner identity/profile foundation, proficiency onboarding, SQLAlchemy/Alembic persistence, eight scenarios, deterministic text conversations, transcript persistence, priority correction rules, Telugu-on-request explanations, and basic progress records. Curated daily lesson selection and streak calculation move to the next learning-focused increment.

## Milestone 3 — Daily curriculum, progress, and provider boundaries

Implemented: five-level curriculum, deterministic selection, lesson sessions, transparent evaluation, UTC streaks/progress, provider protocols/local doubles, and hardened turn sequencing.

## Milestone 4 — Experience and provider evaluation

Daily-plan client contracts, curriculum expansion, score calibration, audio consent/retention lifecycle, and sandbox provider evaluations before choosing production vendors.

Milestone 4 delivers the daily-plan contract, append-only consent, simulated voice sessions, metadata lifecycle, and synthetic pronunciation boundary. Milestone 5 should add authentication/authorization, signed-upload design, durable deletion jobs, privacy assessment, and provider sandbox benchmarks.

## Milestone 4 — Client MVP and subscriptions

Responsive web client, mobile-ready API, voice UX, accessibility, entitlement enforcement, payment sandbox, analytics, and secure account lifecycle.

## Milestone 5 — Learning efficacy and scale

Placement support, adaptive practice, spaced review, safety evaluation, learner experiments, native mobile decisions, operational hardening, and broader language research.

Each milestone requires privacy, accessibility, reliability, learning-quality, and cost review. Multiple Indian languages, social features, live tutors, and institutional dashboards remain later hypotheses.
## Milestone 5 — Authentication, Ownership and API Security

Implemented email/password accounts, bcrypt, JWT access tokens, hashed rotating refresh tokens, account status enforcement, login throttling interface, privacy-safe ownership checks, and authentication migrations. Deferred: social login, email delivery, password reset, MFA, distributed abuse controls, and production identity verification.

Recommended next: Milestone 6 — production operations and observability, including distributed throttling, audit events, secret rotation, structured security telemetry, and deployment hardening.

## Milestone 6 — Production Operations, Audit and Observability

Implemented structured request context/logging, durable security events, readiness probes, metrics/rate-limit interfaces, signing-key rotation, operational errors, deterministic cleanup jobs, and internal administrative services. Next recommended: Milestone 7 — production infrastructure validation, PostgreSQL/Redis integration tests, incident runbooks, backup/restore drills, and release automation.

## Product Milestone 7 — Provider-Neutral AI Conversation and Voice Tutor

Implemented validated provider contracts, deterministic LLM/STT/TTS/synthetic-pronunciation providers, injected OpenAI-compatible boundaries, adaptive feedback policy, learner memory, usage controls, idempotent voice orchestration, authenticated APIs, migrations, examples, and privacy documentation.

Next: Product Milestone 8 — Learner Web Experience and Accessible Voice Practice.
