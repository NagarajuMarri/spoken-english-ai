# Version 1.0 RC1 known issues

## Release blockers

- Closed-beta mode is reported by configuration but is not enforced during registration; invite-code configuration is unused.
- No customer-facing feedback form invokes the authenticated feedback endpoint.
- The founder metrics route is learner-owner scoped, in-memory and is not a founder/admin launch dashboard.
- Pricing is present, but trial activation, subscription status and entitlement UX are not connected into the customer journey.
- The required end-to-end journey lacks explicit profile management, conversation completion/progress acceptance and pronunciation-persistence acceptance.

## Non-blocking limitations

- Forgot-password is not implemented and was treated as optional by the audit request.
- Legal text is explicitly draft and still requires legal/founder approval.
- Live OpenAI latency was not measured because live provider invocation is not authorized.
