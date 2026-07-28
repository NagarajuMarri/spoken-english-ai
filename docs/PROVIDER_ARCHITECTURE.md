# Provider Architecture

LLM, STT, TTS, and pronunciation capabilities use typed provider protocols. Deterministic providers are the default. OpenAI-compatible boundaries use dependency injection, configured models, timeouts, bounded retries, safe failure mapping, and structured-output validation. Tests use injected clients and never invoke live services.
