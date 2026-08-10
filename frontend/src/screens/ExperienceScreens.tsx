import { useCallback, useEffect, useRef, useState } from "react";
import { normalizeExpression } from "../avatar/machine";
import { ApiError, api } from "../api/client";
import { useAuth as requireAuth } from "../auth/AuthProvider";
import { Avatar } from "../components/Avatar";
import type { Account, CurriculumLesson, Dashboard, LanguageMode, Tutor, TutorSpeech, VoiceTranscription } from "../models";
import { useSpeakMateMultimediaRuntime } from "../multimedia";
import { useRouter } from "../routes/router";
import {
  createConversationLatencyTrace,
  emitConversationLatency,
  markConversationLatency,
  type ConversationLatencyTrace,
} from "../telemetry/conversation-latency";
import {
  engineeringDiagnosticInfo,
  engineeringDiagnosticWarning,
} from "../telemetry/engineering-diagnostics";
import { TutorAudioPlayer, type AudioLifecycleEvent, type TutorAudioPlayerHandle } from "../voice/TutorAudioPlayer";
import { useMicrophone, type CapturedAudio } from "../voice/useMicrophone";

const ACTIVE_LESSON_TITLE_KEY = "speakmate.active-lesson-title.v1";
const ACTIVE_LESSON_KEY = "speakmate.active-lesson.v1";

interface ActiveLesson {
  learnerId: string;
  lesson: CurriculumLesson;
  sessionId: string;
  startedAt: number;
}

function readActiveLesson(learnerId: string): ActiveLesson | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(ACTIVE_LESSON_KEY) ?? "null") as ActiveLesson | null;
    return value?.learnerId === learnerId && value.lesson?.id && value.sessionId ? value : null;
  } catch {
    return null;
  }
}

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
  const { account } = useAuthBridge();
  const [lesson, setLesson] = useState<CurriculumLesson | null>(() => account ? readActiveLesson(account.learner_id)?.lesson ?? null : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = account ? readActiveLesson(account.learner_id) : null;
  useEffect(() => {
    if (!account || lesson) return;
    api.dailyLesson(account.learner_id).then(setLesson).catch(() => setError("Today's lesson could not be loaded. Please retry."));
  }, [account, lesson]);
  const beginLesson = async () => {
    if (!account || !lesson || busy) return;
    if (active) {
      navigate("/app/conversation");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const session = await api.createLessonSession(account.learner_id, lesson.id);
      const value: ActiveLesson = { learnerId: account.learner_id, lesson, sessionId: session.id, startedAt: Date.now() };
      sessionStorage.setItem(ACTIVE_LESSON_KEY, JSON.stringify(value));
      sessionStorage.setItem(ACTIVE_LESSON_TITLE_KEY, lesson.title);
      navigate("/app/conversation");
    } catch {
      setError("The lesson could not be started. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  if (!lesson) return <section className="page"><h1>Structured learning</h1><p>{error || "Preparing today's lesson…"}</p></section>;
  return (
    <section className="page">
      <h1>{lesson.title}</h1>
      <article className="lesson">
        <b>{lesson.estimated_duration_minutes} minutes · {lesson.category}</b>
        <h2>{lesson.practice_prompt}</h2>
        <p>{lesson.instruction_prompt}</p>
        <ol><li>Listen to Ananya's instruction</li><li>Respond and retry any genuine correction</li><li>Complete the roleplay: {lesson.roleplay_prompt}</li></ol>
        {error && <p role="alert">{error}</p>}
        <button disabled={busy} onClick={() => void beginLesson()}>{active ? "Resume lesson" : busy ? "Starting…" : "Begin lesson"}</button>
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
  const { navigate } = useRouter();
  const [activeLesson] = useState(() => readActiveLesson(account.learner_id));
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("VOICE");
  const [lessonTitle] = useState(() => sessionStorage.getItem(ACTIVE_LESSON_TITLE_KEY) ?? "");
  const [id, setId] = useState("");
  const [openingPrompt, setOpeningPrompt] = useState("");
  const [openingTurnId, setOpeningTurnId] = useState("");
  const [conversationStarted, setConversationStarted] = useState(false);
  const [avatarReady, setAvatarReady] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [greetingCompleted, setGreetingCompleted] = useState(false);
  const [input, setInput] = useState("");
  const [lastTranscript, setLastTranscript] = useState("");
  const [turnError, setTurnError] = useState("");
  const [lessonCompletionBusy, setLessonCompletionBusy] = useState(false);
  const [lessonCompletionError, setLessonCompletionError] = useState("");
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
  const openingSpeechRequested = useRef("");
  const startBusyRef = useRef(false);
  const conversationRequest = useRef<{
    key: string;
    promise: ReturnType<typeof api.conversation>;
  } | null>(null);
  const latencyBySpeechTurn = useRef(new Map<string, ConversationLatencyTrace>());
  const activeSpeechTurn = useRef("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [feedback, setFeedback] = useState({ grammar: "", incorrect: "", corrected: "", words: [] as string[], telugu: "" });
  const [consent, setConsent] = useState(false);
  const reduced = usePrefersReducedMotion();
  const {
    presentation,
    playbackSignal,
    dispatch,
    dispatchAudioLifecycle,
    attachAudioTransport,
    playAudio,
    replayAudio,
    pauseAudio,
    stopAudio,
    setAudioMuted,
  } = useSpeakMateMultimediaRuntime(reduced);
  const handleAudioPlayerRef = useCallback((player: TutorAudioPlayerHandle | null) => {
    attachAudioTransport(player);
  }, [attachAudioTransport]);
  const conversationSessionKey = `${account.learner_id}:${tutor.tutor_id}`;

  useEffect(() => {
    const requestKey = conversationSessionKey;
    const request = conversationRequest.current?.key === requestKey
      ? conversationRequest.current.promise
      : api.conversation(account.learner_id, activeLesson?.lesson);
    conversationRequest.current = { key: requestKey, promise: request };
    let active = true;
    request
      .then((result) => {
        if (!active) return;
        const prompt = result.opening_prompt?.trim()
          || `Namaste! I’m ${tutor.display_name}. Tell me about your day.`;
        const openingId = result.opening_turn_id?.trim() || "";
        setId(result.id);
        setOpeningPrompt(prompt);
        setOpeningTurnId(openingId);
        setMessages([{ id: `opening-${openingId || result.id}`, role: "tutor", text: prompt }]);
        if (!openingId) setConversationStarted(true);
      })
      .catch(() => {
        if (active) dispatch({ type: "FAIL", errorCode: "conversation_start_failed" });
      });
    return () => {
      active = false;
    };
  }, [account.learner_id, activeLesson?.lesson, conversationSessionKey, dispatch, tutor.display_name, tutor.tutor_id]);

  useEffect(() => {
    engineeringDiagnosticInfo("speakmate_avatar_event", {
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
    dispatchAudioLifecycle(event);
    switch (event.type) {
      case "SOURCE_READY":
        break;
      case "PLAYBACK_STARTED":
        {
          const trace = latencyBySpeechTurn.current.get(event.playbackId);
          if (trace) {
            markConversationLatency(trace, "t8");
            emitConversationLatency(trace);
            latencyBySpeechTurn.current.delete(event.playbackId);
          }
        }
        break;
      case "PLAYBACK_FRAME": {
        break;
      }
      case "PLAYBACK_PAUSED":
        break;
      case "PLAYBACK_STOPPED":
        break;
      case "PLAYBACK_ENDED":
        if (event.playbackId === openingSpeechRequested.current) setGreetingCompleted(true);
        break;
      case "PLAYBACK_ERROR":
        break;
    }
  }, [dispatchAudioLifecycle]);

  const loadSpeech = useCallback(async (
    turnId: string,
    expressionHint = lastExpression,
    latencyTrace?: ConversationLatencyTrace,
  ) => {
    if (!id || !turnId) {
      setAudioError("Tutor voice is not ready yet. Please retry the tutor response.");
      engineeringDiagnosticWarning("speakmate_tts_event", { event: "request_not_made", reason: "missing_identity" });
      return;
    }
    const expression = normalizeExpression(expressionHint);
    const activeLatencyTrace = latencyTrace ?? latencyBySpeechTurn.current.get(turnId);
    activeSpeechTurn.current = turnId;
    dispatch({ type: "TUTOR_RESPONSE_READY", expression });
    setAudioBusy(true);
    setAudioError("");
    engineeringDiagnosticInfo("speakmate_tts_event", { event: "request_started", playback_id: turnId });
    if (activeLatencyTrace) {
      latencyBySpeechTurn.current.set(turnId, activeLatencyTrace);
      markConversationLatency(activeLatencyTrace, "t6");
    }
    try {
      const nextSpeech = await api.speech(id, turnId);
      if (activeSpeechTurn.current !== turnId) {
        latencyBySpeechTurn.current.delete(turnId);
        engineeringDiagnosticInfo("speakmate_tts_event", { event: "stale_audio_ignored", playback_id: turnId });
        return;
      }
      if (activeLatencyTrace) markConversationLatency(activeLatencyTrace, "t7");
      setSpeech(nextSpeech);
      engineeringDiagnosticInfo("speakmate_tts_event", {
        event: "audio_fetch_succeeded",
        playback_id: turnId,
        provider: nextSpeech.provider,
        model: nextSpeech.model,
        voice: nextSpeech.voice,
        content_type: nextSpeech.blob.type,
        size_bytes: nextSpeech.blob.size,
      });
    } catch (error) {
      if (activeSpeechTurn.current !== turnId) return;
      const backendFailure = error instanceof ApiError;
      setAudioError(error instanceof Error ? error.message : "Tutor voice is temporarily unavailable.");
      dispatch({ type: "FAIL", errorCode: "tts_request_failed" });
      engineeringDiagnosticWarning("speakmate_tts_event", backendFailure
        ? { event: "backend_tts_failed", status: error.status, code: error.code, retryable: error.retryable, playback_id: turnId }
        : { event: "audio_fetch_failed", reason: "network_or_browser", playback_id: turnId });
    } finally {
      if (activeSpeechTurn.current === turnId) setAudioBusy(false);
    }
  }, [dispatch, id, lastExpression]);

  useEffect(() => {
    if (!id || !openingTurnId || !openingPrompt || openingSpeechRequested.current === openingTurnId) return;
    openingSpeechRequested.current = openingTurnId;
    setLastSpeechTurn(openingTurnId);
    setSpokenText(openingPrompt);
    void loadSpeech(openingTurnId, "NEUTRAL");
  }, [id, loadSpeech, openingPrompt, openingTurnId]);

  const startConversation = async () => {
    if (conversationStarted || startBusyRef.current) return;
    if (!openingTurnId) {
      setConversationStarted(true);
      return;
    }
    startBusyRef.current = true;
    setStartBusy(true);
    try {
      const started = await playAudio();
      if (started) {
        setAudioError("");
        setConversationStarted(true);
      } else {
        setAudioError("Your tutor voice is ready. Select Start conversation to try again.");
      }
    } finally {
      startBusyRef.current = false;
      setStartBusy(false);
    }
  };

  const continueWithoutOpeningAudio = () => {
    setConversationStarted(true);
    dispatch({ type: "RESET" });
  };

  const submit = useCallback(async (
    text: string,
    retryKey?: string,
    voice?: { detectedLanguage: string; confidence?: number | null },
    latencyTrace?: ConversationLatencyTrace,
    requestKey?: string,
  ) => {
    const learnerText = text.trim();
    if (!learnerText || !id || turnBusyRef.current) return;
    const key = retryKey ?? requestKey ?? turnIdentity();
    const trace = latencyTrace ?? createConversationLatencyTrace(voice ? "VOICE" : "TEXT");
    turnBusyRef.current = true;
    setTurnError("");
    setAudioError("");
    activeSpeechTurn.current = "";
    setAudioBusy(false);
    setSpeech(null);
    setInterruptSequence((value) => value + 1);
    setTurnBusy(true);
    if (!retryKey) {
      setMessages((items) => items.some((item) => item.id === `learner-${key}`)
        ? items
        : [...items, { id: `learner-${key}`, role: "learner", text: learnerText, source: voice ? "VOICE" : "TEXT" }]);
    }
    setInput("");
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    markConversationLatency(trace, "uiFeedbackAt");
    try {
      markConversationLatency(trace, "t3");
      const result = await api.turn(id, learnerText, selectedLanguageMode, key, voice);
      const tutorOutputReady = performance.now();
      markConversationLatency(trace, "t4", tutorOutputReady);
      markConversationLatency(trace, "t5", tutorOutputReady);
      const spoken = result.spoken_text || `${result.tutor_message} ${result.next_question}`.trim();
      const expression = normalizeExpression(result.expression_hint);
      const tutorMessageId = `tutor-${result.turn_id || key}`;
      setMessages((items) => items.some((item) => item.id === tutorMessageId)
        ? items
        : [...items, { id: tutorMessageId, role: "tutor", text: spoken }]);
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
        engineeringDiagnosticWarning("speakmate_tts_event", { event: "request_not_made", reason: "missing_turn_id" });
      } else {
        setLastSpeechTurn(result.turn_id);
        void loadSpeech(result.turn_id, expression, trace);
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
  }, [dispatch, id, loadSpeech, selectedLanguageMode]);

  const transcribeCapture = useCallback(async (capture: CapturedAudio, key: string) => {
    if (!id) throw new Error("The conversation is still loading. Please try again.");
    if (transcriptionBusyRef.current) return;
    transcriptionBusyRef.current = true;
    const trace = createConversationLatencyTrace("VOICE", capture.finishedAtMonotonicMs ?? performance.now());
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    markConversationLatency(trace, "uiFeedbackAt");
    setTranscriptionBusy(true);
    setTranscriptionError("");
    let result: VoiceTranscription;
    try {
      markConversationLatency(trace, "t1");
      result = await api.transcribe(id, { blob: capture.blob, durationMs: capture.durationMs }, key);
      markConversationLatency(trace, "t2");
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
    await submit(
      result.transcript,
      undefined,
      { detectedLanguage: result.detected_language, confidence: result.confidence },
      trace,
      `${key}-turn`,
    );
  }, [dispatch, id, submit]);

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
  }, [dispatch, mic.state]);

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
  const learnerTurnCount = messages.filter((message) => message.role === "learner").length;
  const completeLesson = async () => {
    if (!activeLesson || lessonCompletionBusy || learnerTurnCount < 2) return;
    setLessonCompletionBusy(true);
    setLessonCompletionError("");
    try {
      const durationSeconds = Math.max(1, Math.round((Date.now() - activeLesson.startedAt) / 1000));
      await api.completeLessonSession(activeLesson.sessionId, durationSeconds);
      sessionStorage.removeItem(ACTIVE_LESSON_KEY);
      sessionStorage.removeItem(ACTIVE_LESSON_TITLE_KEY);
      navigate("/app/daily-lesson");
    } catch {
      setLessonCompletionError("Your progress could not be saved. Please retry lesson completion.");
    } finally {
      setLessonCompletionBusy(false);
    }
  };

  return (
    <section
      className={`conversation-experience mode-${practiceMode.toLowerCase()}${showVoiceCoaching ? " has-coaching" : ""}`}
      data-practice-mode={practiceMode}
      data-greeting-completed={greetingCompleted}
    >
      <div className="practice-mode-switch" role="group" aria-label="Practice mode">
        <button type="button" disabled={!conversationStarted || mic.state === "recording" || transcriptionBusy} aria-pressed={practiceMode === "VOICE"} onClick={() => setPracticeMode("VOICE")}>Voice mode</button>
        <button type="button" disabled={!conversationStarted || mic.state === "recording" || transcriptionBusy} aria-pressed={practiceMode === "TEXT"} onClick={() => setPracticeMode("TEXT")}>Text mode</button>
      </div>

      <div className="conversation-layout">
        <section className="studio voice-classroom" aria-label={`${tutor.display_name} live lesson`}>
          {lessonTitle && <p className="lesson-context"><span>Current lesson</span><strong>{lessonTitle}</strong></p>}
          <Avatar
            key={conversationSessionKey}
            tutor={tutor}
            presentation={presentation}
            reducedMotion={reduced}
            playbackSignal={playbackSignal}
            onReady={() => setAvatarReady(true)}
          />

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
              <button disabled={!conversationStarted || turnBusy} onClick={() => void submit(input, pendingTurn?.retryable && pendingTurn.text === input.trim() ? pendingTurn.key : undefined)}>
                {turnBusy ? "Waiting for tutor…" : "Send"}
              </button>
            </div>
          </details>

          {turnError && <div className="learner-error"><p role="alert">{turnError}</p>{pendingTurn?.retryable && <button disabled={turnBusy} onClick={() => void submit(pendingTurn.text, pendingTurn.key)}>Retry tutor response</button>}</div>}
          {activeLesson && <section className="lesson-completion" aria-label="Lesson progress">
            <p>{Math.min(learnerTurnCount, 2)} of 2 practice responses completed.</p>
            <button disabled={learnerTurnCount < 2 || lessonCompletionBusy || turnBusy} onClick={() => void completeLesson()}>
              {lessonCompletionBusy ? "Saving progress…" : "Complete lesson"}
            </button>
            {lessonCompletionError && <p role="alert">{lessonCompletionError}</p>}
          </section>}

          <div className={`voice-control-dock${conversationStarted ? "" : " prestart"}`}>
            {!conversationStarted ? <section className="start-conversation-gate" aria-label="Start live lesson">
              <strong>{speech ? `${tutor.display_name} is ready.` : `Preparing ${tutor.display_name}…`}</strong>
              <p>Start once to hear the welcome and begin your live lesson.</p>
              <button type="button" disabled={!id || !speech || !avatarReady || audioBusy || startBusy} onClick={() => void startConversation()}>
                {startBusy ? "Starting…" : "Start conversation"}
              </button>
              {audioError && !speech && <button type="button" className="secondary" onClick={continueWithoutOpeningAudio}>Continue without audio</button>}
            </section> : <fieldset className="microphone-controls">
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
            </fieldset>}

            <TutorAudioPlayer
              ref={handleAudioPlayerRef}
              speech={speech}
              spokenText={spokenText}
              playbackId={lastSpeechTurn}
              interruptSequence={interruptSequence}
              compact={practiceMode === "VOICE"}
              autoPlay={Boolean(lastSpeechTurn) && lastSpeechTurn !== openingTurnId}
              trackAmplitude={!reduced}
              controlsVisible={conversationStarted}
              commandPort={{
                play: playAudio,
                replay: replayAudio,
                pause: pauseAudio,
                stop: stopAudio,
                setMuted: setAudioMuted,
              }}
              onAutoplayBlocked={() => setAudioError("Tutor voice is ready. Select Play tutor voice to continue.")}
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
