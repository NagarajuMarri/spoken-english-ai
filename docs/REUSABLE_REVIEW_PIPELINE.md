# Reusable reviewed-content architecture

SpeakMate and future Vedha AI subjects use this presentation boundary:

`CONTENT GENERATOR → SUBJECT REVIEWER → LANGUAGE REVIEWER → FINAL PRESENTATION`

- The content generator owns facts, correction results, learning goals, safety meaning,
  scoring, and evaluation signals.
- A subject reviewer may validate subject correctness without changing the learner's selected
  language style. SpeakMate currently preserves this boundary for future subject modules.
- The language reviewer owns presentation only: Telugu naturalness, conversational flow,
  vocabulary choice, sentence structure, useful code-switching, and teacher tone.
- Final presentation and TTS consume only the reviewed learner-facing fields.

The language reviewer cannot return or overwrite protected content fields. A digest binds the
review to the exact protected content, and the application checks the protected fields again
after review. Runtime logs contain only mode, reason code, expression hint, request counts, and
sanitized validation paths—not learner or tutor text.
