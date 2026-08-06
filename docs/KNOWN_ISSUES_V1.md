# Version 1.0 RC1 known issues

## Release blockers

- Closed-beta mode is reported by configuration but is not enforced during registration; invite-code configuration is unused.
- No customer-facing feedback form invokes the authenticated feedback endpoint.
- The founder metrics route is learner-owner scoped, in-memory and is not a founder/admin launch dashboard.
- Pricing is present, but trial activation, subscription status and entitlement UX are not connected into the customer journey.
- The required end-to-end journey lacks explicit profile management, conversation completion/progress acceptance and pronunciation-persistence acceptance.

## Non-blocking limitations

- Forgot-password is not implemented and was treated as optional by the audit request.
- Pytest 8.4.2 is development-only and is flagged by pip-audit; its compatible upgrade is tracked separately.
- One pre-existing nullable-conversation mypy warning remains; runtime ownership tests pass.
- Legal text is explicitly draft and still requires legal/founder approval.
- Live OpenAI latency was not measured because live provider invocation is not authorized.
