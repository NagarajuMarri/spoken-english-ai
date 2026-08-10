# Staging deployment package

This package is deliberately provider-neutral and does not deploy itself. Operators supply private PostgreSQL, Redis, and S3-compatible endpoints plus immutable image references through a secret store.

```sh
cp .env.production.example .env.production
docker compose --env-file .env.production -f compose.production.yaml config
docker compose --env-file .env.production -f compose.production.yaml run --rm migrate
docker compose --env-file .env.production -f compose.production.yaml up -d worker backend frontend
curl --fail https://STAGING_HOST/health/ready
```

Replace every placeholder, keep `.env.production` outside version control, restrict backend/storage/database/Redis to private networks, and record the evidence listed in `PRODUCTION_READINESS.md`. Stop after staging validation and wait for human promotion approval.

## Ingress topology and forwarded identity

Compose publishes the Nginx container only as `127.0.0.1:8080`; it is not a public HTTP listener. An approved TLS ingress on the same host must own the public HTTPS socket and proxy to that loopback address. Do not expose container port 8080 on `0.0.0.0`, publish the backend, or use the loopback listener as a general non-TLS endpoint: the application proxy deliberately forwards the canonical scheme as `https`.

The host ingress must replace, not append to, Internet-supplied `X-Forwarded-For`, and must derive the client address from its accepted connection. It must also accept public application traffic only over TLS and discard any client-supplied forwarded-proto value. Set `TRUSTED_INGRESS_CIDR` to the single exact peer address Nginx observes for that approved ingress (`/32` for IPv4 or `/128` for IPv6). The example `127.0.0.1/32` is valid only when the container actually observes that address; Docker NAT may present a host-gateway address instead. Never use `0.0.0.0/0`, `::/0`, a whole Docker subnet, or an unverified private range. Render the container template and verify the resolved value before traffic.

Nginx accepts forwarded client identity only from that peer, resolves it to `$remote_addr`, then overwrites both `X-Real-IP` and `X-Forwarded-For` before the private backend hop. It overwrites `X-Forwarded-Proto` with `https`. Capture a staging request through the approved ingress and verify the backend's privacy-minimised rate-limit identity changes for distinct test clients without trusting a spoofed inbound header.

## Voice upload boundary

Only the authenticated conversation-transcription route receives the Nginx `10m` body ceiling, HTTP/1.1 streaming, and `proxy_request_buffering off`. The backend applies the tighter exact default of 10,000,000 bytes. The Nginx filesystem is read-only and its temporary/cache paths are memory-backed, so raw STT request bodies are not persistently buffered to container disk. The backend processes the bounded body transiently and persists only privacy-minimised attempt metadata, never raw audio. Verify these settings on the rendered image; they are not a substitute for ingress request/time limits and memory monitoring.

## Mutating browser acceptance

Live registration, authentication, and password-reset Playwright scenarios create accounts, waitlist entries, sessions, and reset records. Their default target is loopback. A non-loopback disposable target additionally requires `SPEAKMATE_ALLOW_DISPOSABLE_E2E_TARGET=I_ACCEPT_DISPOSABLE_TEST_DATA`, and `/health/version` must report `development`, `test`, or `staging`. A target reporting `production` is rejected even when the override is present. The override is acknowledgement of disposable test data, not deployment authorization; never store it in production configuration or point these scenarios at production. Independently verify `PLAYWRIGHT_BASE_URL` and any `VITE_API_PROXY_TARGET` before enabling a `LIVE_*_ACCEPTANCE` flag.
