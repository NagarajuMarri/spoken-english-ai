# AI API

- `POST /api/v1/conversations/{id}/ai-turns`
- `POST /api/v1/voice-sessions/{session_id}/turns/{turn_id}/process`
- `GET /api/v1/voice-sessions/{session_id}/turns/{turn_id}/result`
- `GET|DELETE /api/v1/learners/{id}/memory`
- `GET /api/v1/learners/{id}/ai-usage`
- `POST /api/v1/learners/{id}/daily-plan/generate`

Voice processing requires `Idempotency-Key`. Responses contain validated learner-facing fields, request/correlation identifiers, processing status, and degraded-feature labels—not provider payloads or configuration.
