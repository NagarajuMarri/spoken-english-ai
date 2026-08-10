import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { TutorSpeech } from "../models";
import type { MultimediaAudioTransport } from "../multimedia/contracts";
import {
  engineeringDiagnosticInfo,
  engineeringDiagnosticWarning,
} from "../telemetry/engineering-diagnostics";

export type AudioLifecycleEvent =
  | { type: "SOURCE_READY"; playbackId: string }
  | { type: "PLAYBACK_STARTED"; playbackId: string }
  | { type: "PLAYBACK_FRAME"; playbackId: string; currentTimeMs: number; durationMs: number; amplitude: number }
  | { type: "PLAYBACK_PAUSED"; playbackId: string }
  | { type: "PLAYBACK_STOPPED"; playbackId: string }
  | { type: "PLAYBACK_ENDED"; playbackId: string }
  | { type: "PLAYBACK_ERROR"; playbackId: string; errorCode: string };

export type TutorAudioPlayerHandle = MultimediaAudioTransport;

interface TutorAudioPlayerProps {
  speech: TutorSpeech | null;
  spokenText: string;
  playbackId: string;
  interruptSequence?: number;
  compact?: boolean;
  showDiagnostics?: boolean;
  autoPlay?: boolean;
  trackAmplitude?: boolean;
  controlsVisible?: boolean;
  commandPort?: MultimediaAudioTransport;
  onAutoplayBlocked?: () => void;
  onLifecycle?: (event: AudioLifecycleEvent) => void;
}

export const TutorAudioPlayer = forwardRef<TutorAudioPlayerHandle, TutorAudioPlayerProps>(function TutorAudioPlayer({
  speech,
  spokenText,
  playbackId,
  interruptSequence = 0,
  compact = false,
  showDiagnostics = false,
  autoPlay = true,
  trackAmplitude = true,
  controlsVisible = true,
  commandPort,
  onAutoplayBlocked,
  onLifecycle,
}: TutorAudioPlayerProps, ref) {
  const audio = useRef<HTMLAudioElement>(null);
  const objectUrl = useRef("");
  const animationFrame = useRef<number | undefined>(undefined);
  const lifecycle = useRef(onLifecycle);
  const autoplayBlocked = useRef(onAutoplayBlocked);
  const sourcePlaybackId = useRef("");
  const ignoreNextPause = useRef(false);
  const audioContext = useRef<AudioContext | null>(null);
  const analyser = useRef<AnalyserNode | null>(null);
  const mediaSource = useRef<MediaElementAudioSourceNode | null>(null);
  const timeDomainData = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const smoothedAmplitude = useRef(0);
  const [status, setStatus] = useState("Tutor voice ready.");
  const [muted, setMuted] = useState(false);
  const playbackRequest = useRef<((kind: "autoplay" | "manual" | "replay") => Promise<boolean>) | undefined>(undefined);

  useEffect(() => {
    lifecycle.current = onLifecycle;
  }, [onLifecycle]);

  useEffect(() => {
    autoplayBlocked.current = onAutoplayBlocked;
  }, [onAutoplayBlocked]);

  const stopFrameLoop = useCallback(() => {
    if (animationFrame.current !== undefined) window.cancelAnimationFrame(animationFrame.current);
    animationFrame.current = undefined;
  }, []);

  const activateAnalyser = useCallback((player: HTMLAudioElement) => {
    if (!trackAmplitude || analyser.current) return;
    const AudioContextConstructor = window.AudioContext
      ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextConstructor) return;
    const context = audioContext.current ?? new AudioContextConstructor();
    audioContext.current = context;
    void context.resume().then(() => {
      if (context.state !== "running" || analyser.current) return;
      const nextAnalyser = context.createAnalyser();
      nextAnalyser.fftSize = 512;
      nextAnalyser.smoothingTimeConstant = 0.45;
      const source = mediaSource.current ?? context.createMediaElementSource(player);
      mediaSource.current = source;
      source.connect(nextAnalyser);
      nextAnalyser.connect(context.destination);
      analyser.current = nextAnalyser;
      timeDomainData.current = new Uint8Array(new ArrayBuffer(nextAnalyser.fftSize));
    }).catch(() => {
      // Audio remains usable without visual analysis on restricted/older devices.
    });
  }, [trackAmplitude]);

  const readAmplitude = useCallback(() => {
    const meter = analyser.current;
    const samples = timeDomainData.current;
    if (!meter || !samples) return 0;
    meter.getByteTimeDomainData(samples);
    let energy = 0;
    for (const sample of samples) {
      const normalized = (sample - 128) / 128;
      energy += normalized * normalized;
    }
    const rms = Math.sqrt(energy / samples.length);
    smoothedAmplitude.current = smoothedAmplitude.current * 0.58 + rms * 0.42;
    return Math.min(1, smoothedAmplitude.current);
  }, []);

  const startFrameLoop = useCallback((player: HTMLAudioElement, id: string) => {
    stopFrameLoop();
    if (!trackAmplitude) return;
    const emitFrame = () => {
      if (player.paused || player.ended || sourcePlaybackId.current !== id) {
        animationFrame.current = undefined;
        return;
      }
      lifecycle.current?.({
        type: "PLAYBACK_FRAME",
        playbackId: id,
        currentTimeMs: Math.max(0, player.currentTime * 1000),
        durationMs: Number.isFinite(player.duration) ? Math.max(0, player.duration * 1000) : 0,
        amplitude: readAmplitude(),
      });
      animationFrame.current = window.requestAnimationFrame(emitFrame);
    };
    emitFrame();
  }, [readAmplitude, stopFrameLoop, trackAmplitude]);

  const requestPlayback = useCallback(async (kind: "autoplay" | "manual" | "replay") => {
    const player = audio.current;
    if (!player || !speech || !sourcePlaybackId.current) return false;
    if (kind !== "autoplay") activateAnalyser(player);
    try {
      await player.play();
      engineeringDiagnosticInfo("speakmate_tts_event", { event: `${kind}_requested`, playback_id: sourcePlaybackId.current });
      return true;
    } catch (error: unknown) {
      const blocked = error instanceof DOMException && error.name === "NotAllowedError";
      setStatus(blocked
        ? controlsVisible
          ? "Audio is ready. Select Play tutor voice to continue."
          : "Audio is ready. Start the conversation to hear your tutor."
        : "Audio is ready. Try again.");
      if (kind === "autoplay") autoplayBlocked.current?.();
      engineeringDiagnosticWarning("speakmate_tts_event", {
        event: blocked ? "browser_playback_blocked" : "browser_playback_failed",
        reason: blocked ? "autoplay_policy" : "media_error",
        playback_id: sourcePlaybackId.current,
      });
      return false;
    }
  }, [activateAnalyser, controlsVisible, speech]);

  useEffect(() => {
    playbackRequest.current = requestPlayback;
  }, [requestPlayback]);

  useEffect(() => {
    const player = audio.current;
    stopFrameLoop();
    if (!speech || !player || !playbackId) return;

    sourcePlaybackId.current = playbackId;
    smoothedAmplitude.current = 0;
    objectUrl.current = URL.createObjectURL(speech.blob);
    player.src = objectUrl.current;
    player.load();
    lifecycle.current?.({ type: "SOURCE_READY", playbackId });
    if (autoPlay) void playbackRequest.current?.("autoplay");

    return () => {
      stopFrameLoop();
      const releasedPlaybackId = sourcePlaybackId.current;
      const wasPlaying = !player.paused;
      if (wasPlaying) {
        ignoreNextPause.current = true;
        if (releasedPlaybackId) lifecycle.current?.({ type: "PLAYBACK_STOPPED", playbackId: releasedPlaybackId });
      }
      player.pause();
      player.removeAttribute("src");
      player.load();
      if (objectUrl.current) {
        URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = "";
      }
      if (sourcePlaybackId.current === releasedPlaybackId) sourcePlaybackId.current = "";
    };
  }, [autoPlay, playbackId, speech, stopFrameLoop]);

  useEffect(() => () => {
    void audioContext.current?.close();
    audioContext.current = null;
    analyser.current = null;
    mediaSource.current = null;
    timeDomainData.current = null;
  }, []);

  useEffect(() => {
    if (interruptSequence === 0) return;
    const interruptedPlaybackId = sourcePlaybackId.current;
    const player = audio.current;
    stopFrameLoop();
    if (player) {
      if (!player.paused) ignoreNextPause.current = true;
      player.pause();
      player.currentTime = 0;
    }
    smoothedAmplitude.current = 0;
    if (interruptedPlaybackId) lifecycle.current?.({ type: "PLAYBACK_STOPPED", playbackId: interruptedPlaybackId });
  }, [interruptSequence, stopFrameLoop]);

  const stop = useCallback(() => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    stopFrameLoop();
    if (!player.paused) ignoreNextPause.current = true;
    player.pause();
    player.currentTime = 0;
    smoothedAmplitude.current = 0;
    setStatus("Tutor voice stopped.");
    if (activeId) lifecycle.current?.({ type: "PLAYBACK_STOPPED", playbackId: activeId });
    engineeringDiagnosticInfo("speakmate_tts_event", { event: "playback_stopped", playback_id: activeId });
  }, [stopFrameLoop]);

  const pause = useCallback(() => {
    const player = audio.current;
    if (!player) return;
    stopFrameLoop();
    player.pause();
  }, [stopFrameLoop]);

  const replay = useCallback(() => {
    const player = audio.current;
    if (!player) return Promise.resolve(false);
    player.currentTime = 0;
    smoothedAmplitude.current = 0;
    return requestPlayback("replay");
  }, [requestPlayback]);

  const setMutedValue = useCallback((nextMuted: boolean) => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    player.muted = nextMuted;
    setMuted(nextMuted);
    setStatus(nextMuted ? "Tutor voice muted." : "Tutor voice unmuted.");
    engineeringDiagnosticInfo("speakmate_tts_event", { event: nextMuted ? "playback_muted" : "playback_unmuted", playback_id: activeId });
  }, []);

  const toggleMute = useCallback(() => setMutedValue(!muted), [muted, setMutedValue]);

  const requestManualPlay = useCallback(() => {
    void (commandPort?.play() ?? requestPlayback("manual"));
  }, [commandPort, requestPlayback]);
  const requestReplay = useCallback(() => {
    void (commandPort?.replay() ?? replay());
  }, [commandPort, replay]);
  const requestStop = useCallback(() => {
    if (commandPort) commandPort.stop();
    else stop();
  }, [commandPort, stop]);
  const requestMuteToggle = useCallback(() => {
    if (commandPort) commandPort.setMuted(!muted);
    else toggleMute();
  }, [commandPort, muted, toggleMute]);

  useImperativeHandle(ref, () => ({
    play: () => requestPlayback("manual"),
    replay,
    pause,
    stop,
    setMuted: setMutedValue,
  }), [pause, replay, requestPlayback, setMutedValue, stop]);

  return (
    <section className={`tutor-audio ${compact ? "compact" : ""}`} aria-label="Tutor voice controls">
      <h3 className={compact ? "sr-only" : ""}>Tutor voice</h3>
      {showDiagnostics && <p className="ai-disclosure">AI-generated voice diagnostics</p>}
      <audio
        ref={audio}
        controls={showDiagnostics}
        className={showDiagnostics ? "" : "sr-only"}
        preload="auto"
        muted={muted}
        onPlay={() => {
          engineeringDiagnosticInfo("speakmate_tts_event", { event: "media_play", playback_id: sourcePlaybackId.current });
        }}
        onPlaying={(event) => {
          const activeId = sourcePlaybackId.current;
          if (!activeId) return;
          activateAnalyser(event.currentTarget);
          setStatus("Tutor voice is playing.");
          lifecycle.current?.({ type: "PLAYBACK_STARTED", playbackId: activeId });
          startFrameLoop(event.currentTarget, activeId);
          engineeringDiagnosticInfo("speakmate_tts_event", { event: "playback_started", playback_id: activeId, current_time_ms: event.currentTarget.currentTime * 1000 });
        }}
        onPause={() => {
          stopFrameLoop();
          if (ignoreNextPause.current) {
            ignoreNextPause.current = false;
            return;
          }
          const activeId = sourcePlaybackId.current;
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_PAUSED", playbackId: activeId });
          engineeringDiagnosticInfo("speakmate_tts_event", { event: "playback_paused", playback_id: activeId });
        }}
        onEnded={() => {
          stopFrameLoop();
          smoothedAmplitude.current = 0;
          const activeId = sourcePlaybackId.current;
          setStatus("Tutor voice finished.");
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_ENDED", playbackId: activeId });
          engineeringDiagnosticInfo("speakmate_tts_event", { event: "playback_ended", playback_id: activeId });
        }}
        onError={() => {
          stopFrameLoop();
          smoothedAmplitude.current = 0;
          const activeId = sourcePlaybackId.current;
          setStatus("Tutor audio could not be played.");
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_ERROR", playbackId: activeId, errorCode: "browser_audio_error" });
          engineeringDiagnosticWarning("speakmate_tts_event", { event: "browser_audio_error", playback_id: activeId });
        }}
        aria-label={showDiagnostics && spokenText ? `Tutor voice audio: ${spokenText}` : "Tutor voice audio"}
      />
      {controlsVisible && <div className="audio-actions">
        <button disabled={!speech} onClick={requestManualPlay}>Play tutor voice</button>
        <button aria-label="Stop tutor voice" disabled={!speech} onClick={requestStop}>Stop</button>
        <button aria-label="Replay tutor voice" disabled={!speech} onClick={requestReplay}>Replay</button>
        <button aria-label={muted ? "Unmute tutor voice" : "Mute tutor voice"} disabled={!speech} aria-pressed={muted} onClick={requestMuteToggle}>{muted ? "Unmute" : "Mute"}</button>
      </div>}
      <p className={compact ? "sr-only" : undefined} role="status" aria-live="polite">{speech ? status : "No tutor audio yet."}</p>
      {showDiagnostics && speech && <p className="audio-evidence">Provider: {speech.provider} · Model: {speech.model} · Voice: {speech.voice}</p>}
    </section>
  );
});
