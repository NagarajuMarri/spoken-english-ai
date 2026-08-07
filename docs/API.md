# AI API

- `POST /api/v1/conversations/{id}/ai-turns`
- `POST /api/v1/voice-sessions/{session_id}/turns/{turn_id}/process`
- `GET /api/v1/voice-sessions/{session_id}/turns/{turn_id}/result`
- `GET|DELETE /api/v1/learners/{id}/memory`
- `GET /api/v1/learners/{id}/ai-usage`
- `POST /api/v1/learners/{id}/daily-plan/generate`

Voice processing requires `Idempotency-Key`. Responses contain validated learner-facing fields, request/correlation identifiers, processing status, and degraded-feature labels—not provider payloads or configuration.
# Voice input

`POST /api/v1/conversations/{conversation_id}/transcriptions` accepts an authenticated raw audio request (`audio/webm`, `audio/ogg`, `audio/mp4`, `audio/wav`, or `audio/mpeg`) with `X-Audio-Duration-Ms` and explicit `X-Voice-Processing-Consent: accepted`. It returns the normalized transcript, detected language, captured duration and byte count. Raw audio is transient request data and is not persisted by this endpoint.
