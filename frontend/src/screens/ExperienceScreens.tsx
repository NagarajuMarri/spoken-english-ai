import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { normalizeExpression, initialTutorPresentation, reduceTutorPresentation } from "../avatar/machine";
import { ApiError, api } from "../api/client";
import { useAuth as requireAuth } from "../auth/AuthProvider";
import { Avatar } from "../components/Avatar";
import type { Account, Dashboard, LanguageMode, Tutor, TutorSpeech, VoiceTranscription } from "../models";
import { useRouter } from "../routes/router";
import { TutorAudioPlayer, type AudioLifecycleEvent } from "../voice/TutorAudioPlayer";
import { useMicrophone, type CapturedAudio } from "../voice/useMicrophone";

const ACTIVE_LESSON_TITLE_KEY = "speakmate.active-lesson-title.v1";
const DAILY_LESSON_TITLE = "A confident morning routine";

type PracticeMode = "VOICE" | "TEXT";
type ConversationRole = "learner" | "tutor";

interface ConversationMessage {
  id: string;
  role: ConversationRole;
  text: string;
  source?: PracticeMode;
}

function latestMessage(messages: ConversationMessage[], role: ConversationRole) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === role) return messages[index];
  }
  return undefined;
}

export function DashboardScreen({ data, tutor }: { data: Dashboard; tutor: Tutor }) {
  const { navigate } = useRouter();
  const startConversation = () => {
    sessionStorage.removeItem(ACTIVE_LESSON_TITLE_KEY);
    navigate("/app/conversation");
  };
  return (
    <section className="page">
      <h1>Ready for today’s conversation?</h1>
      <div className="dashboard-grid">
        <article className="hero-card">
          <img src={tutor.avatar_profile} alt={`${tutor.display_name}, your tutor`} />
          <div>
            <h2>{tutor.display_name}</h2>
            <p>{tutor.teaching_style}</p>
            <button onClick={startConversation}>Start speaking</button>
          </div>
        </article>
        {[[data.current_streak_days, "day streak"], [data.completed_sessions, "sessions"], [data.total_practice_minutes, "minutes"]].map(([value, label]) => (
          <article className="metric" key={label}><strong>{value}</strong><span>{label}</span></article>
        ))}
      </div>
    </section>
  );
}

export function DailyLessonScreen() {
  const { navigate } = useRouter();
  const beginLesson = () => {
    sessionStorage.setItem(ACTIVE_LESSON_TITLE_KEY, DAILY_LESSON_TITLE);
    navigate("/app/conversation");
  };
  return (
    <section className="page">
      <h1>{DAILY_LESSON_TITLE}</h1>
      <article className="lesson">
        <b>10 minutes · Indian English</b>
        <h2>Describe your morning clearly</h2>
        <p>Use usually, afterwards, and routine. Focus on present simple and natural sentence stress.</p>
        <ol><li>Warm-up and listen</li><li>Speak naturally</li><li>Review grammar and vocabulary</li></ol>
        <button onClick={beginLesson}>Begin lesson</button>
      </article>
    </section>
  );
}

export function ProgressScreen({ data }: { data: Dashboard }) {
  return (
    <section className="page">
      <h1>Small practice. Real momentum.</h1>
      <div className="progress-grid">
        {[[data.current_streak_days, "Current streak"], [data.completed_sessions, "Completed sessions"], [data.total_practice_minutes, "Practice minutes"]].map(([value, label]) => (
          <article key={label}><strong>{value}</strong><span>{label}</span></article>
        ))}
      </div>
    </section>
  );
}

export function SettingsScreen({ data, tutor, onChange }: { data: Dashboard; tutor: Tutor; onChange: () => void }) {
  const { logoutAll } = useAuthBridge();
  const plan = data.subscription_tier.replaceAll("_", " ");
  const status = data.subscription_status.replaceAll("_", " ");
  const voiceDescription = tutor.tutor_id === "ananya" ? "Warm Indian English voice" : "Confident Indian English voice";
  return (
    <section className="page">
      <h1>Make practice feel like yours.</h1>
      <article className="settings-card">
        <img src={tutor.avatar_profile} alt="" />
        <div><h2>{tutor.display_name}</h2><p>{voiceDescription}</p><button onClick={onChange}>Change tutor</button></div>
      </article>
      <p><strong>Subscription:</strong> {plan} · {status}.</p>
      <button onClick={() => void logoutAll()}>Log out on all devices</button>
    </section>
  );
}

function useAuthBridge() {
  return requireAuth();
}

function turnIdentity() {
  return globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function canRetryTranscription(error: unknown) {
  if (error instanceof ApiError) return error.retryable && [409, 503, 504].includes(error.status);
  return error instanceof TypeError;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

export function ConversationScreen({
  account,
  tutor,
  languageMode,
  telugu,
}: {
  account: Account;
  tutor: Tutor;
  languageMode?: LanguageMode;
  telugu?: boolean;
}) {
  const selectedLanguageMode: LanguageMode = languageMode ?? (telugu ? "ENGLISH_TELUGU" : "ENGLISH");
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("VOICE");
  const [lessonTitle] = useState(() => sessionStorage.getItem(ACTIVE_LESSON_TITLE_KEY) ?? "");
  const [id, setId] = useState("");
  const [input, setInput] = useState("");
  const [lastTranscript, setLastTranscript] = useState("");
  const [turnError, setTurnError] = useState("");
  const [audioError, setAudioError] = useState("");
  const [audioBusy, setAudioBusy] = useState(false);
  const [speech, setSpeech] = useState<TutorSpeech | null>(null);
  const [spokenText, setSpokenText] = useState("");
  const [lastSpeechTurn, setLastSpeechTurn] = useState("");
  const [lastExpression, setLastExpression] = useState("NEUTRAL");
  const [interruptSequence, setInterruptSequence] = useState(0);
  const [pendingTurn, setPendingTurn] = useState<{ text: string; key: string; retryable: boolean } | null>(null);
  const [pendingTranscription, setPendingTranscription] = useState<{ capture: CapturedAudio; key: string } | null>(null);
  const [transcriptionError, setTranscriptionError] = useState("");
  const [transcriptionBusy, setTranscriptionBusy] = useState(false);
  const [turnBusy, setTurnBusy] = useState(false);
  const turnBusyRef = useRef(false);
  const transcriptionBusyRef = useRef(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([
    { id: "welcome", role: "tutor", text: `Namaste! I’m ${tutor.display_name}. Tell me about your day.` },
  ]);
  const [feedback, setFeedback] = useState({ grammar: "", incorrect: "", corrected: "", words: [] as string[], telugu: "" });
  const [presentation, dispatch] = useReducer(reduceTutorPresentation, initialTutorPresentation);
  const [consent, setConsent] = useState(false);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    api.conversation(account.learner_id)
      .then((result) => setId(result.id))
      .catch(() => dispatch({ type: "FAIL", errorCode: "conversation_start_failed" }));
  }, [account.learner_id]);

  useEffect(() => {
    console.info("speakmate_avatar_event", {
      state: presentation.state,
      expression: presentation.expression,
      mouth: presentation.mouth,
      playback_id: presentation.activePlaybackId ?? null,
      synchronization: presentation.state === "SPEAKING" ? "AUDIO_LIFECYCLE" : "NOT_SPEAKING",
      reduced_motion: reduced,
    });
  }, [presentation.activePlaybackId, presentation.expression, presentation.mouth, presentation.state, reduced]);

  useEffect(() => {
    if (presentation.state !== "ERROR" || presentation.errorCode !== "browser_audio_error") return;
    setAudioError("Tutor audio could not be played. Request a fresh copy and try again.");
  }, [presentation.errorCode, presentation.state]);

  const handleAudioLifecycle = useCallback((event: AudioLifecycleEvent) => {
    switch (event.type) {
      case "SOURCE_READY":
        dispatch({ type: "AUDIO_SOURCE_READY", playbackId: event.playbackId });
        break;
      case "PLAYBACK_STARTED":
        dispatch({ type: "AUDIO_PLAYBACK_STARTED", playbackId: event.playbackId });
        break;
      case "PLAYBACK_FRAME":
        dispatch({ type: "AUDIO_PLAYBACK_FRAME", playbackId: event.playbackId, currentTimeMs: event.currentTimeMs, durationMs: event.durationMs });
        break;
      case "PLAYBACK_PAUSED":
        dispatch({ type: "AUDIO_PLAYBACK_PAUSED", playbackId: event.playbackId });
        break;
      case "PLAYBACK_STOPPED":
        dispatch({ type: "AUDIO_PLAYBACK_STOPPED", playbackId: event.playbackId });
        break;
      case "PLAYBACK_ENDED":
        dispatch({ type: "AUDIO_PLAYBACK_ENDED", playbackId: event.playbackId });
        break;
      case "PLAYBACK_ERROR":
        dispatch({ type: "AUDIO_PLAYBACK_ERROR", playbackId: event.playbackId, errorCode: event.errorCode });
        break;
    }
  }, []);

  const loadSpeech = useCallback(async (turnId: string, expressionHint = lastExpression) => {
    if (!id || !turnId) {
      setAudioError("Tutor voice is not ready yet. Please retry the tutor response.");
      console.warn("speakmate_tts_event", { event: "request_not_made", reason: "missing_identity" });
      return;
    }
    const expression = normalizeExpression(expressionHint);
    dispatch({ type: "TUTOR_RESPONSE_READY", expression });
    setAudioBusy(true);
    setAudioError("");
    console.info("speakmate_tts_event", { event: "request_started", playback_id: turnId });
    try {
      const nextSpeech = await api.speech(id, turnId);
      setSpeech(nextSpeech);
      console.info("speakmate_tts_event", {
        event: "audio_fetch_succeeded",
        playback_id: turnId,
        provider: nextSpeech.provider,
        model: nextSpeech.model,
        voice: nextSpeech.voice,
        content_type: nextSpeech.blob.type,
        size_bytes: nextSpeech.blob.size,
      });
    } catch (error) {
      const backendFailure = error instanceof ApiError;
      setAudioError(error instanceof Error ? error.message : "Tutor voice is temporarily unavailable.");
      dispatch({ type: "FAIL", errorCode: "tts_request_failed" });
      console.warn("speakmate_tts_event", backendFailure
        ? { event: "backend_tts_failed", status: error.status, code: error.code, retryable: error.retryable, playback_id: turnId }
        : { event: "audio_fetch_failed", reason: "network_or_browser", playback_id: turnId });
    } finally {
      setAudioBusy(false);
    }
  }, [id, lastExpression]);

  const submit = useCallback(async (
    text: string,
    retryKey?: string,
    voice?: { detectedLanguage: string; confidence?: number | null },
  ) => {
    const learnerText = text.trim();
    if (!learnerText || !id || turnBusyRef.current) return;
    const key = retryKey ?? turnIdentity();
    turnBusyRef.current = true;
    setTurnError("");
    setAudioError("");
    setSpeech(null);
    setInterruptSequence((value) => value + 1);
    setTurnBusy(true);
    if (!retryKey) {
      setMessages((items) => [...items, { id: `learner-${key}`, role: "learner", text: learnerText, source: voice ? "VOICE" : "TEXT" }]);
    }
    setInput("");
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    try {
      const result = await api.turn(id, learnerText, selectedLanguageMode, key, voice);
      const spoken = result.spoken_text || `${result.tutor_message} ${result.next_question}`.trim();
      const expression = normalizeExpression(result.expression_hint);
      setMessages((items) => [...items, { id: `tutor-${result.turn_id || key}`, role: "tutor", text: spoken }]);
      setSpokenText(spoken);
      setLastExpression(expression);
      setFeedback({
        grammar: result.correction_explanation || (result.coaching_state === "WAITING_FOR_RETRY" ? "Almost—please try the corrected sentence once more." : ""),
        incorrect: result.incorrect_span || "",
        corrected: result.corrected_form || result.corrected_sentence || "",
        words: result.vocabulary_suggestions,
        telugu: result.telugu_explanation || "",
      });
      setPendingTurn(null);
      dispatch({ type: "TUTOR_RESPONSE_READY", expression });
      if (!result.turn_id) {
        setAudioError("Tutor voice is not ready for this response. You can continue reading or retry your response.");
        dispatch({ type: "FAIL", errorCode: "missing_turn_id" });
        console.warn("speakmate_tts_event", { event: "request_not_made", reason: "missing_turn_id" });
      } else {
        setLastSpeechTurn(result.turn_id);
        await loadSpeech(result.turn_id, expression);
      }
    } catch (error) {
      dispatch({ type: "FAIL", errorCode: "tutor_turn_failed" });
      const retryable = error instanceof ApiError ? error.retryable : true;
      setPendingTurn({ text: learnerText, key, retryable });
      setInput(learnerText);
      setTurnError(error instanceof Error ? error.message : "The tutor is temporarily unavailable. Please try again.");
    } finally {
      turnBusyRef.current = false;
      setTurnBusy(false);
    }
  }, [id, loadSpeech, selectedLanguageMode]);

  const transcribeCapture = useCallback(async (capture: CapturedAudio, key: string) => {
    if (!id) throw new Error("The conversation is still loading. Please try again.");
    if (transcriptionBusyRef.current) return;
    transcriptionBusyRef.current = true;
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    setTranscriptionBusy(true);
    setTranscriptionError("");
    let result: VoiceTranscription;
    try {
      result = await api.transcribe(id, { blob: capture.blob, durationMs: capture.durationMs }, key);
    } catch (error) {
      setPendingTranscription(canRetryTranscription(error) ? { capture, key } : null);
      setTranscriptionError(error instanceof Error ? error.message : "Speech recognition failed.");
      dispatch({ type: "FAIL", errorCode: "microphone_error" });
      throw error;
    } finally {
      transcriptionBusyRef.current = false;
      setTranscriptionBusy(false);
    }
    setPendingTranscription(null);
    setLastTranscript(result.transcript);
    setInput(result.transcript);
    await submit(result.transcript, undefined, { detectedLanguage: result.detected_language, confidence: result.confidence });
  }, [id, submit]);

  const handleCapture = useCallback(
    (capture: CapturedAudio) => transcribeCapture(capture, turnIdentity()),
    [transcribeCapture],
  );
  const mic = useMicrophone(consent, handleCapture);

  useEffect(() => {
    if (consent) return;
    setPendingTranscription(null);
    setTranscriptionError("");
  }, [consent]);

  useEffect(() => {
    if (mic.state === "recording") dispatch({ type: "MICROPHONE_STARTED" });
    if (mic.state === "cancelled") dispatch({ type: "RESET" });
    if (["denied", "no_speech", "too_large", "error"].includes(mic.state)) {
      dispatch({ type: "FAIL", errorCode: `microphone_${mic.state}` });
    }
  }, [mic.state]);

  const startMicrophone = async () => {
    setPendingTranscription(null);
    setTranscriptionError("");
    setInterruptSequence((value) => value + 1);
    dispatch({ type: "RESET" });
    await mic.start();
  };

  const cancelMicrophone = () => {
    setPendingTranscription(null);
    setTranscriptionError("");
    mic.cancel();
    dispatch({ type: "RESET" });
  };

  const retryTranscription = async () => {
    if (!pendingTranscription || transcriptionBusyRef.current) return;
    mic.retry();
    try {
      await transcribeCapture(pendingTranscription.capture, pendingTranscription.key);
    } catch {
      // The safe error and retry state are owned by transcribeCapture.
    }
  };

  const discardTranscription = () => {
    setPendingTranscription(null);
    setTranscriptionError("");
    mic.retry();
    dispatch({ type: "RESET" });
  };

  const microphoneState = transcriptionBusy ? "processing" : mic.state;
  const microphoneError = transcriptionError || mic.errorMessage;
  const microphoneStatus = ({
    unavailable: "Microphone unavailable",
    idle: "Microphone ready",
    requesting_permission: "Waiting for microphone permission",
    recording: "Listening",
    processing: "Processing speech",
    denied: "Microphone permission denied",
    no_speech: "No speech detected",
    too_large: "Recording was too long",
    cancelled: "Recording cancelled",
    error: "Microphone unavailable",
  } as Record<string, string>)[microphoneState] ?? "Microphone ready";
  const currentLearnerMessage = latestMessage(messages, "learner");
  const currentTutorMessage = latestMessage(messages, "tutor");
  const compactHistory = messages.filter((message) => message !== currentLearnerMessage && message !== currentTutorMessage);
  const hasCorrection = Boolean(feedback.incorrect || feedback.corrected || feedback.grammar);
  const hasTeluguExplanation = selectedLanguageMode !== "ENGLISH" && Boolean(feedback.telugu) && feedback.telugu !== feedback.grammar;
  const showVoiceCoaching = hasCorrection || hasTeluguExplanation;
  const showCoach = practiceMode === "TEXT" || showVoiceCoaching;
  const startMicrophoneLabel = mic.state === "denied" ? "Retry microphone" : "Start microphone";

  return (
    <section className={`conversation-experience mode-${practiceMode.toLowerCase()}${showVoiceCoaching ? " has-coaching" : ""}`} data-practice-mode={practiceMode}>
      <div className="practice-mode-switch" role="group" aria-label="Practice mode">
        <button type="button" disabled={mic.state === "recording" || transcriptionBusy} aria-pressed={practiceMode === "VOICE"} onClick={() => setPracticeMode("VOICE")}>Voice mode</button>
        <button type="button" disabled={mic.state === "recording" || transcriptionBusy} aria-pressed={practiceMode === "TEXT"} onClick={() => setPracticeMode("TEXT")}>Text mode</button>
      </div>

      <div className="conversation-layout">
        <section className="studio voice-classroom" aria-label={`${tutor.display_name} live lesson`}>
          {lessonTitle && <p className="lesson-context"><span>Current lesson</span><strong>{lessonTitle}</strong></p>}
          <Avatar tutor={tutor} presentation={presentation} reducedMotion={reduced} />

          <section className="current-exchange" aria-label="Current conversation" aria-live="polite" hidden={practiceMode !== "VOICE"}>
            {practiceMode === "VOICE" && <>
              <p aria-label={currentLearnerMessage?.source === "VOICE" ? "Latest recognized transcript" : "Latest learner message"}><strong>You</strong><span>{currentLearnerMessage?.text || lastTranscript || "Your latest speech will appear here."}</span></p>
              <p aria-label="Current tutor response"><strong>{tutor.display_name}</strong><span>{currentTutorMessage?.text || "Your tutor’s response will appear here."}</span></p>
            </>}
          </section>

          <details className="conversation-history" hidden={practiceMode !== "VOICE"}>
            {practiceMode === "VOICE" && <>
              <summary>Conversation history <span>({compactHistory.length})</span></summary>
              <div className="transcript" aria-label="Earlier conversation">
                {compactHistory.length === 0
                  ? <p>No earlier messages yet.</p>
                  : compactHistory.map((message) => <p key={message.id}><strong>{message.role === "learner" ? "You" : tutor.display_name}:</strong> {message.text}</p>)}
              </div>
            </>}
          </details>

          <div className="transcript text-conversation-history" aria-live="polite" aria-label="Conversation history" hidden={practiceMode !== "TEXT"}>
            {practiceMode === "TEXT" && messages.map((message) => (
              <p key={message.id}><strong>{message.role === "learner" ? "You" : tutor.display_name}:</strong> {message.text}</p>
            ))}
          </div>

          <details className="text-entry" open={practiceMode === "TEXT" ? true : undefined}>
            <summary>{practiceMode === "VOICE" ? "Type instead" : "Write your message"}</summary>
            <label htmlFor="message">Your message</label>
            <div className="composer">
              <input id="message" value={input} disabled={turnBusy} onChange={(event) => setInput(event.target.value)} />
              <button disabled={turnBusy} onClick={() => void submit(input, pendingTurn?.retryable && pendingTurn.text === input.trim() ? pendingTurn.key : undefined)}>
                {turnBusy ? "Waiting for tutor…" : "Send"}
              </button>
            </div>
          </details>

          {turnError && <div className="learner-error"><p role="alert">{turnError}</p>{pendingTurn?.retryable && <button disabled={turnBusy} onClick={() => void submit(pendingTurn.text, pendingTurn.key)}>Retry tutor response</button>}</div>}

          <div className="voice-control-dock">
            <fieldset className="microphone-controls">
              <legend>Speak to {tutor.display_name}</legend>
              <label className="voice-consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I consent to voice processing for this turn</label>
              <p className={practiceMode === "VOICE" ? "sr-only" : "microphone-state"} aria-live="polite">{microphoneStatus}</p>
              <div className="microphone-actions">
                <button aria-label={startMicrophoneLabel} disabled={!consent || !id || turnBusy || transcriptionBusy || mic.state === "recording" || mic.state === "processing"} onClick={() => void startMicrophone()}>{mic.state === "denied" ? "Retry microphone" : "🎤 Speak"}</button>
                <button aria-label="Stop and transcribe" disabled={mic.state !== "recording"} onClick={mic.stop}>■ Stop</button>
                <button aria-label="Cancel recording" disabled={mic.state !== "recording"} onClick={cancelMicrophone}>Cancel</button>
              </div>
              {microphoneError && <p role="alert">{microphoneError} {mic.state === "denied" && "Enable microphone access in your browser settings, then retry."}</p>}
              {pendingTranscription && <div className="voice-recovery"><button disabled={transcriptionBusy || turnBusy} onClick={() => void retryTranscription()}>Retry transcription</button><button disabled={transcriptionBusy} onClick={discardTranscription}>Discard recording</button></div>}
            </fieldset>

            <TutorAudioPlayer
              speech={speech}
              spokenText={spokenText}
              playbackId={lastSpeechTurn}
              interruptSequence={interruptSequence}
              compact={practiceMode === "VOICE"}
              onLifecycle={handleAudioLifecycle}
            />
          </div>

          {audioBusy && <p className="voice-progress" role="status">Preparing tutor voice…</p>}
          {audioError && <div className="learner-error"><p role="alert">{audioError}</p>{lastSpeechTurn && <button disabled={audioBusy} onClick={() => void loadSpeech(lastSpeechTurn)}>Retry tutor voice</button>}</div>}
        </section>

        {showCoach && <aside className="coach" aria-live="polite" aria-label="Live coaching">
          <h2>Live coaching</h2>
          {practiceMode === "VOICE" ? (
            <>
              {hasCorrection && <section className="compact-correction" aria-label="Current grammar correction">
                <h3>Correction</h3>
                {feedback.incorrect && <p><span>Try</span><s>{feedback.incorrect}</s></p>}
                {feedback.corrected && <p><span>Say</span><strong>{feedback.corrected}</strong></p>}
                {feedback.grammar && <p>{feedback.grammar}</p>}
              </section>}
              {hasTeluguExplanation && <section className="compact-telugu" aria-label="Telugu explanation"><h3>తెలుగు సహాయం</h3><p>{feedback.telugu}</p></section>}
            </>
          ) : (
            <>
              <h3>Grammar correction</h3>
              {feedback.incorrect && <p><strong>Incorrect:</strong> {feedback.incorrect}</p>}
              {feedback.corrected && <p><strong>Correct:</strong> {feedback.corrected}</p>}
              <p>{feedback.grammar || "No correction needed yet."}</p>
              <h3>Vocabulary</h3>
              <div className="chips">{feedback.words.length ? feedback.words.map((word) => <span key={word}>{word}</span>) : <span>No suggestions yet.</span>}</div>
              {selectedLanguageMode !== "ENGLISH" && feedback.telugu && <><h3>Telugu explanation</h3><p>{feedback.telugu}</p></>}
            </>
          )}
        </aside>}
      </div>
    </section>
  );
}
