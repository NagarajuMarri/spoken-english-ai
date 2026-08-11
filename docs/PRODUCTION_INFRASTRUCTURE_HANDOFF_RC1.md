# SpeakMate RC1 production infrastructure handoff

No provider or hosting purchase is implied by this handoff. Production deployment remains a separate approved operation.

## Runtime topology

- Backend: one ASGI container plus one worker container. Start the API with `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*` only behind the repository's trusted TLS ingress. Run the worker with `python -m backend.app.cli.worker`.
- Published Compose limits are 1 CPU/768 MiB for the API, 0.5 CPU/512 MiB for one worker, and 0.25 CPU/128 MiB for the frontend. Capacity testing must confirm these initial limits.
- Health endpoints are `/health/live`, `/health/ready`, and `/health/version`. Admit traffic only while readiness returns 200.
- Frontend: run `npm ci` and `npm run build` in `frontend`; publish `frontend/dist` with the supplied Nginx/container configuration. `VITE_API_BASE_URL` is build-time configuration; same-origin ingress/proxying is preferred.

## Database and migration

- Use a supported PostgreSQL release with TLS, automated backups, point-in-time recovery, and a dedicated least-privilege application role. SQLite is not a production database.
- `SPOKEN_ENGLISH_DATABASE_URL` must be a percent-encoded SQLAlchemy PostgreSQL URL such as `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require`.
- Run exactly one pre-release migration job: `alembic upgrade head`. Current RC head is `0019_realtime_turns`.
- Configure `SPOKEN_ENGLISH_DATABASE_POOL_SIZE`, `SPOKEN_ENGLISH_DATABASE_POOL_TIMEOUT_SECONDS`, and `SPOKEN_ENGLISH_DATABASE_CONNECT_TIMEOUT_SECONDS` within managed-database connection limits. The application enables pool pre-ping and recycles pooled connections.

## Required configuration groups

- Identity/security: `SPOKEN_ENGLISH_ENVIRONMENT=production`, `SPOKEN_ENGLISH_JWT_SECRET`, `SPOKEN_ENGLISH_JWT_ACTIVE_KEY_ID`, `SPOKEN_ENGLISH_JWT_VERIFICATION_KEYS_JSON`, issuer, audience, secure-cookie, HTTPS, trusted-host, trusted-proxy, build-identifier, beta-code/allowlist, and support-email settings.
- Public routing: `SPOKEN_ENGLISH_PUBLIC_FRONTEND_URL`, `SPOKEN_ENGLISH_PUBLIC_API_URL`, and an exact `SPOKEN_ENGLISH_CORS_ORIGINS` allowlist. Allocate separate canonical frontend and API DNS names or route `/api` same-origin. Both must use valid HTTPS; WebRTC microphone access requires a secure browser context.
- Realtime/OpenAI: `SPOKEN_ENGLISH_REALTIME_VOICE_ENABLED`, `SPOKEN_ENGLISH_OPENAI_API_KEY`, `SPOKEN_ENGLISH_OPENAI_REALTIME_MODEL`, `SPOKEN_ENGLISH_OPENAI_REALTIME_VOICE`, `SPOKEN_ENGLISH_OPENAI_STT_MODEL`, connect timeout, SDP byte limit, and the reviewed VAD threshold/prefix/silence settings. Never expose the standard OpenAI key to the browser.
- Redis/rate limiting: set `SPOKEN_ENGLISH_REDIS_URL` and `SPOKEN_ENGLISH_REDIS_REQUIRED=true` for distributed production enforcement.
- SMTP: set delivery provider to `smtp` and configure `SPOKEN_ENGLISH_SMTP_HOST`, port, username, password, timeout, and `SPOKEN_ENGLISH_PASSWORD_RESET_EMAIL_FROM`. Until verified, status is `PRODUCTION_SMTP_CONFIGURATION_REQUIRED`.
- Object storage: configure the object-storage backend, bucket, endpoint/region credentials, and retention policy when production audio storage is enabled.

## Network and browser requirements

- Terminate TLS at the approved ingress, overwrite untrusted forwarded headers, restrict the backend port to the private ingress path, and set `TRUSTED_INGRESS_CIDR` to that exact network.
- Permit outbound HTTPS from the API to OpenAI and SMTP/object-storage endpoints. Client networks must permit WebRTC/ICE traffic; current signaling is HTTPS through `/api/v1/realtime/calls`.
- Support current Chromium, Firefox, and Safari releases with microphone permission. Keep text and standard-voice degraded modes available.

## Operations

- Monitor API readiness, 5xx/429 rates, Realtime connect failures, reconnect exhaustion, transcript-analysis failures, provider latency p50/p95/max, silent/duplicate turns, worker queue depth, PostgreSQL connections/locks/storage, Redis availability, SMTP failures, and frontend error rate. Alerts must redact transcripts, tokens, and provider secrets.
- Back up PostgreSQL with encrypted daily full backups plus PITR/WAL retention appropriate to the recovery objectives. Test restore into an isolated environment and run integrity/readiness checks at least quarterly. Back up required object storage and deployment configuration separately.
- Roll back application containers to the prior immutable image. Prefer a forward database fix; use `alembic downgrade` only after validating that no post-migration data would be lost. Retain the previous frontend asset image for atomic rollback.
- Before release: restore a backup in staging, run migrations, verify readiness, execute smoke/auth/Realtime journeys, then promote immutable image digests. Never reuse acceptance secrets or disposable databases.
