import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { normalizeExpression, initialTutorPresentation, reduceTutorPresentation } from "../avatar/machine";
import { ApiError, api } from "../api/client";
import { useAuth as requireAuth } from "../auth/AuthProvider";
import { Avatar } from "../components/Avatar";
import type { Account, Dashboard, LanguageMode, Tutor, TutorSpeech, VoiceTranscription } from "../models";
import { useRouter } from "../routes/router";
import { TutorAudioPlayer, type AudioLifecycleEvent } from "../voice/TutorAudioPlayer";
import { useMicrophone, type CapturedAudio } from "../voice/useMicrophone";

export function DashboardScreen({ data, tutor }: { data: Dashboard; tutor: Tutor }) {
  const { navigate } = useRouter();
  return <section className="page"><h1>Ready for today’s conversation?</h1><div className="dashboard-grid"><article className="hero-card"><img src={tutor.avatar_profile} alt={`${tutor.display_name}, your tutor`} /><div><h2>{tutor.display_name}</h2><p>{tutor.teaching_style}</p><button onClick={() => navigate("/app/conversation")}>Start speaking</button></div></article>{[[data.current_streak_days, "day streak"], [data.completed_sessions, "sessions"], [data.total_practice_minutes, "minutes"]].map(([value, label]) => <article className="metric" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>;
}

export function DailyLessonScreen() {
  const { navigate } = useRouter();
  return <section className="page"><h1>A confident morning routine</h1><article className="lesson"><b>10 minutes · Indian English</b><h2>Describe your morning clearly</h2><p>Use usually, afterwards, and routine. Focus on present simple and natural sentence stress.</p><ol><li>Warm-up and listen</li><li>Speak naturally</li><li>Review grammar and vocabulary</li></ol><button onClick={() => navigate("/app/conversation")}>Begin lesson</button></article></section>;
}

export function ProgressScreen({ data }: { data: Dashboard }) {
  return <section className="page"><h1>Small practice. Real momentum.</h1><div className="progress-grid">{[[data.current_streak_days, "Current streak"], [data.completed_sessions, "Completed sessions"], [data.total_practice_minutes, "Practice minutes"]].map(([value, label]) => <article key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>;
}

export function SettingsScreen({ data, tutor, onChange }: { data: Dashboard; tutor: Tutor; onChange: () => void }) {
  const { logoutAll } = useAuthBridge();
  const plan = data.subscription_tier.replaceAll("_", " ");
  const status = data.subscription_status.replaceAll("_", " ");
  return <section className="page"><h1>Make practice feel like yours.</h1><article className="settings-card"><img src={tutor.avatar_profile} alt="" /><div><h2>{tutor.display_name}</h2><p>{tutor.voice_profile}</p><button onClick={onChange}>Change tutor</button></div></article><p><strong>Subscription:</strong> {plan} · {status}.</p><button onClick={() => void logoutAll()}>Log out on all devices</button></section>;
}

function useAuthBridge() {
  return requireAuth();
}

function turnIdentity() {
  return globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function canRetryTranscription(error: unknown) {
  if (error instanceof ApiError) {
    return error.retryable && [409, 503, 504].includes(error.status);
  }
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
  const [id, setId] = useState("");
  const [input, setInput] = useState("");
  const [lastTranscript, setLastTranscript] = useState("");
  const [turnError, setTurnError] = useState("");
  const [audioError, setAudioError] = useState("");
  const [audioPathStatus, setAudioPathStatus] = useState("Waiting for the first tutor response.");
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
  const [messages, setMessages] = useState<string[]>([`Namaste! I’m ${tutor.display_name}. Tell me about your day.`]);
  const [feedback, setFeedback] = useState({ grammar: "Your correction will appear here.", incorrect: "", corrected: "", words: [] as string[], telugu: "" });
  const [languageReview, setLanguageReview] = useState({ changed: false, reason: "Waiting for the first reviewed response.", terms: [] as string[] });
  const [presentation, dispatch] = useReducer(reduceTutorPresentation, initialTutorPresentation);
  const [consent, setConsent] = useState(false);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    api.conversation(account.learner_id).then((result) => setId(result.id)).catch(() => dispatch({ type: "FAIL", errorCode: "conversation_start_failed" }));
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
    setAudioPathStatus("Browser audio playback failed. Use Retry OpenAI voice to fetch a fresh audio source.");
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
      setAudioPathStatus("TTS request not made: missing conversation or tutor turn identity.");
      console.warn("speakmate_tts_event", { event: "request_not_made", reason: "missing_identity" });
      return;
    }
    const expression = normalizeExpression(expressionHint);
    dispatch({ type: "TUTOR_RESPONSE_READY", expression });
    setAudioBusy(true);
    setAudioError("");
    setAudioPathStatus("Requesting OpenAI tutor audio from the backend…");
    console.info("speakmate_tts_event", { event: "request_started", playback_id: turnId });
    try {
      const nextSpeech = await api.speech(id, turnId);
      setSpeech(nextSpeech);
      setAudioPathStatus("OpenAI tutor audio received. Avatar waits for real Chrome playback…");
      console.info("speakmate_tts_event", { event: "audio_fetch_succeeded", playback_id: turnId, provider: nextSpeech.provider, model: nextSpeech.model, voice: nextSpeech.voice, content_type: nextSpeech.blob.type, size_bytes: nextSpeech.blob.size });
    } catch (error) {
      const backendFailure = error instanceof ApiError;
      setAudioError(error instanceof Error ? error.message : "Tutor voice is temporarily unavailable.");
      setAudioPathStatus(backendFailure ? "Backend TTS request failed. Use Retry OpenAI voice." : "Audio fetch failed before a backend response. Check the browser network connection.");
      dispatch({ type: "FAIL", errorCode: "tts_request_failed" });
      console.warn("speakmate_tts_event", backendFailure ? { event: "backend_tts_failed", status: error.status, code: error.code, retryable: error.retryable, playback_id: turnId } : { event: "audio_fetch_failed", reason: "network_or_browser", playback_id: turnId });
    } finally {
      setAudioBusy(false);
    }
  }, [id, lastExpression]);

  const submit = useCallback(async (text: string, retryKey?: string, voice?: {detectedLanguage:string;confidence?:number|null}) => {
    const learnerText = text.trim();
    if (!learnerText || !id || turnBusyRef.current) return;
    const key = retryKey ?? turnIdentity();
    turnBusyRef.current = true;
    setTurnError("");
    setAudioError("");
    setAudioPathStatus("Waiting for the tutor text response before requesting audio…");
    setSpeech(null);
    setInterruptSequence((value) => value + 1);
    setTurnBusy(true);
    if (!retryKey) setMessages((items) => [...items, `You: ${learnerText}`]);
    setInput("");
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    try {
      const result = await api.turn(id, learnerText, selectedLanguageMode, key, voice);
      const spoken = result.spoken_text || `${result.tutor_message} ${result.next_question}`.trim();
      const expression = normalizeExpression(result.expression_hint);
      setMessages((items) => [...items, `${tutor.display_name}: ${spoken}`]);
      setSpokenText(spoken);
      setLastExpression(expression);
      setFeedback({ grammar: result.correction_explanation || (result.coaching_state === "WAITING_FOR_RETRY" ? "Almost—please try the corrected sentence once more." : "That sentence works well."), incorrect: result.incorrect_span || "", corrected: result.corrected_form || result.corrected_sentence || "", words: result.vocabulary_suggestions, telugu: result.telugu_explanation || "Telugu explanation will appear when the conversation provider supplies it." });
      setLanguageReview({ changed: Boolean(result.review_changed), reason: result.review_reason_code || "NOT_REQUIRED", terms: result.preserved_learning_terms || [] });
      setPendingTurn(null);
      dispatch({ type: "TUTOR_RESPONSE_READY", expression });
      if (!result.turn_id) {
        setAudioError("Tutor audio was not requested because the completed tutor turn identity is missing. Reload the latest frontend and retry.");
        setAudioPathStatus("TTS request not made: tutor response omitted its turn identity.");
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
  }, [id, loadSpeech, selectedLanguageMode, tutor.display_name]);

  const transcribeCapture = useCallback(async (capture: CapturedAudio, key: string) => {
    if (!id) throw new Error("The conversation is still loading. Please try again.");
    if (transcriptionBusyRef.current) return;
    transcriptionBusyRef.current = true;
    dispatch({ type: "TUTOR_PROCESSING_STARTED" });
    setTranscriptionBusy(true);
    setTranscriptionError("");
    let result: VoiceTranscription;
    try {
      result = await api.transcribe(
        id,
        { blob: capture.blob, durationMs: capture.durationMs },
        key,
      );
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

  return <div className="conversation-layout"><section className="studio"><Avatar tutor={tutor} presentation={presentation} reducedMotion={reduced} /><p className="avatar-sync-evidence"><strong>Avatar:</strong> {presentation.state.toLowerCase()} · {presentation.expression.toLowerCase()} expression · mouth {reduced ? "static (reduced motion)" : presentation.mouth.toLowerCase()}<br /><small>Speaking and mouth movement are driven by real tutor-audio playback events.</small></p><p className="capability-note"><strong>Language mode:</strong> {selectedLanguageMode.replaceAll("_", " + ")}</p><div className="transcript" aria-live="polite">{messages.map((message, index) => <p key={index}>{message}</p>)}</div><TutorAudioPlayer speech={speech} spokenText={spokenText} playbackId={lastSpeechTurn} interruptSequence={interruptSequence} onLifecycle={handleAudioLifecycle} /><p className="audio-path-status" role="status" aria-live="polite"><strong>Audio path:</strong> {audioPathStatus}</p>{audioBusy && <p role="status">Generating OpenAI tutor voice…</p>}{audioError && <div><p role="alert">{audioError}</p>{lastSpeechTurn && <button disabled={audioBusy} onClick={() => void loadSpeech(lastSpeechTurn)}>Retry OpenAI voice</button>}</div>}<label htmlFor="message">Your message</label><div className="composer"><input id="message" value={input} disabled={turnBusy} onChange={(event) => setInput(event.target.value)} /><button disabled={turnBusy} onClick={() => void submit(input, pendingTurn?.retryable && pendingTurn.text === input.trim() ? pendingTurn.key : undefined)}>{turnBusy ? "Waiting for tutor…" : "Send"}</button></div>{turnError && <div><p role="alert">{turnError}</p>{pendingTurn?.retryable && <button disabled={turnBusy} onClick={() => void submit(pendingTurn.text, pendingTurn.key)}>Retry tutor response</button>}</div>}<fieldset><legend>Voice controls</legend><label><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I consent to voice processing for this turn</label><p aria-live="polite">Microphone: {microphoneState}{microphoneState === "recording" ? ` · ${Math.ceil(mic.elapsed / 1000)} seconds` : ""}</p><p>Browser permission: {mic.permission}</p><button disabled={!consent || !id || turnBusy || transcriptionBusy || mic.state === "recording" || mic.state === "processing"} onClick={() => void startMicrophone()}>{mic.state === "denied" ? "Retry microphone" : "Start microphone"}</button><button disabled={mic.state !== "recording"} onClick={mic.stop}>Stop and transcribe</button><button disabled={mic.state !== "recording"} onClick={cancelMicrophone}>Cancel</button>{lastTranscript && <p aria-live="polite" aria-label="Recognized speech"><strong>We heard:</strong> {lastTranscript}</p>}{microphoneError && <p role="alert">{microphoneError} {mic.state === "denied" && "Enable microphone access in Chrome site settings, then retry."}</p>}{pendingTranscription && <div><button disabled={transcriptionBusy || turnBusy} onClick={() => void retryTranscription()}>Retry transcription</button> <button disabled={transcriptionBusy} onClick={discardTranscription}>Discard recording</button></div>}</fieldset></section><aside className="coach" aria-live="polite"><h2>Live coaching</h2><h3>Grammar correction</h3>{feedback.incorrect && <p><strong>Incorrect:</strong> {feedback.incorrect}</p>}{feedback.corrected && <p><strong>Correct:</strong> {feedback.corrected}</p>}<p>{feedback.grammar}</p><h3>Vocabulary</h3><div className="chips">{feedback.words.length ? feedback.words.map((word) => <span key={word}>{word}</span>) : <span>No suggestions yet.</span>}</div>{selectedLanguageMode !== "ENGLISH" && <><h3>Native Telugu quality review</h3><p>{feedback.telugu}</p><p><strong>Review:</strong> {languageReview.changed ? languageReview.reason : "No wording change needed"}</p>{languageReview.terms.length > 0 && <p><strong>Learning terms kept in English:</strong> {languageReview.terms.join(", ")}</p>}</>}</aside></div>;
}
