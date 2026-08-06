# SpeakMate Version 1.0 launch readiness

This repository contains Release Candidate 1 for a controlled individual-learner beta delivered as an installable PWA. It is not a public release or deployment authorization. Razorpay must remain in test mode and OpenAI is the only approved launch AI/STT/TTS provider family, behind existing cost and privacy controls.

## Release gates

- Founder approves final product name, icons, pricing, legal text, beta cohort and domain.
- Privacy, Terms, Refund/Cancellation, voice consent, retention/deletion, support and FAQ surfaces are reviewed.
- Registration, tutor selection, voice consent, learning path, progress, entitlements and session restoration pass RC acceptance.
- DNS, HTTPS, trusted hosts, CORS, secrets, monitoring, alerting, backup and restore are verified in staging.
- Razorpay configuration reports `test`; no real customer charge is permitted.
- OpenAI request, token, voice and monthly cost ceilings are configured and alertable.
- Exact RC SHA passes backend, frontend, accessibility, Playwright, migration, build, secret, dependency and PWA checks.

## Controlled beta and support

Closed beta is enabled by configuration. Invite enforcement must be enabled and reviewed before any external cohort is admitted. Feedback accepts bounded text only; users are instructed not to submit raw speech, credentials, payment data or secrets. Support requests use the configured address and privacy/deletion requests are separately classified.

## RC1 and rollback

RC1 evidence is bound to the feature-branch SHA. A human go/no-go is required after staging rehearsal. Rollback uses the last known-good image and compatible schema; restore is rehearsed on an isolated database before cutover. Deployment, public release and post-launch actions remain unauthorized in this milestone.
