# Deployment

Supply a high-entropy active signing key, explicit active key ID, verification-key JSON, issuer, audience, database URL, environment, and build identifier through the deployment secret/configuration system. Never use `.env.example` values in production.

For rotation, add the new key, deploy it as active while retaining the prior verification key, wait beyond the maximum access-token lifetime, then remove the retired key. Keep the `legacy` key only during migration for tokens without `kid`.

Production must use HTTPS, PostgreSQL migrations, a distributed Redis-compatible rate limiter, centralized redacted logs, backups, and alerting. Readiness must return 200 before traffic is admitted. The Compose web port is loopback-only and must sit behind an approved same-host TLS ingress. Configure `TRUSTED_INGRESS_CIDR` as the exact peer Nginx observes, make the ingress replace untrusted forwarded-address/proto headers, and verify Nginx overwrites the private backend hop with its sanitized client IP and canonical `https` scheme. See `STAGING_DEPLOYMENT.md`; broad trusted-proxy ranges and direct public port 8080 exposure are forbidden. Known limitations include no paid monitoring integration, MFA, or automated key management.

Mutating live Playwright acceptance is for local or explicitly disposable non-production targets only. The remote-target override cannot bypass the runtime `production` prohibition and must never be present in production secrets or automation.

AI providers are optional. Deterministic providers require no secret. A live adapter receives its client, model, secret reference, timeout, and retry settings through deployment composition. The application never logs or persists provider keys.
