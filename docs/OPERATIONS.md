# Operations

Run `python -m backend.app.cli.cleanup_audio` from a scheduler. Cleanup orders eligible assets by creation time and ID, respects the configured batch size, records confirmation time, and is idempotent. Retry count and bounded failure reason are reserved for storage-adapter failures.

Internal `AdministrativeService` supports account disable/lock/unlock, session revocation, audit inspection by user/time, and pending-audio inspection. It is not exposed as an unauthenticated or learner HTTP API.

Incident signals include login throttling, access-token rejection, refresh reuse/family revocation, blocked cross-user access, readiness failure, pending deletion growth, and cleanup failures.

AI signals include provider latency/failure/retry, consent and usage blocks, degraded results, voice-turn success/failure, memory updates, and generated-audio lifecycle events. Provider exception text, prompts, transcripts, and credentials are excluded from logs and audits.
