# API Contract

The API is JSON over HTTPS under a future `/v1` prefix; `/health` remains unversioned for operations. Clients send a request/correlation ID where supported. Errors will use a stable code, human-readable message, optional field details, and request ID. Breaking changes require a new version.

## Implemented endpoint

`GET /health` requires no external services and returns `200`:

```json
{
  "status": "healthy",
  "service": "spoken-english-ai",
  "version": "0.1.0"
}
```

## Milestone 2 resources

- `POST /api/v1/learners` creates a learner from `email` and `display_name`.
- `GET /api/v1/learners/{learner_id}` returns the profile.
- `PATCH /api/v1/learners/{learner_id}/onboarding` sets proficiency, learning goal, daily minutes, and native language.
- `GET /api/v1/scenarios` returns the eight deterministic scenario definitions.
- `POST /api/v1/conversations` starts a session from `learner_id` and `scenario_id`.
- `POST /api/v1/conversations/{conversation_id}/messages` accepts `text` and optional `include_telugu_explanation`.
- `GET /api/v1/conversations/{conversation_id}` returns the complete ordered transcript.

Errors use `{"error":{"code":"...","message":"...","details":[]?}}`. Stable codes cover missing resources, duplicate email, invalid onboarding selections, invalid daily goals, unsupported languages, and empty messages.

Message responses include tutor text, turn number, the persisted transcript entry, and an optional correction. The original learner text is never rewritten. Audio references, authentication, idempotency keys, pagination, and streaming protocols remain deferred.

## Milestone 3 resources

Curriculum is exposed at `/api/v1/curriculum/levels`, `/lessons`, and `/lessons/{lesson_id}`; learner selection at `/api/v1/learners/{id}/daily-lesson`; lesson sessions at `/api/v1/lesson-sessions`; and summaries at `/api/v1/learners/{id}/progress` and `/streak`. Lesson completion is idempotent and returns the stored evaluation.

## Milestone 4 resources

Consent uses `GET/PUT/DELETE /api/v1/learners/{id}/voice-consent`; voice practice uses `POST /api/v1/voice-sessions`, `GET /voice-sessions/{id}`, `POST /voice-sessions/{id}/turns`, and `POST /voice-sessions/{id}/complete`; `/api/v1/learners/{id}/daily-plan` is client-ready. Turn input is a safe simulated reference, not an upload, and synthetic assessment is clearly labeled.
## Authentication and ownership

`POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout`, `/logout-all`, and `GET /me` implement the authentication lifecycle. Access tokens are bearer JWTs; refresh tokens are opaque and rotate on every successful refresh. Reuse, expiry, invalid issuer, invalid audience, and inactive accounts produce structured authentication errors.

All learner-specific endpoints require authentication. A caller may address only the learner linked to their account and resources owned by that learner. Cross-account access consistently returns `404 resource_not_found`; anonymous access returns `401 authentication_required`. Public catalog and health endpoints remain anonymous.

Operational endpoints: `GET /health/live` never touches the database; `GET /health/ready` checks database and signing configuration and returns 503 when unavailable; `GET /health/version` returns non-sensitive build metadata. A disabled-by-default `/internal/metrics` exposes only the in-memory development snapshot. Rate-limited responses use `429 rate_limited` and a safe `Retry-After` header.
