# Production Provider Sandbox

Product Milestone 9 implements only the evaluation sandbox defined by approved plan
`spoken-english-ai-product-milestone-9-v1` and locked PRD v1.0. It does not enable a live provider,
payment, deployment, production billing, or public access.

`backend.app.provider_sandbox` provides provider-neutral capability registration for LLM, STT, TTS,
avatar timing, usage metering, and health. Configurations accept only `sandbox` or `test`
environments. Real boundaries name an environment variable containing a key; key values never enter
configuration, errors, usage records, logs, evidence, or persistence. The real boundary deliberately
refuses network invocation until a later, separately approved adapter is installed.

Every request passes hard request, token, audio, per-user, daily, and monthly controls. Providers can
be disabled, timed out, retried within a bound, circuit-opened after failures, and routed to an
ordered fallback. Usage records contain units, measured latency, and estimated cost but no prompt,
transcript, audio, credential, or response body.

Current official-documentation evidence is tracked in `PROVIDER_SANDBOX_EVIDENCE.json`. It is a
shortlist, not a benchmark. Indian-English quality, Telugu-accented-English handling, latency,
retention settings, current quotes, voice naturalness, browser support, and viseme support must be
measured in a consented internal cohort. The human package therefore remains NO_GO and makes no
automatic selection.
