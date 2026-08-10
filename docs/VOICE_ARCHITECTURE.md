# Voice Architecture

## Provider-neutral flow

Client audio is recorded with `getUserMedia` and `MediaRecorder` in bounded chunks. Stopping produces one non-empty Blob that is uploaded as the raw request body to the authenticated conversation transcription endpoint. Audio ingress validates ownership, media type, duration and size, calls the configured speech-to-text interface, and does not retain the raw request body. The normalized transcript is displayed to the learner and enters the same conversation use case as typed text. Privacy-minimised transcription-attempt rows retain an audio digest, idempotency identity, safe status/result metadata and charge duration for replay and quota accounting; they never retain audio bytes.

Interfaces should expose provider-independent requests, results, confidence, language hints, timing, and error categories. Adapters translate these to vendors. LLM, speech-to-text, and text-to-speech providers are all `disabled` in Milestone 1.

## Reliability

- Text fallback is always available.
- Timeouts, retries, cancellation, quotas, and circuit breaking live outside domain logic.
- Low confidence triggers clarification and is excluded from pronunciation scoring.
- Correlation IDs connect audio, transcript, turn, and feedback without exposing provider details.
- Web and mobile clients use the same API contract.

## Privacy and cost controls

Require explicit microphone permission and clear recording state. Default to deleting raw audio after transcription unless a learner explicitly opts into retention for review. Enforce duration and size limits, redact sensitive logs, and make provider region/retention terms a launch criterion.

The production configuration fails closed unless speech-to-text is `openai` with an injected API key. The fake implementation is a local/test double only and is never acceptance evidence for transcription quality. No audio is stored in relational tables or application logs.

## Browser behavior

Current Chrome on Windows supports microphone capture on `http://localhost` and `http://127.0.0.1` because browsers treat loopback origins as secure contexts. Non-loopback environments require HTTPS. The UI exposes permission, recording, processing, denied, empty-capture, cancelled, oversized and provider-error states; text entry remains available in every failure state.

## Consent-aware simulated workflow

Active versioned processing consent is required. Storage consent is separate: assets are `TEMPORARY` with configurable expiry or `RETAINED`; withdrawal blocks processing and marks outstanding metadata `PENDING_DELETION`; cleanup moves it to `DELETED`. No raw bytes are stored. Fake pronunciation always reports `assessment_type: synthetic_test_double` and never enters progress.
