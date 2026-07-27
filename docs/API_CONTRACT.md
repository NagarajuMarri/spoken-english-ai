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

## Planned MVP resources

- `POST /v1/learners` and `GET/PATCH /v1/learners/{id}/profile`
- `GET /v1/lessons/daily?level=...`
- `POST /v1/conversations`, `POST /v1/conversations/{id}/turns`, and `POST /v1/conversations/{id}/complete`
- `GET /v1/conversations/{id}` for transcript and summary
- `GET /v1/learners/{id}/progress`
- `GET /v1/learners/{id}/entitlements`

Turn requests accept `text` or a future uploaded/streamed audio reference and include client turn IDs for idempotency. Responses carry tutor text, optional speech reference, correction checkpoint, and usage metadata. Authentication, pagination details, and streaming protocols are intentionally deferred.

