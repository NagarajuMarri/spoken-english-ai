# Version 1.0 changelog

## v1.0.0-rc1 — 2026-08-07

### Added

- Secure individual learner accounts, session lifecycle and owner isolation.
- Animated Indian-English tutors, lessons, conversation coaching, Telugu guidance and consent-aware voice practice.
- Provider-neutral AI, speech, pronunciation, TTS and avatar boundaries with deterministic adapters.
- Evidence-backed progress, streak, activity, goal, achievement and conversation-history reporting.
- Plans, trials, entitlements, usage limits and Razorpay test-mode commercial safeguards.
- Installable responsive PWA plus landing, pricing, FAQ, support and draft legal pages.
- Closed-beta invitation, allowlist, founder override and waiting-list controls.
- Durable feedback and a founder-authorized read-only launch dashboard.
- PostgreSQL, Redis, private object storage, worker, readiness, telemetry, backup, restore and rollback foundations.
- Alembic revisions through `0010_beta_launch_readiness`.

### Security and privacy

- Added password hashing, bounded JWT sessions, refresh-reuse response, throttling, audit events and privacy-safe errors.
- Added explicit voice consent, minimization, retention and deletion boundaries.
- Kept provider credentials, payment secrets and production controls environment-driven and fail-closed.

### Verification

- 183 backend tests, 37 frontend tests and 7 deterministic Playwright scenarios passed.
- Ruff, TypeScript, ESLint, production build, migration and npm dependency audit passed.

### Known limitations

- Pronunciation guidance remains synthetic/non-acoustic unless validated provider evidence exists.
- Legal text requires final legal approval.
- Production deployment, public publication and real payments are not authorized.
