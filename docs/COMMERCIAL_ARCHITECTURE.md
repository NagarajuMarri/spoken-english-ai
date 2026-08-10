# Commercial Architecture

Milestone 10 implements `spoken-english-ai-product-milestone-10-v1` against locked PRD v1.0. Plans are `FREE`, `PREMIUM_MONTHLY`, and `PREMIUM_YEARLY`; enterprise remains planning-only. Prices (default INR 299 monthly and INR 2999 yearly), the seven-day trial, limits, feature flags, and fair-use thresholds are configuration—not domain constants.

The entitlement engine accepts only internal plan and subscription state. It has no Razorpay dependency. The persisted launch runtime expires trials, resolves FREE/TRIAL/paid entitlements, and enforces new-conversation, STT voice-minute, daily/monthly tutor-request, token, and estimated AI-cost ceilings before provider work. Dated provider-call events reserve capacity before each dispatch and reconcile duration, units and outcome afterward, so a retry is attributed to when that call occurred. Lower-level grammar and pronunciation dimensions remain domain-enforcer contracts; the launch UI does not make a separate paid entitlement claim for those dimensions.

## Payment flow

The launch boundary is Razorpay with planned UPI, credit card, debit card, and net-banking methods. Live subscription creation remains disabled until approved secrets are supplied. Signed webhooks are verified before processing, event IDs are idempotent, ownership is checked, duplicate events are ignored, refunds require authorization, and all accepted decisions create audit evidence. Google Play Billing, Apple App Store, Stripe, and PayPal are not implemented.

## Subscription lifecycle

Validated transitions cover trial, active, grace period, expiration, cancellation, renewal, upgrade, downgrade, payment failure, and restore. A trial can activate only once per learner and expires from its configured start time. Historical payment/refund evidence is never deleted by a transition.

## Founder metrics

The founder-authorized read-only launch dashboard exposes registrations, active/paid/trial users, configuration-priced estimated MRR/ARR, AI cost, and subscription counts. Financial results are estimates rather than provider settlement. Operational health is linked to `/health/ready`; the dashboard does not invent a successful dependency check.
