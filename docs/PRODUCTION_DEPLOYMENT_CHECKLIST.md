# Production deployment checklist

- [ ] RC blockers in `KNOWN_ISSUES_V1.md` are closed and regression tested.
- [ ] Exact release SHA has human go/no-go approval.
- [ ] Legal text, pricing, beta cohort and support ownership are approved.
- [ ] PostgreSQL migrations, Redis, private object storage and workers are ready.
- [ ] DNS, HTTPS, trusted hosts, CORS and security headers are verified.
- [ ] OpenAI keys and hard cost ceilings are configured through secrets management.
- [ ] Razorpay remains test mode unless separately authorized after this milestone.
- [ ] Monitoring, alerts, backup restore and rollback are rehearsed.
- [ ] PWA install/offline behavior and mobile/desktop acceptance pass.
- [ ] No deployment occurs from this audit.
