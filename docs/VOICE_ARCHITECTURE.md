# Voice Architecture

## Provider-neutral flow

Client audio is recorded in bounded chunks or streamed through a future transport. An audio-ingress service validates format and duration, stores only when policy permits, and calls a speech-to-text interface. The normalized transcript enters the same conversation use case as typed text. Tutor text is optionally sent through a text-to-speech interface, and the client receives text plus an audio reference or stream.

Interfaces should expose provider-independent requests, results, confidence, language hints, timing, and error categories. Adapters translate these to vendors. LLM, speech-to-text, and text-to-speech providers are all `disabled` in Milestone 1.

## Reliability

- Text fallback is always available.
- Timeouts, retries, cancellation, quotas, and circuit breaking live outside domain logic.
- Low confidence triggers clarification and is excluded from pronunciation scoring.
- Correlation IDs connect audio, transcript, turn, and feedback without exposing provider details.
- Web and mobile clients use the same API contract.

## Privacy and cost controls

Require explicit microphone permission and clear recording state. Default to deleting raw audio after transcription unless a learner explicitly opts into retention for review. Enforce duration and size limits, redact sensitive logs, and make provider region/retention terms a launch criterion.

