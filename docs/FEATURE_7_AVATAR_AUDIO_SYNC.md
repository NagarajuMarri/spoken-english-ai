# Feature 7 — Avatar expressions and audio synchronization

Status: **ENGINEERING_ACCEPTED_WITH_DEFERRED_DEVICE_GATE**

Release status: **RC1 engineering validation in progress; founder release approval not granted**

## Release boundary

Feature 7 engineering acceptance is isolated on
`agent/rc1-feature-7-engineering-acceptance`, based directly on the accepted Feature 6
commit `8d50cea2f08ca52ffca8e0ed8e705d47e903f43a`. The original implementation commit
`a49f6035abc474909300aa4f15a8ac8b24f6ba16` is already an ancestor of that baseline.
Nothing in this feature authorizes merge, deployment, public release, production payments,
or a claim that a founder's physical browser, microphone, speaker, or hearing test passed.

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
- Pause, stop and end retain ownership of the currently loaded source so resume or replay can
  re-enter synchronized speaking.
- A browser-audio error clears ownership of the failed source, resets the mouth, and exposes a
  retry that refetches TTS; only the resulting fresh `SOURCE_READY` event can speak again.
- Source replacement and new tutor processing clear old ownership; stale playback IDs remain
  unable to control a later response.
- Natural blink, listening waveform and thinking indicators are visual, not state evidence.
- The 2D renderer keeps portrait-specific facial anchors for Ananya and Arjun; those coordinates
  do not leak into the neutral controller contract.
- `POSITIVE`, `ENCOURAGING` and `CORRECTIVE` metadata are orthogonal to playback state.
- Error states expose retry paths; successful retry may re-enter thinking and speaking.
- Reduced-motion mode preserves state/expression information while suppressing blink, mouth,
  waveform and thinking-dot animation.
- There is no fixed fake speaking timer and no phoneme-accuracy claim.

## Automated acceptance contract

Tests prove:

1. audio ready alone does not claim speaking;
2. real playback start produces speaking;
3. real playback position changes mouth shape;
4. pause, end, stop and interruption reset the mouth;
5. pause, stop and end can resume or replay the current source;
6. two consecutive responses cannot cross-control one another;
7. all three non-neutral expressions reach the renderer;
8. microphone recording produces listening;
9. browser-audio errors require a fresh TTS source and then recover safely;
10. reduced-motion renders a static mouth;
11. existing TTS and native Telugu review behavior remains green.

## Current acceptance evidence

- `CODE_EVIDENCE`: complete on top of the accepted Feature 6 baseline.
- `TARGETED_TEST_EVIDENCE`: 22 Feature 7 state, renderer, audio-lifecycle and accessibility
  tests pass; the focused backend tutor-experience suite passes 7 tests.
- `FULL_REGRESSION_EVIDENCE`: 313 backend tests and 72 frontend tests pass.
- `BROWSER_AUTOMATION_EVIDENCE`: all 9 enabled Playwright Chromium journeys pass, including
  real WAV playback lifecycle/current-time mouth motion, immediate stop/reset, replay
  re-synchronization, microphone denial recovery and MediaRecorder byte submission. Four
  separate live-account tests remain environment-gated and belong to the final RC gate.
- `RUNTIME_EVIDENCE`: backend and frontend both return HTTP 200. Headless Chromium executes
  the Feature 7 journey against the running frontend.
- `DEVICE_EVIDENCE`: not available. The in-app browser could not attach to the founder's
  physical Chrome session, and automation cannot hear speaker output or judge physical-device
  quality.

Feature 7 therefore meets its automatable engineering gate and is
**ENGINEERING_ACCEPTED_WITH_DEFERRED_DEVICE_GATE**. It must not be described as founder-device
accepted or acoustically/phoneme synchronized.

## Deferred final RC device review

The founder should review these once, against the final RC in Windows Chrome or Edge:

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
12. With reduced motion enabled, no blink/mouth/wave/dot animation is required to understand
    tutor state.

Every item above is currently `DEFERRED_DEVICE_GATE`, not `PASS`. These checks do not block
engineering progression, but founder release approval still requires their final disposition.
