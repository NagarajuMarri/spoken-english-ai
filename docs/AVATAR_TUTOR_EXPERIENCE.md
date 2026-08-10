# Avatar tutor learner experience

SpeakMate presents Ananya as a real-time, rigged 3D tutor in the focused Voice-mode lesson surface. The renderer uses Three.js and a bundled, Meshopt-compressed GLB model in chest-up live-class framing. The model has natural blink and eye motion, subtle breathing and head motion, and distinct `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `SUCCESS`, and `RETRY` behavior. Arjun retains his configured portrait; the Ananya model is never reused as Arjun.

The browser is the microphone and playback boundary. Captured microphone bytes are sent through the consent-gated server STT boundary, while accepted tutor text is rendered through the server TTS boundary and an HTML audio element. Typed practice remains available when browser recording is unavailable.

## Multimedia runtime layer

Conversation and AI code emit semantic events into `SpeakMateMultimediaRuntime`; they do not manipulate Three.js objects, animation loops, or mouth geometry. The runtime coordinates the authoritative tutor presentation, real audio lifecycle, expression, replaceable lip-sync strategy, reduced-motion behavior, animation clock, and renderer fallback contract:

`Conversation Engine -> Tutor Response -> TTS -> Multimedia Runtime -> renderer / animation / audio / lip-sync / expression / device fallback`

The React bridge adapts runtime snapshots to the learner screen, while the renderer-neutral frame can be consumed by the bundled-model, lightweight-3D, portrait, or future tutor implementations. `MultimediaAudioPort` keeps play, replay, stop, mute, and lifecycle publication provider-neutral. The default `AmplitudeLipSyncProvider` consumes measured Web Audio frames; a future timestamped `LipSyncProvider` can supply phoneme/viseme poses without changing the conversation engine or renderer contract.

## Rendering and fallback boundary

The presentation controller remains renderer-neutral. On a capable device, Ananya first renders a lightweight volumetric 3D tutor and upgrades to the bundled rigged model when it is ready. Save-data and devices reporting no more than two logical cores retain the lightweight 3D renderer. A missing WebGL context, initialization/render exception, or lost context falls back to Ananya's portrait without trapping the lesson. Reduced-motion mode preserves visible and announced state while suppressing continuous character motion.

The model asset provenance, upstream revision, source and optimized SHA-256 hashes, CC0 declaration, and transformation steps are recorded in `frontend/public/models/README.md`. The optimized GLB is 13,918,296 bytes and is fetched only by the capable-device upgrade path. Renderer initialization and model-load duration are measured separately; after a five-second active window the renderer also reports capped average FPS and, only where the browser exposes it, aggregate JavaScript heap usage. These metrics contain no learner text, audio, account, request, or playback identifiers.

Both supported static-serving paths expose the bundled `/models` directory. Their Content Security Policy permits the narrowly scoped `wasm-unsafe-eval` source required by Three.js Meshopt decoding while continuing to forbid general `unsafe-eval`.

## Playback synchronization

Speaking begins only when the active audio element emits a real `playing` event. A browser `AnalyserNode` measures the currently playing tutor audio and drives jaw/viseme amplitude. Pause, stop, end, interruption, source replacement, and error immediately stop mouth movement. Replay reuses the same loaded source and restarts synchronized movement only when playback actually resumes. No fixed speaking timer or phoneme-accuracy claim is made.

The opening tutor turn is a server-owned conversation turn. The learner sees one `Start conversation` action when a browser gesture is needed; that action unlocks and plays the opening greeting exactly once. Later tutor replies auto-play where browser policy permits. A persistent opening-audio failure has an explicit continue-without-audio path, so the learner is never locked out of the lesson.

## Security and product boundary

Raw audio is not stored in browser storage. The rotating access/refresh pair remains in origin-scoped `sessionStorage`; logout, logout-all, refresh rejection, and authentication failure clear it. Production deployment must add the approved Content Security Policy and should prefer a hardened same-site cookie/BFF design where available.

Only individual learners are in scope. Subscription fields are an integration boundary; real payment, deployment, public release, and production authorization are outside this engineering candidate. Subjective naturalness, audible synchronization, and physical microphone/speaker behavior remain founder device gates.
