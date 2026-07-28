# Observability

Completion logs are JSON-compatible and contain timestamp, level, event name, request/correlation IDs, route, method, status, duration, service, and environment. Authentication and learner identifiers are included only where explicitly safe. Bodies, credentials, tokens, hashes, secrets, raw IP addresses, raw audio, and connection strings are prohibited.

Counters cover HTTP requests/errors, registrations, login outcomes, throttling, refresh rotation/reuse, voice sessions, lesson completion, and cleanup. Timings cover HTTP, authentication, lesson completion, and voice turns. Gauges cover active voice sessions, pending deletions, and active refresh tokens. The built-in metrics endpoint is development-only and disabled by default.

Critical refresh-reuse family revocation is fail-closed: revocation and the audit event commit before the public rejection. Other telemetry is best-effort and must never alter privacy-safe API messages.
