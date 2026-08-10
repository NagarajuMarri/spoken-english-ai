# Version 1.0 production go-live checklist

## Engineering release-candidate evidence

- [x] Product Milestone 12 approval evidence is retained as historical input.
- [x] Final RC automatable engineering gates have no known Sev-1 or Sev-2 defect.
- [x] Closed-beta admission, feedback, founder dashboard, trial, subscription, entitlement and progress workflows are implemented.
- [x] Core learner, accessibility, build, migration and browser gates passed.
- [x] Release notes, changelog, known issues and operating documentation are present.

## Required before production deployment

- [ ] Record explicit production-release and deployment approval.
- [ ] Complete the consolidated final founder device and end-user acceptance checklist.
- [ ] Approve final brand, legal text, pricing, beta cohort and production domain.
- [ ] Provision and independently verify each founder-dashboard account; do not treat the configured email allowlist or ordinary self-registration as verification.
- [ ] Configure and verify DNS, HTTPS, trusted hosts and production secrets.
- [ ] Verify loopback-only Nginx publication, the exact trusted host-ingress peer, sanitized client IP/proto forwarding, and rejection of spoofed forwarding headers.
- [ ] Verify bounded streamed STT uploads leave no persistent raw-audio proxy buffer, and verify the service-worker v2 reset-cache migration.
- [ ] Provision PostgreSQL, Redis, private object storage and worker services.
- [ ] Validate staging migration, immutable artifact, smoke tests, rollback and restore evidence.
- [ ] Configure monitoring, alerts, uptime checks, cost ceilings and incident ownership.
- [ ] Confirm support coverage and incident communications.
- [ ] Confirm mutating Playwright is prohibited against production and its disposable-target override is absent from production configuration.

## Payment and publication gates

- [ ] Obtain separate approval before enabling Razorpay production mode or real charges.
- [ ] Verify production webhook, idempotency, refund and reconciliation flows.
- [ ] Obtain separate approval before public publication or general availability.

## Current state

- Deployment: **NOT AUTHORIZED**
- Public release: **NOT AUTHORIZED**
- Razorpay production mode: **DISABLED**
Next gate: **final founder acceptance, followed by separate production-release approval**
