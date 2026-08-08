# Feature 7 — Avatar expressions and audio synchronization

Status: **BLOCKED — founder visual acceptance required**

SpeakMate status: **RC1_NOT_READY**

## Release boundary

Feature 7 is isolated on `agent/rc1-feature-7-avatar-audio-sync`, based directly on the
accepted Feature 6 commit `ba7b1b9dcf904d185e848f6ea8ab1aa8b60e6356`. Nothing in this
feature authorizes merge, deployment, public release, or production payments.

## Architecture

The presentation pipeline is renderer-neutral:

`MICROPHONE / TUTOR TURN / HTML AUDIO EVENTS → TUTOR PRESENTATION CONTROLLER → RENDERER FRAME → 2D RENDERER`

The controller owns state, expression, mouth shape, playback ownership, interruption and
recovery. The 2D component owns only visual rendering. A future 3D renderer can consume the
same `TutorRendererFrame` without importing microphone, API, TTS or conversation code.

## Implemented behavior

- `LISTENING` begins when the browser microphone is actually recording.
- `THINKING` covers STT, tutor generation and TTS preparation.
- `SPEAKING` begins only from the active HTML audio element's real `play` event.
- Mouth shapes follow the active audio element's `currentTime` animation frames.
- Pause, stop, end, source replacement, user interruption and error stop mouth movement.
- End and stop return the tutor to `IDLE` immediately.
- Natural blink, listening waveform and thinking indicators are visual, not state evidence.
- The 2D renderer keeps portrait-specific facial anchors for Ananya and Arjun; those coordinates
  do not leak into the neutral controller contract.
- `POSITIVE`, `ENCOURAGING` and `CORRECTIVE` metadata are orthogonal to playback state.
- Playback IDs reject stale events from a previous tutor response.
- Error states expose retry paths; successful retry may re-enter thinking and speaking.
- Reduced-motion mode preserves state/expression information while suppressing blink, mouth,
  waveform and thinking-dot animation.
- There is no fixed fake speaking timer.

## Automated acceptance evidence

Tests must prove:

1. audio ready alone does not claim speaking;
2. real playback start produces speaking;
3. real playback position changes mouth shape;
4. pause, end, stop and interruption reset the mouth;
5. two consecutive responses cannot cross-control one another;
6. all three non-neutral expressions reach the renderer;
7. microphone recording produces listening;
8. errors recover safely;
9. reduced-motion renders a static mouth;
10. existing TTS and native Telugu review behavior remains green.

Current evidence:

- `CODE_EVIDENCE`: complete.
- `AUTOMATED_TEST_EVIDENCE`: 241 backend tests and 68 frontend tests pass; TypeScript,
  ESLint, production build, JSON validation and diff checks pass.
- The 13-test Playwright suite is syntactically discoverable, including a real WAV playback
  lifecycle case and microphone-listening case.
- `RUNTIME_EVIDENCE`: component-level HTML audio lifecycle execution passes. Full Playwright
  Chromium execution is not available in the current workspace because its browser executable
  is not installed; this is not counted as Chrome visual evidence.
- `FOUNDER_VISUAL_ACCEPTANCE`: missing. Feature 7 therefore remains blocked.

## Founder visual review

Automated tests and state labels are not visual acceptance. In Windows Chrome, the founder
must visually confirm each item:

1. Ananya naturally blinks while idle.
2. Starting the microphone visibly changes Ananya to listening.
3. Stopping the microphone and waiting for the tutor visibly shows thinking.
4. Speaking does not start before tutor audio is audible.
5. Mouth movement starts with audible tutor audio and continues for the audio duration.
6. Mouth movement stops when audio ends.
7. Stop resets the mouth and tutor immediately.
8. Replay starts synchronized motion again.
9. A second tutor response synchronizes independently.
10. Positive, encouraging and corrective responses look visually distinct and appropriate.
11. An audio failure shows error/recovery and a successful retry synchronizes correctly.
12. With Chrome reduced-motion enabled, no blink/mouth/wave/dot animation is required to
    understand tutor state.

Founder must return `ACCEPT` or `REVISE` for each item. Feature 7 remains **BLOCKED** until
all required visual checks are accepted.
