# Avatar tutor learner experience

Milestone 8 adds a learner-facing web experience at `/` and two configuration-driven Indian-English tutors: Ananya and Arjun. Learners choose a tutor during onboarding and may change that preference later in Settings. Tutor configuration includes identity, gender, avatar, voice, accent, teaching, animation, prompt, vocabulary, and enabled status.

The browser is the microphone and playback boundary. Captured microphone bytes are sent through the consent-gated server STT boundary, while accepted tutor text is rendered through the server OpenAI TTS boundary and an HTML audio element. Typed practice remains available when browser recording is unavailable.

The current avatar maturity is **ANIMATED_2D_TUTOR**: distinct photographic tutor portraits receive accessible 2D state animation. A human-like photorealistic video avatar is not implemented. A headless presentation controller owns idle, listening, thinking, speaking, positive, encouraging, corrective, interruption, error and recovery behavior. The 2D renderer consumes a neutral frame contract and can later be replaced by a 3D renderer without moving microphone, tutor-turn or audio-lifecycle logic.

Voice maturity is **OPENAI_TTS_PLAYBACK_BOUNDARY**. Browser capture is consent-gated, bounded to accepted audio types, five MiB, and 60 seconds, and raw audio is not stored in browser storage. Tutor audio is requested for the exact completed tutor turn.

Lip-sync maturity is **AUDIO_LIFECYCLE_APPROXIMATE**. Speaking begins only from the real audio element's `play` event. Mouth shapes are sampled from the element's real `currentTime` while playback is active and stop on pause, stop, end, interruption or error. There is no fixed fake speaking timer and no phoneme-accuracy claim. The provider-neutral contract can accept timed visemes later without changing the controller or renderer interface.

The frontend stores the rotating access/refresh pair only in origin-scoped `sessionStorage` to support restoration within a browser tab. It never stores passwords or audio. Logout, logout-all, refresh rejection, and authentication failure clear the session. Production deployment must add a restrictive Content Security Policy and should prefer a hardened same-site cookie/BFF design where available.

Only individual learners are in scope. Parent and teacher portals are excluded. The MVP tutor catalogue is Indian English only. New personas, accents, exam modes, and coaching products are data configuration rather than conditional UI implementations.

Subscription fields are exposed as an integration-ready boundary; payment processing and deployment are not part of this milestone. The typed avatar and lip-sync adapters remain ready for later 3D or video-avatar integration without changing learner routes.
