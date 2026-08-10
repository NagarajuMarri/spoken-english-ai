# Version 1.0 RC1 known issues

## Blocking production release

- The consolidated founder acceptance on physical Chrome/Edge, microphone, real STT, speaker output, live tutor/TTS quality, and avatar/audio synchronization is still pending.
- Staging infrastructure, DNS/HTTPS, production secrets, monitoring/alerts, backup/restore, rollback, and immutable-image evidence have not been supplied in this repository workspace.
- Docker and Nginx executables are unavailable in this workspace, so rendered-template `nginx -t`, container smoke, actual host-ingress peer observation, spoofed-header verification, streamed-upload behavior, and service-worker cache-migration evidence remain staging gates.
- Automated database concurrency coverage in this workspace is SQLite/sequential. The implemented PostgreSQL row-lock/CAS paths for quota reservations, refresh rotation, provider retry claims, and subscription expiry still require real-contention staging stress evidence before production; this is an evidence gap, not a claim that those implementations are incorrect.
- Final legal text, brand, pricing, beta cohort, production domain, and support/incident ownership require founder approval.
- **Founder device gate:** the RC now contains a rigged Three.js Ananya model with analyser-driven speaking motion and explicit weak-device/WebGL fallbacks. Physical Chrome/Edge visual naturalness, audible synchronization, microphone behavior, and speaker quality remain unaccepted until the founder tests the final pushed SHA.
- **External mail gate:** password reset has a production SMTP boundary and durable Redis-worker delivery path, but sender-domain verification, real credentials, provider health, DNS, mailbox receipt, link completion, and one-time reuse rejection still require a controlled founder/staging mailbox run.
- Production deployment, public release, Razorpay live mode, and real charges are not authorized.

## Non-blocking engineering limitations

- Pronunciation guidance remains synthetic/non-acoustic unless a validated provider supplies acoustic evidence.
- Live OpenAI latency and subjective Telugu/English voice quality require the deferred founder device run; deterministic and contract-level provider paths are automated.
- Production modules pass the typed gate; test modules are not part of the production MyPy target.
- Payment upgrade is intentionally a Razorpay test-mode preview. It creates an audit event but no subscription and no charge.
- Legal pages remain draft until the production-release approval gate.
