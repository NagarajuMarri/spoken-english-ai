# Staging deployment package

This package is deliberately provider-neutral and does not deploy itself. Operators supply private PostgreSQL, Redis, and S3-compatible endpoints plus immutable image references through a secret store.

```sh
cp .env.production.example .env.production
docker compose --env-file .env.production -f compose.production.yaml config
docker compose --env-file .env.production -f compose.production.yaml run --rm migrate
docker compose --env-file .env.production -f compose.production.yaml up -d worker backend frontend
curl --fail https://STAGING_HOST/health/ready
```

Replace every placeholder, keep `.env.production` outside version control, terminate TLS at the approved ingress, restrict backend/storage/database/Redis to private networks, and record the evidence listed in `PRODUCTION_READINESS.md`. Stop after staging validation and wait for human promotion approval.
