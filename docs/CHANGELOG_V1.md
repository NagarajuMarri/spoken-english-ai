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
- Alembic revisions through `0018_opening_turns`.

### Security and privacy

- Added password hashing, bounded JWT sessions, refresh-reuse response, throttling, audit events and privacy-safe errors.
- Added explicit voice consent, minimization, retention and deletion boundaries.
- Kept provider credentials, payment secrets and production controls environment-driven and fail-closed.
- Added refresh single-flight protection, fragment-only password-reset tokens, reset-route cache/log exclusion, and production browser security headers.

### Final RC hardening

- Made migration readiness use the actual Alembic head and fixed worker-heartbeat readiness.
- Connected persisted subscriptions to configuration-backed entitlements, trial expiry, runtime limits, and honest test-upgrade presentation.
- Replaced hard-coded launch progress, registration, pricing, and health claims with evidence-backed values or the authoritative readiness endpoint.
- Added live-account Playwright configuration that uses isolated, unique test identities and an explicit beta invitation.

### Founder-acceptance learner UX hardening — 2026-08-10

- Split the conversation screen into focused Voice mode and fuller Text mode without remounting or resetting the shared conversation.
- Made Voice mode show one current learner/tutor exchange, compact prior history, concise tutor state, useful correction/Telugu guidance only when present, and a unified microphone/audio control dock.
- Removed learner-facing provider, model, voice, audio-path, internal review, avatar lifecycle, and other engineering metadata; explicit diagnostics remain available only at the component diagnostics boundary.
- Preserved stable message identities and a single mounted tutor-audio player across mode changes to prevent duplicate messages, speech requests, or autoplay.
- Added responsive mobile/desktop Playwright coverage plus accessibility, replay, lesson-context, and mode-switch regression coverage.

### Founder-acceptance runtime remediation — 2026-08-10

- Added a bundled, provenance-recorded rigged 3D Ananya model, Three.js renderer, lightweight 3D and portrait fallbacks, reduced-motion support, initialization telemetry, and real playback-amplitude jaw/viseme movement.
- Made the server own one idempotent opening tutor turn and made the browser speak it exactly once after the honest autoplay gesture gate; later replies auto-play without remounting the audio player.
- Added generalized Unicode/grapheme and writing-system validation before learner persistence and before tutor output persistence, API presentation, or TTS.
- Added privacy-safe T0–T8 conversational-latency instrumentation, bounded server stage metrics, and browser-readable `Server-Timing`; non-streaming first output is labeled as complete-response delivery rather than claimed as token streaming.
- Added production SMTP configuration, Redis-worker delivery with bounded retries, neutral request timing, and secure failure handling for password recovery; real mailbox delivery remains an external acceptance gate.
- Added revision `0018_opening_turns` so opening attempts are distinguished from learner turns and excluded from daily learner AI quotas.

### Verification

- 351 backend tests, 105 frontend tests and 11 deterministic Playwright scenarios passed; 4 live-environment scenarios remain intentionally gated.
- Ruff, TypeScript, ESLint, production build, migration and npm dependency audit passed.

### Known limitations

- Pronunciation guidance remains synthetic/non-acoustic unless validated provider evidence exists.
- Legal text requires final legal approval.
- Production deployment, public publication and real payments are not authorized.
