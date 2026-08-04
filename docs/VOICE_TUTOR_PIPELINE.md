# Voice Tutor Pipeline

The authenticated pipeline checks ownership, active processing consent, audio state, rate and usage limits, then runs STT, validated AI generation, synthetic pronunciation assessment, memory update, usage persistence, and optional TTS.

STT and AI failures are fatal and retryable. Pronunciation or TTS failures produce a labelled degraded success. Replays with the same turn and idempotency key return the stored result without duplicate provider, memory, usage, or audit records. Raw audio is never stored in relational columns.
