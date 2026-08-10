# Administrator guide

Administrators must manage configuration through secrets/environment controls, keep Razorpay in test mode until separately approved, configure OpenAI ceilings, review `/health/ready`, monitor authentication/rate-limit/worker signals, and perform backup/restore rehearsals. The RC provides a founder-authorized read-only launch dashboard with configuration-backed commercial estimates; operational dependency health remains authoritative only at `/health/ready`. Engineering acceptance does not authorize deployment or replace the final founder and staging gates.

## Founder dashboard provisioning

`SPOKEN_ENGLISH_FOUNDER_EMAILS` is an allowlist, not proof of identity and not an account-provisioning mechanism. Dashboard access requires both an authenticated account whose normalized email is in that configuration and `user_accounts.email_verified = true`. Ordinary self-registration, including registration by an allowlisted founder email, creates an unverified account and cannot access the dashboard.

This RC has no public email-verification link or endpoint. Provision the founder account, or independently mark an existing account verified, only through a reviewed operator/data-migration procedure with identity confirmation, least-privilege database access, and audit evidence. Never bulk-verify learners, infer verification from possession of an invitation code, or describe the password-reset flow as email verification. Remove both the configured allowlist entry and authenticated sessions when revoking founder access.
