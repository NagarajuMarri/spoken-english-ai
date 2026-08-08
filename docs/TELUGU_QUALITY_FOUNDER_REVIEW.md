# Feature 6 — Native Telugu founder review

Status: **BLOCKED — founder language acceptance required**

Acceptance question for every sample:

> Does this sound like a native Telugu English teacher speaking naturally to a student?

Review the 12 reference responses in `backend/evals/telugu_quality.json`. Mark each case
`ACCEPT`, `REVISE`, or `REJECT`, and add the exact phrase you would naturally use when a
case needs revision. Automated checks cover structure and preservation; they do not certify
native Telugu quality.

Release acceptance requires all four evidence classes:

1. `CODE_EVIDENCE`
2. `AUTOMATED_TEST_EVIDENCE`
3. `RUNTIME_EVIDENCE`
4. `FOUNDER_LANGUAGE_ACCEPTANCE`

Feature 5 OpenAI TTS is **ACCEPTED**. Feature 7 avatar synchronization must not start until
Feature 6 receives founder language acceptance.
