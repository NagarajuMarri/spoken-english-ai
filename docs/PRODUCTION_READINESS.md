# Production readiness

Milestone 11 packages the modular application for repeatable staging review. It does not authorize a production deployment or any live AI provider.

## Runtime boundaries

- PostgreSQL is mandatory in production. Alembic owns schema creation; application startup never creates production tables.
- Redis is used for distributed rate limits, durable queued work, idempotency, retry/dead-letter handling, and worker heartbeats.
- Private S3-compatible storage holds temporary audio bytes. Relational records retain metadata and time-limited scoped references only.
- The web image serves the PWA and reverse-proxies same-origin `/api/` and `/health/` requests to the backend. Compose publishes it only on host loopback behind an approved same-host TLS ingress; the exact observed ingress peer is the only trusted forwarded-address source.
- The STT proxy route streams a bounded upload with buffering disabled. Nginx caps it at `10m`, the backend enforces 10,000,000 bytes, and read-only/tmpfs container storage prevents persistent raw-audio request buffering.
- Readiness checks schema revision `0018_opening_turns`, signing keys, configured providers, PostgreSQL, Redis, object storage, payment configuration, password-reset delivery, and the Redis worker heartbeat.

## Release sequence

1. Build immutable backend and frontend images tagged with the commit SHA.
2. Scan source, Python and npm dependencies, and both images. Record accepted findings.
3. Back up PostgreSQL and verify the restore checkpoint.
4. Render `docker compose --env-file .env.production -f compose.production.yaml config` and review it for secrets or unexpected ports.
5. Run the one-shot `migrate` service. Do not start application traffic if it fails.
6. Start worker, backend, and frontend; wait for `/health/ready` to return 200.
7. Run registration/login, one deterministic conversation, PWA installability, reset-cache migration, ingress anti-spoofing, and cleanup smoke tests. Mutating Playwright must target only an independently verified disposable environment, never production.
8. Promote only after human review. Roll back application images independently; use a forward database migration unless a tested downgrade is explicitly approved.

## Required staging evidence

Record image digests, migration revision, readiness response, rendered loopback port/trusted-ingress configuration, client-IP/proto anti-spoofing evidence, streamed-upload evidence, service-worker cache migration, smoke-test output, backup/restore drill result, vulnerability reports, operator and timestamp. Credentials, connection strings, reset tokens, and raw audio must not appear in evidence.
