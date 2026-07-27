# Security and Privacy

## Baseline

Collect the minimum identity and learning data needed. Secrets come only from environment-backed secret management and are never committed or logged. Use TLS in transit, encryption at rest, least-privilege service/database roles, dependency scanning, structured audit events, and generic external errors.

Treat voice, transcripts, Telugu explanations, learner level, and progress as personal data. Obtain explicit microphone permission, visibly indicate recording, state why audio is used, and default to deleting raw audio after transcription. Provide retention, export, correction, and deletion workflows before production.

Never send credentials or unnecessary identity data to AI/speech providers. Contractually verify provider training, retention, residency, deletion, and subprocessor behavior. Redact logs and assign short retention periods.

## Safety

Doctor Visit is language practice, not medical advice. Content needs abuse and self-harm escalation rules before broad release. Users aged 12–17 require an age-aware launch design, parental/guardian and jurisdiction review, and stricter defaults; the MVP foundation does not claim compliance for child-directed use.

Threat modeling, authentication, authorization, rate limiting, abuse prevention, backup/restore testing, incident response, and a privacy impact assessment are release gates, not Milestone 1 implementations.

## Voice consent and lifecycle

Consent changes are append-only records with policy version and timestamps. Processing and storage consent are distinct. Simulated media types are restricted, unsafe/traversal references are rejected, and errors expose no secrets. Production requires authenticated ownership, confirmed object deletion, background retries, monitoring, and provider legal/security review.
