# Security and Privacy

## Baseline

Collect the minimum identity and learning data needed. Secrets come only from environment-backed secret management and are never committed or logged. Use TLS in transit, encryption at rest, least-privilege service/database roles, dependency scanning, structured audit events, and generic external errors.

Treat voice, transcripts, Telugu explanations, learner level, and progress as personal data. Obtain explicit microphone permission, visibly indicate recording, state why audio is used, and default to deleting raw audio after transcription. The production STT path streams at most Nginx `10m` to a backend that enforces 10,000,000 bytes; request buffering is disabled and Nginx writable paths are tmpfs, so raw captures do not persist to proxy disk. Provide retention, export, correction, and deletion workflows before production.

Never send credentials or unnecessary identity data to AI/speech providers. Contractually verify provider training, retention, residency, deletion, and subprocessor behavior. Redact logs and assign short retention periods.

## Safety

Doctor Visit is language practice, not medical advice. Content needs abuse and self-harm escalation rules before broad release. Users aged 12–17 require an age-aware launch design, parental/guardian and jurisdiction review, and stricter defaults; the MVP foundation does not claim compliance for child-directed use.

Threat modeling, authentication, authorization, rate limiting, abuse prevention, backup/restore testing, incident response, and a privacy impact assessment are release gates, not Milestone 1 implementations.

## Voice consent and lifecycle

Consent changes are append-only records with policy version and timestamps. Processing and storage consent are distinct. Simulated media types are restricted, unsafe/traversal references are rejected, and errors expose no secrets. Production requires authenticated ownership, confirmed object deletion, background retries, monitoring, and provider legal/security review.
## Authentication controls

Passwords are hashed with bcrypt and must meet the configured minimum length. JWT access tokens validate signature, algorithm, expiration, issuer, audience, subject, and token type. Signing secrets come from deployment environment configuration and must be high-entropy and rotated through an operational secret manager.

Refresh tokens are random opaque values, stored only as SHA-256 hashes, and linked by a family identifier plus a unique parent. Rotation locks the source row on PostgreSQL, revokes it, and creates exactly one replacement. Reuse of a replaced token revokes every active family descendant and records a durable security event, requiring login again. SQLite tests verify constraints and sequential behaviour but do not model PostgreSQL row-lock concurrency.

Passwords have configured minimum length and a 72-byte maximum so bcrypt never silently truncates input. Validation error details omit submitted values. Login errors are generic; throttling uses both a normalized-email hash and a privacy-minimized network hash. Tests use deterministic in-memory counters; production configuration uses the Redis-backed limiter.

Password-recovery requests return the same public response for known and unknown emails and apply a bounded minimum response-time floor to reduce lookup timing leakage. Production requests enqueue idempotent work over TLS-protected Redis and never perform SMTP or mail-provider DNS/TLS calls on the HTTP request path. The separately deployed worker uses authenticated STARTTLS, bounded retries, restart-recoverable in-flight work, success/failure audit events, and a scrubbed dead-letter record; terminal delivery failure invalidates the reset token. Reset tokens are cryptographically random, stored only as SHA-256 hashes in the database, short-lived, rate-limited by both token and privacy-minimised network keys, and single-use. A successful password change updates the bcrypt hash, consumes all outstanding reset tokens, revokes all refresh sessions, and records an audit event in one transaction. Production fails closed unless TLS-protected Redis throttling, the worker, a non-placeholder SMTP sender, and an HTTPS frontend URL are configured; development may use only the mode-0600 local outbox, which is excluded from version control. SMTP telemetry and delivery audits contain only bounded provider outcome, latency, safe error class, and non-secret database references—never recipient, reset URL, raw token, credentials, or message content. Reset tokens use a URL fragment, are scrubbed from browser history before validation, and are excluded from service-worker caching and Nginx access logging. Service-worker cache generation `spoken-english-shell-v2` deletes older cache generations when it activates and bypasses `/reset-password`; existing tabs must receive and activate the new worker during rollout. Submitted passwords are never logged. Real provider credentials, sender-domain verification, worker health, and controlled-mailbox delivery remain deployment acceptance gates.

Ownership checks use a privacy-safe `404` for cross-user resources. User-agent metadata is bounded; raw IP addresses are not stored. Redis-backed production throttling, key rotation, audit logging, HTTPS enforcement, and token-family reuse response are implemented boundaries. Production still requires deployment verification, secret-rotation rehearsal, and an owner decision on breached-password screening.

The public network boundary is the approved host TLS ingress. The application Nginx port is loopback-published only. The ingress replaces client-supplied forwarding headers; Nginx trusts only its exact observed peer, normalizes the client address, overwrites forwarded IP headers for the backend, and supplies canonical `https`. A broad `TRUSTED_INGRESS_CIDR` would turn attacker-controlled headers into rate-limit identity and is prohibited.

Founder dashboard authorization is deliberately two-part: the signed-in account's normalized email must be configured in `SPOKEN_ENGLISH_FOUNDER_EMAILS`, and its persisted `email_verified` flag must already be true. Configuration alone grants no dashboard access. Self-registration leaves the flag false, and this RC exposes no public email-verification flow; founder verification therefore requires a separate, identity-checked and audited provisioning procedure outside learner-facing APIs.

JWTs carry an explicit `kid`. New tokens use the configured active symmetric key; configured previous keys verify older tokens. Unknown keys and unexpected algorithms are rejected. Tokens without `kid` use only the documented `legacy` migration key. Keys never appear in probes, logs, metrics, or API payloads.

Logs never include request bodies, authorization headers, passwords, tokens, hashes, audio, connection strings, or signing keys. Network identifiers are one-way privacy-minimized before throttling or audit persistence.
