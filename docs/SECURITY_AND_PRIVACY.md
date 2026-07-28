# Security and Privacy

## Baseline

Collect the minimum identity and learning data needed. Secrets come only from environment-backed secret management and are never committed or logged. Use TLS in transit, encryption at rest, least-privilege service/database roles, dependency scanning, structured audit events, and generic external errors.

Treat voice, transcripts, Telugu explanations, learner level, and progress as personal data. Obtain explicit microphone permission, visibly indicate recording, state why audio is used, and default to deleting raw audio after transcription. Provide retention, export, correction, and deletion workflows before production.

Never send credentials or unnecessary identity data to AI/speech providers. Contractually verify provider training, retention, residency, deletion, and subprocessor behavior. Redact logs and assign short retention periods.

## Safety

Doctor Visit is language practice, not medical advice. Content needs abuse and self-harm escalation rules before broad release. Users aged 12–17 require an age-aware launch design, parental/guardian and jurisdiction review, and stricter defaults; the MVP foundation does not claim compliance for child-directed use.

Threat modeling, authentication, authorization, rate limiting, abuse prevention, backup/restore testing, incident response, and a privacy impact assessment are release gates, not Milestone 1 implementations.

## Voice consent and lifecycle

Consent changes are append-only records with policy version and timestamps. Processing and storage consent are distinct. Simulated media types are restricted, unsafe/traversal references are rejected, and errors expose no secrets. Production requires authenticated ownership, confirmed object deletion, background retries, monitoring, and provider legal/security review.
## Authentication controls

Passwords are hashed with bcrypt and must meet the configured minimum length. JWT access tokens validate signature, algorithm, expiration, issuer, audience, subject, and token type. Signing secrets come from deployment environment configuration and must be high-entropy and rotated through an operational secret manager.

Refresh tokens are random opaque values, stored only as SHA-256 hashes, and linked by a family identifier plus a unique parent. Rotation locks the source row on PostgreSQL, revokes it, and creates exactly one replacement. Reuse of a replaced token revokes every active family descendant and records a durable security event, requiring login again. SQLite tests verify constraints and sequential behaviour but do not model PostgreSQL row-lock concurrency.

Passwords have configured minimum length and a 72-byte maximum so bcrypt never silently truncates input. Validation error details omit submitted values. Login errors are generic; throttling uses both a normalized-email hash and a privacy-minimized network hash, and successful login resets both in-memory counters.

Ownership checks use a privacy-safe `404` for cross-user resources. User-agent metadata is bounded; raw IP addresses are not stored. Before production, replace in-memory throttling with a distributed rate limiter, add secret rotation procedures, audit logging, HTTPS enforcement, breached-password screening, and token-family reuse response.

JWTs carry an explicit `kid`. New tokens use the configured active symmetric key; configured previous keys verify older tokens. Unknown keys and unexpected algorithms are rejected. Tokens without `kid` use only the documented `legacy` migration key. Keys never appear in probes, logs, metrics, or API payloads.

Logs never include request bodies, authorization headers, passwords, tokens, hashes, audio, connection strings, or signing keys. Network identifiers are one-way privacy-minimized before throttling or audit persistence.
