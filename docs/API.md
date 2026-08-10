# AI API

- `POST /api/v1/conversations/{id}/ai-turns`
- `POST /api/v1/conversations/{id}/ai-turns/{turn_id}/speech`
- `POST /api/v1/voice-sessions/{session_id}/turns/{turn_id}/process`
- `GET /api/v1/voice-sessions/{session_id}/turns/{turn_id}/result`
- `GET|DELETE /api/v1/learners/{id}/memory`
- `GET /api/v1/learners/{id}/ai-usage`
- `POST /api/v1/learners/{id}/daily-plan/generate`

Voice processing requires `Idempotency-Key`. AI tutor turns also accept this header; the browser sends one stable key per learner turn and reuses it for safe recovery. A completed retry returns the stored result without another provider call. Responses contain validated learner-facing fields, request/correlation identifiers, processing status, and degraded-feature labels—not provider payloads or configuration.

OpenAI responses that end at the configured output limit return `502 llm_incomplete_response` with `retryable: true`. The failed call's reported token usage is retained as failure usage, no tutor success is persisted, and a browser retry reuses the original turn identity. Genuinely malformed or schema-invalid provider output remains separately classified.

# Voice input

`POST /api/v1/conversations/{conversation_id}/transcriptions` accepts an authenticated raw audio request (`audio/webm`, `audio/ogg`, `audio/mp4`, `audio/wav`, or `audio/mpeg`) with `X-Audio-Duration-Ms` and explicit `X-Voice-Processing-Consent: accepted`. Clients should also send a stable `Idempotency-Key`; the server falls back to the request identity when it is omitted. The duration header is a bounded capture hint, not billing authority; successful quota accounting uses provider-reported duration and failed attempts retain a conservative reservation. A completed retry with the same key and audio returns the stored safe result without another provider call, while reuse with different audio is rejected. The response contains the normalized transcript, detected language, authoritative duration and byte count. Raw audio is transient request data and is never persisted; only its digest, idempotency/status metadata, safe result fields and charged duration are retained.

# Tutor speech

The authenticated speech endpoint synthesizes only the stored text of a completed tutor turn. Production requires OpenAI `gpt-4o-mini-tts`; Ananya and Arjun map to separately configured built-in voices. It returns binary MP3 (`audio/mpeg`) and safe evidence headers for provider, model, voice, cache status, input characters, provider-call count and usage classification. The first successful result is cached per AI turn, so replay does not create another paid provider request. OpenAI's binary speech response does not include token usage; SpeakMate therefore records characters and audio bytes without presenting an estimated charge as provider billing.

The browser uses an HTML audio element. If Chrome blocks autoplay, the learner must click Play tutor voice. Browser speech synthesis is not a production fallback.
