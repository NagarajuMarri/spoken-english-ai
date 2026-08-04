# Avatar tutor learner experience

Milestone 8 adds a learner-facing web experience at `/` and two configuration-driven Indian-English tutors: Ananya and Arjun. Learners choose a tutor during onboarding and may change that preference later in Settings. Tutor configuration includes identity, gender, avatar, voice, accent, teaching, animation, prompt, vocabulary, and enabled status.

The browser is the microphone and playback boundary. Supported browsers use `SpeechRecognition` with `en-IN` for speech-to-text and `speechSynthesis` with `en-IN` for spoken tutor replies. Typed practice remains available when browser speech recognition is unavailable. Server-side provider-neutral STT, AI, pronunciation, and TTS boundaries remain available for future production adapters.

The current avatar maturity is **ANIMATED_2D_TUTOR**: distinct photographic tutor portraits receive accessible 2D state animation. A human-like photorealistic video avatar is not implemented. The typed state machine controls idle, listening, processing, thinking, speaking, encouraging, correcting, error, and paused states and offers a reduced-motion fallback.

Voice maturity is **BROWSER_NATIVE_VOICE_BOUNDARY**. No live external provider is enabled by default. Browser capture is consent-gated, bounded to accepted audio types, five MiB, and 60 seconds, and raw audio is not stored in browser storage. Production STT and TTS remain provider integrations.

Lip-sync maturity is **APPROXIMATE_OR_PROVIDER_TIMED**. The provider-neutral contract accepts validated audio duration and viseme timing metadata. The deterministic local fallback animates approximate mouth shapes and does not claim phoneme accuracy; higher-fidelity synchronization remains a future provider integration.

The frontend stores the rotating access/refresh pair only in origin-scoped `sessionStorage` to support restoration within a browser tab. It never stores passwords or audio. Logout, logout-all, refresh rejection, and authentication failure clear the session. Production deployment must add a restrictive Content Security Policy and should prefer a hardened same-site cookie/BFF design where available.

Only individual learners are in scope. Parent and teacher portals are excluded. The MVP tutor catalogue is Indian English only. New personas, accents, exam modes, and coaching products are data configuration rather than conditional UI implementations.

Subscription fields are exposed as an integration-ready boundary; payment processing and deployment are not part of this milestone. The typed avatar and lip-sync adapters remain ready for later 3D or video-avatar integration without changing learner routes.
