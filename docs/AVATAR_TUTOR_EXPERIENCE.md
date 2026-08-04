# Avatar tutor learner experience

Milestone 8 adds a learner-facing web experience at `/` and two configuration-driven Indian-English tutors: Ananya and Arjun. Learners choose a tutor during onboarding and may change that preference later in Settings. Tutor configuration includes identity, gender, avatar, voice, accent, teaching, animation, prompt, vocabulary, and enabled status.

The browser is the microphone and playback boundary. Supported browsers use `SpeechRecognition` with `en-IN` for speech-to-text and `speechSynthesis` with `en-IN` for spoken tutor replies. Typed practice remains available when browser speech recognition is unavailable. Server-side provider-neutral STT, AI, pronunciation, and TTS boundaries remain available for future production adapters.

The interface presents listening, thinking, speaking, blinking, and subtle expression states around human-like tutor portraits. The authenticated backend retains ownership controls, conversation memory, grammar corrections, vocabulary suggestions, optional Telugu preference, daily practice, progress, and streaks.

Only individual learners are in scope. Parent and teacher portals are excluded. The MVP tutor catalogue is Indian English only. New personas, accents, exam modes, and coaching products are data configuration rather than conditional UI implementations.

Subscription fields are exposed as an integration-ready boundary; payment processing and deployment are not part of this milestone.
