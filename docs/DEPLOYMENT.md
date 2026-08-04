# Deployment

Supply a high-entropy active signing key, explicit active key ID, verification-key JSON, issuer, audience, database URL, environment, and build identifier through the deployment secret/configuration system. Never use `.env.example` values in production.

For rotation, add the new key, deploy it as active while retaining the prior verification key, wait beyond the maximum access-token lifetime, then remove the retired key. Keep the `legacy` key only during migration for tokens without `kid`.

Production must use HTTPS, PostgreSQL migrations, a distributed Redis-compatible rate limiter, centralized redacted logs, backups, and alerting. Readiness must return 200 before traffic is admitted. Known limitations include no live Redis adapter implementation, paid monitoring integration, real object storage, MFA, or automated key management.

AI providers are optional. Deterministic providers require no secret. A live adapter receives its client, model, secret reference, timeout, and retry settings through deployment composition. The application never logs or persists provider keys.
