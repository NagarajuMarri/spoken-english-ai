# Commercial Architecture

Milestone 10 implements `spoken-english-ai-product-milestone-10-v1` against locked PRD v1.0. Plans are `FREE`, `PREMIUM_MONTHLY`, and `PREMIUM_YEARLY`; enterprise remains planning-only. Prices (default INR 299 monthly and INR 2999 yearly), the seven-day trial, limits, feature flags, and fair-use thresholds are configuration—not domain constants.

The entitlement engine accepts only internal plan and subscription state. It has no Razorpay dependency. Trusted backend enforcement covers conversation, voice, grammar, pronunciation, AI-request, trial, subscription-status, AI-cost, and fair-use limits.

## Payment flow

The launch boundary is Razorpay with planned UPI, credit card, debit card, and net-banking methods. Live subscription creation remains disabled until approved secrets are supplied. Signed webhooks are verified before processing, event IDs are idempotent, ownership is checked, duplicate events are ignored, refunds require authorization, and all accepted decisions create audit evidence. Google Play Billing, Apple App Store, Stripe, and PayPal are not implemented.

## Subscription lifecycle

Validated transitions cover trial, active, grace period, expiration, cancellation, renewal, upgrade, downgrade, payment failure, and restore. A trial can activate only once per learner and expires from its configured start time. Historical payment/refund evidence is never deleted by a transition.

## Founder metrics

Backend-only owner-scoped APIs expose registrations, active/paid/trial users, conversion, estimated MRR/ARR, AI cost, AI cost per learner/conversation, and subscription counts. Financial results are explicitly `ESTIMATE_NOT_PROVIDER_SETTLEMENT`; no dashboard UI or production settlement integration exists.
