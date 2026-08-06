# Version 1.0 production go-live checklist

## Approved release-candidate evidence

- [x] Product Milestone 12 received human approval.
- [x] RC audit is `RC1_READY` with no blocking issues.
- [x] Closed-beta admission, feedback, founder dashboard, trial, subscription, entitlement and progress workflows are implemented.
- [x] Core learner, accessibility, build, migration and browser gates passed.
- [x] Release notes, changelog, known issues and operating documentation are present.

## Required before production deployment

- [ ] Record explicit production-release and deployment approval.
- [ ] Approve final brand, legal text, pricing, beta cohort and production domain.
- [ ] Configure and verify DNS, HTTPS, trusted hosts and production secrets.
- [ ] Provision PostgreSQL, Redis, private object storage and worker services.
- [ ] Validate staging migration, immutable artifact, smoke tests, rollback and restore evidence.
- [ ] Configure monitoring, alerts, uptime checks, cost ceilings and incident ownership.
- [ ] Confirm support coverage and incident communications.

## Payment and publication gates

- [ ] Obtain separate approval before enabling Razorpay production mode or real charges.
- [ ] Verify production webhook, idempotency, refund and reconciliation flows.
- [ ] Obtain separate approval before public publication or general availability.

## Current state

Deployment: **NOT AUTHORIZED**  
Public release: **NOT AUTHORIZED**  
Razorpay production mode: **DISABLED**  
Next gate: **explicit production-release approval**
