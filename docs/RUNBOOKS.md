# Operational runbooks

## Database unavailable

Keep the backend out of service. Check PostgreSQL reachability, connection saturation, TLS/DNS, and the migration job. Confirm `SELECT 1` and `alembic current`; never enable automatic table creation. Restore from the most recent verified backup only after preserving incident evidence.

## Migration incompatible

Stop rollout and leave the previous compatible image serving. Compare the reported revision with `0018_opening_turns`. Re-run the idempotent upgrade only after resolving the failed migration. Prefer a forward repair; rehearse any downgrade on a restored copy first.

### Local SQLite database created before Alembic

If `/health/ready` reports `migration: incompatible` even though `alembic current` prints the head revision, do not use `alembic stamp head`. Preserve the database if it contains useful local work, then inspect it for the authentication columns `learners.user_account_id`, `refresh_tokens.family_id`, and `refresh_tokens.parent_token_id`.

For a disposable development database, stop the backend, move `spoken_english_ai.db` to a dated backup outside the application path, run `alembic upgrade head` to create a new empty database, and re-run registration, logout, login, and session restoration. For a database containing data that must be retained, restore a copy in isolation and build a reviewed forward data migration; never mark an incompatible schema current by stamping it.

## Redis or worker unavailable

Keep readiness failed when Redis is required or worker processing is enabled. Check Redis persistence, memory, connectivity, queue depth, dead-letter depth, and `spoken-english:worker:heartbeat`. Restart one worker at a time. Replaying work is safe only with its original idempotency key.

## Object storage unavailable

Block new audio work while preserving metadata. Check private-bucket access, endpoint/TLS, quota, retention rules, and scoped-reference expiry. Do not switch production to local disk. Resume cleanup and upload workers after a successful bucket health check.

## Ingress identity or scheme incorrect

Remove the service from traffic. Confirm the frontend is published only as `127.0.0.1:8080`, the approved host TLS ingress is the sole caller, and it replaces inbound forwarded-address/proto headers. Determine the source address Nginx actually observes for that ingress and compare it with the rendered `set_real_ip_from`; use one exact `/32` or `/128`, not a broad Docker/private range. Confirm Nginx overwrites backend `X-Real-IP` and `X-Forwarded-For` with normalized `$remote_addr` and sends `X-Forwarded-Proto: https`. Re-test through the ingress with a forged client header before restoring traffic. Do not solve lost client attribution by trusting all proxies.

## Voice upload buffering or size mismatch

Stop new voice work if raw requests appear in persistent storage or memory pressure is unsafe. Confirm the transcription location has `client_max_body_size 10m`, `proxy_request_buffering off`, and HTTP/1.1 upstream proxying; confirm the backend limit is 10,000,000 bytes. Verify the frontend root filesystem is read-only and `/tmp` plus `/var/cache/nginx` are tmpfs. Treat tmpfs as transient sensitive memory, not retained storage. Preserve metadata-only evidence, never a learner's raw recording.

## Password-reset cache migration

After deploying service-worker cache generation `spoken-english-shell-v2`, close every tab controlled by the old worker and then reopen the application; an ordinary reload may download the new worker but does not guarantee that a waiting worker activates. Verify activation removes `spoken-english-shell-v1` and other old cache generations, `/reset-password` is absent from Cache Storage, Nginx returns `Cache-Control: no-store`, and reset navigations are not access-logged. If an old worker remains, keep reset traffic paused while affected clients unregister it or clear site data; never collect a reset URL or token as troubleshooting evidence.

## Mutating Playwright target refused

Treat refusal as a safety control, not a test failure to bypass. Verify `PLAYWRIGHT_BASE_URL`, `VITE_API_PROXY_TARGET`, and `/health/version`. Local development/test targets need no remote override. A non-loopback disposable development/test/staging target requires the exact acknowledgement `SPEAKMATE_ALLOW_DISPOSABLE_E2E_TARGET=I_ACCEPT_DISPOSABLE_TEST_DATA`. Production is forbidden even with that value. Never change a production environment label, copy the override into production, or run live registration/password-reset acceptance against real learner data.

## Credential exposure

Disable affected access, rotate provider/storage/database/JWT credentials, invalidate sessions when signing material is involved, search redacted logs and Git history, and document scope. Never paste the exposed value into the incident record.

## Rollback and restore

Pin the last known-good image digests and confirm its schema compatibility. Database restore requires a new isolated database, integrity checks, revision validation, and an approved cutover. Validate registration, authentication, learner ownership, and audit events after recovery.
