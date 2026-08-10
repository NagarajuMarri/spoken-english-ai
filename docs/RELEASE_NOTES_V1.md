# SpeakMate Version 1.0 RC1 release notes

Release candidate `v1.0.0-rc1` is the engineering-validated Version 1.0 candidate awaiting consolidated founder acceptance. It is not a deployment, public-release, or production-payment authorization.

## Learner experience

- Secure registration, login, session restoration, logout and owner-isolated learner data.
- Ananya as a rigged real-time 3D Indian-English tutor with analyser-driven speaking motion, plus the configured Arjun portrait, tutor selection, and settings.
- Daily lessons, text and consent-gated voice practice, grammar correction, vocabulary coaching, optional Telugu explanations and conversation memory.
- Focused Voice mode now presents a live-class surface with the current exchange and compact history, while Text mode keeps the fuller conversation; switching preserves messages, corrections, lesson context, and tutor audio without replaying or duplicating it.
- Provider/model/audio diagnostics are hidden from ordinary learner surfaces and remain behind an explicit engineering diagnostics boundary.
- Detailed evidence-backed progress; unavailable scores are identified rather than invented.
- Responsive, keyboard-operable PWA experience with reduced-motion support.

## Controlled launch readiness

- Configuration-driven closed beta with invitation codes, allowlist, founder override, waiting list and customer-safe access messages.
- Authenticated feedback and a founder-authorized read-only launch dashboard.
- Free, trial and subscription presentation backed by persisted expiry and server-side conversation, voice, tutor-request, token, and cost ceilings; upgrade remains an explicitly non-charging test preview.
- Razorpay remains in test mode; no real payment path is authorized.

## Operations and assurance

- PostgreSQL, Redis, private object-storage and worker boundaries; migrations through `0018_opening_turns`.
- Readiness, telemetry, security audit, backup, restore, rollback and incident-response guidance.
- The final RC remediation audit is recorded as engineering verification only after all local gates pass and the exact commit is pushed; founder final acceptance remains required.

## Release boundaries

- No deployment or public publication has occurred.
- Production domain, DNS, secrets, monitoring and final legal text still require go-live approval.
- Razorpay production mode and real charges remain disabled.
- Subjective 3D naturalness, physical microphone/speaker behavior, live-provider voice and latency, and real password-reset mailbox delivery remain founder/staging gates.
