# Production deployment checklist

- [ ] RC blockers in `KNOWN_ISSUES_V1.md` are closed and regression tested.
- [ ] Exact release SHA has human go/no-go approval.
- [ ] Legal text, pricing, beta cohort and support ownership are approved.
- [ ] Each founder-dashboard account is independently identity-checked and marked `email_verified` through an audited provisioning process; configured email or self-registration alone is not accepted.
- [ ] PostgreSQL migrations, Redis, private object storage and workers are ready.
- [ ] DNS, HTTPS, trusted hosts, CORS and security headers are verified.
- [ ] Nginx is loopback-published behind the approved host TLS ingress; its exact observed peer is the sole `TRUSTED_INGRESS_CIDR`, and spoofed client IP/proto headers are sanitized.
- [ ] The STT route's Nginx `10m`/backend 10,000,000-byte limits, streaming configuration, read-only filesystem, tmpfs paths, and no-persistent-raw-audio behavior are verified.
- [ ] OpenAI keys and hard cost ceilings are configured through secrets management.
- [ ] Razorpay remains test mode unless separately authorized after this milestone.
- [ ] Monitoring, alerts, backup restore and rollback are rehearsed.
- [ ] PWA install/offline behavior, `spoken-english-shell-v2` reset-cache migration, and mobile/desktop acceptance pass.
- [ ] Mutating Playwright overrides are absent from production; any remote acceptance ran only against a verified disposable non-production target.
- [ ] No deployment occurs from this audit.
