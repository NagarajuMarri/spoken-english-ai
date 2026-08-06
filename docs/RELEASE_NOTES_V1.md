# SpeakMate Version 1.0 RC1 release notes

Release candidate `v1.0.0-rc1` is the human-approved Version 1.0 product candidate for controlled review and production go-live preparation. It is not a deployment or public-release authorization.

## Learner experience

- Secure registration, login, session restoration, logout and owner-isolated learner data.
- Ananya and Arjun animated Indian-English tutors with tutor selection and settings.
- Daily lessons, text and consent-gated voice practice, grammar correction, vocabulary coaching, optional Telugu explanations and conversation memory.
- Detailed evidence-backed progress; unavailable scores are identified rather than invented.
- Responsive, keyboard-operable PWA experience with reduced-motion support.

## Controlled launch readiness

- Configuration-driven closed beta with invitation codes, allowlist, founder override, waiting list and customer-safe access messages.
- Authenticated feedback and a founder-authorized read-only launch dashboard.
- Free, trial, subscription and upgrade presentation with server-side entitlements and fair-use messaging.
- Razorpay remains in test mode; no real payment path is authorized.

## Operations and assurance

- PostgreSQL, Redis, private object-storage and worker boundaries; migrations through `0010_beta_launch_readiness`.
- Readiness, telemetry, security audit, backup, restore, rollback and incident-response guidance.
- RC audit: `RC1_READY`; 183 backend, 37 frontend and 7 deterministic Playwright tests passed.

## Release boundaries

- No deployment or public publication has occurred.
- Production domain, DNS, secrets, monitoring and final legal text still require go-live approval.
- Razorpay production mode and real charges remain disabled.
