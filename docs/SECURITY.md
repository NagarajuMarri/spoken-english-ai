# AI Security

All learner AI endpoints require authentication and ownership. Provider output is untrusted and validated. Stable idempotency keys prevent replay duplication. Provider timeouts and failures map to privacy-safe errors without raw exception text. Live-provider configuration must be injected and is never required for startup or tests.
