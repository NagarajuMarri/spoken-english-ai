# Feature 7 — Real 3D tutor and audio synchronization

Status: **ENGINEERING_REMEDIATED_WITH_DEFERRED_DEVICE_GATE**

Release status: **FOUNDER_FINAL_ACCEPTANCE_REQUIRED; PRODUCTION_NOT_AUTHORIZED**

## Release boundary

The RC remediation is developed on `agent/rc1-final-engineering-acceptance`. It does not authorize merge, deployment, public release, production payments, or a claim that a founder's physical browser, microphone, speaker, hearing, or subjective visual-quality review passed.

## Architecture

The presentation pipeline remains renderer-neutral:

`MICROPHONE / TUTOR TURN / HTML AUDIO EVENTS / AUDIO AMPLITUDE → PRESENTATION CONTROLLER → RENDERER FRAME → THREE.JS MODEL`

The controller owns learner-visible state, expression, playback ownership, interruption, and recovery. A Three.js adapter renders Ananya's rigged GLB model. Save-data/low-power devices use a lightweight volumetric 3D rig; WebGL or renderer failures fall back to the configured portrait. Microphone, API, TTS, and conversation state do not live in the renderer.

## Implemented behavior

- Ananya supports `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `SUCCESS`, `RETRY`, and error recovery.
- The model includes blink, eye/head motion, subtle breathing, listening/thinking posture, encouragement, and clarification behavior.
- `SPEAKING` begins only when the active HTML audio element emits `playing`.
- A Web Audio analyser measures real playback amplitude and drives jaw/viseme movement.
- Pause, stop, end, source replacement, interruption, and error stop speaking motion immediately.
- Replay restarts motion only when the same source actually resumes playback.
- The opening server-owned tutor turn is synthesized once and played after the single browser gesture gate where required.
- A source-generation or playback failure cannot falsely report completion and cannot trap the learner.
- Reduced-motion mode preserves state information without continuous motion.
- Initialization telemetry is bounded and contains no learner text, audio, token, or account identifier.
- There is no fixed fake-speaking timer and no phoneme-accuracy claim.

## Automated acceptance contract

Tests cover real-event playback start, amplitude-driven mouth motion, pause/end/stop/error reset, replay, stale-source isolation, all learner states, reduced motion, model rig and morph control, WebGL/lite/portrait fallback, opening greeting exactly once, autoplay rejection, rapid-start idempotency, StrictMode request idempotency, no duplicate TTS across mode changes, and learner-safe accessibility labels.

Responsive browser acceptance covers desktop and mobile containment, essential controls, hidden engineering metadata, stable conversation state, and the bundled WebGL model path. Exact final suite totals belong in the RC acceptance report and release notes after all gates complete.

## Deferred founder device review

The founder must still review the final pushed SHA on physical Windows Chrome or Edge:

1. Ananya's model, framing, appearance, blink, breathing, and head/eye motion look natural and professionally appropriate.
2. Listening, thinking, speaking, success, and retry behavior are distinct without exaggeration.
3. The opening greeting and later replies are audible without repetitive manual play actions.
4. Mouth movement begins with audible speech, follows it plausibly, and stops immediately on stop/end/error.
5. Replay, mute, stop, microphone permission recovery, weak-device fallback, and reduced-motion behavior are acceptable.
6. Live-provider latency and Telugu/English voice quality feel conversational.

Every item above is `DEFERRED_DEVICE_GATE`, not founder `PASS`.
