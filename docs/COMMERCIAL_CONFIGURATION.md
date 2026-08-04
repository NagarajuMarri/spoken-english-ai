# Commercial Configuration Guide

All variables use the `SPOKEN_ENGLISH_` prefix. Configure monthly/yearly INR prices, trial days, FREE limits, PREMIUM fair-use requests and voice minutes, monthly AI-cost ceiling, advertisements, and premium tutor flags through environment configuration. Defaults are documented in `.env.example`.

`SPOKEN_ENGLISH_RAZORPAY_ENABLED` defaults to `false`. A webhook secret must come from an approved secret store and must never be committed, logged, returned by APIs, or placed in payment/entitlement records. Enabling configuration alone does not install a live network adapter or authorize production billing.
