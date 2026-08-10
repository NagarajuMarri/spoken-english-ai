# Version 1.0 RC1 known issues

## Blocking production release

- The consolidated founder acceptance on physical Chrome/Edge, microphone, real STT, speaker output, live tutor/TTS quality, and avatar/audio synchronization is still pending.
- Staging infrastructure, DNS/HTTPS, production secrets, monitoring/alerts, backup/restore, rollback, and immutable-image evidence have not been supplied in this repository workspace.
- Docker and Nginx executables are unavailable in this workspace, so rendered-template `nginx -t`, container smoke, actual host-ingress peer observation, spoofed-header verification, streamed-upload behavior, and service-worker cache-migration evidence remain staging gates.
- Automated database concurrency coverage in this workspace is SQLite/sequential. The implemented PostgreSQL row-lock/CAS paths for quota reservations, refresh rotation, provider retry claims, and subscription expiry still require real-contention staging stress evidence before production; this is an evidence gap, not a claim that those implementations are incorrect.
- Final legal text, brand, pricing, beta cohort, production domain, and support/incident ownership require founder approval.
- Production deployment, public release, Razorpay live mode, and real charges are not authorized.

## Non-blocking engineering limitations

- Pronunciation guidance remains synthetic/non-acoustic unless a validated provider supplies acoustic evidence.
- Live OpenAI latency and subjective Telugu/English voice quality require the deferred founder device run; deterministic and contract-level provider paths are automated.
- The full MyPy run has 56 existing errors confined to test files; the checked production modules pass their typed gate.
- Payment upgrade is intentionally a Razorpay test-mode preview. It creates an audit event but no subscription and no charge.
- Legal pages remain draft until the production-release approval gate.
