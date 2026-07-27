# Subscription Model

## Product tiers

The limited **Free** plan supports onboarding, a bounded number of daily conversation minutes/turns, text fallback, transcript, a concise correction summary, basic history, and streaks. A future **Plus** plan can raise limits and unlock more modes, deeper history, targeted practice, richer progress insights, and additional voice allowance.

Learning safety, core privacy controls, data export/deletion, and essential accessibility must never be paywalled.

## Architecture

Features check provider-independent entitlements such as `conversation_turns_daily`, `voice_minutes_monthly`, `mode.job_interview`, and `progress.history_days`; they do not check payment-provider products directly. A payment adapter will translate verified webhook state into subscriptions and entitlements. Production payment integration is excluded.

Quotas should be transparent, measured server-side, timezone-aware, idempotent, and accompanied by a usable text path when voice allowance ends. Pricing and exact limits require learner research and unit-economics validation.

