# Operational runbooks

## Database unavailable

Keep the backend out of service. Check PostgreSQL reachability, connection saturation, TLS/DNS, and the migration job. Confirm `SELECT 1` and `alembic current`; never enable automatic table creation. Restore from the most recent verified backup only after preserving incident evidence.

## Migration incompatible

Stop rollout and leave the previous compatible image serving. Compare the reported revision with `0009_commercial_subscriptions`. Re-run the idempotent upgrade only after resolving the failed migration. Prefer a forward repair; rehearse any downgrade on a restored copy first.

## Redis or worker unavailable

Keep readiness failed when Redis is required or worker processing is enabled. Check Redis persistence, memory, connectivity, queue depth, dead-letter depth, and `spoken-english:worker:heartbeat`. Restart one worker at a time. Replaying work is safe only with its original idempotency key.

## Object storage unavailable

Block new audio work while preserving metadata. Check private-bucket access, endpoint/TLS, quota, retention rules, and scoped-reference expiry. Do not switch production to local disk. Resume cleanup and upload workers after a successful bucket health check.

## Credential exposure

Disable affected access, rotate provider/storage/database/JWT credentials, invalidate sessions when signing material is involved, search redacted logs and Git history, and document scope. Never paste the exposed value into the incident record.

## Rollback and restore

Pin the last known-good image digests and confirm its schema compatibility. Database restore requires a new isolated database, integrity checks, revision validation, and an approved cutover. Validate registration, authentication, learner ownership, and audit events after recovery.
