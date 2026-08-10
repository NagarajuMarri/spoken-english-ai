import { useCallback, useEffect, useRef, useState } from "react";
import type { TutorSpeech } from "../models";

export type AudioLifecycleEvent =
  | { type: "SOURCE_READY"; playbackId: string }
  | { type: "PLAYBACK_STARTED"; playbackId: string }
  | { type: "PLAYBACK_FRAME"; playbackId: string; currentTimeMs: number; durationMs: number }
  | { type: "PLAYBACK_PAUSED"; playbackId: string }
  | { type: "PLAYBACK_STOPPED"; playbackId: string }
  | { type: "PLAYBACK_ENDED"; playbackId: string }
  | { type: "PLAYBACK_ERROR"; playbackId: string; errorCode: string };

export function TutorAudioPlayer({
  speech,
  spokenText,
  playbackId,
  interruptSequence = 0,
  compact = false,
  showDiagnostics = false,
  onLifecycle,
}: {
  speech: TutorSpeech | null;
  spokenText: string;
  playbackId: string;
  interruptSequence?: number;
  compact?: boolean;
  showDiagnostics?: boolean;
  onLifecycle?: (event: AudioLifecycleEvent) => void;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const objectUrl = useRef("");
  const animationFrame = useRef<number | undefined>(undefined);
  const lifecycle = useRef(onLifecycle);
  const sourcePlaybackId = useRef("");
  const ignoreNextPause = useRef(false);
  const [status, setStatus] = useState("Tutor voice ready.");
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    lifecycle.current = onLifecycle;
  }, [onLifecycle]);

  const stopFrameLoop = useCallback(() => {
    if (animationFrame.current !== undefined) window.cancelAnimationFrame(animationFrame.current);
    animationFrame.current = undefined;
  }, []);

  const startFrameLoop = useCallback((player: HTMLAudioElement, id: string) => {
    stopFrameLoop();
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
      });
      animationFrame.current = window.requestAnimationFrame(emitFrame);
    };
    emitFrame();
  }, [stopFrameLoop]);

  useEffect(() => {
    const player = audio.current;
    stopFrameLoop();
    if (!speech || !player || !playbackId) return;

    sourcePlaybackId.current = playbackId;
    objectUrl.current = URL.createObjectURL(speech.blob);
    player.src = objectUrl.current;
    player.load();
    lifecycle.current?.({ type: "SOURCE_READY", playbackId });
    void player.play().then(() => {
      console.info("speakmate_tts_event", { event: "autoplay_requested", playback_id: playbackId });
    }).catch((error: unknown) => {
      const blocked = error instanceof DOMException && error.name === "NotAllowedError";
      setStatus(blocked ? "Chrome blocked autoplay. Click Play tutor voice." : "Audio is ready. Click Play tutor voice.");
      console.warn("speakmate_tts_event", {
        event: blocked ? "browser_playback_blocked" : "browser_playback_failed",
        reason: blocked ? "autoplay_policy" : "media_error",
        playback_id: playbackId,
      });
    });

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
  }, [playbackId, speech, stopFrameLoop]);

  useEffect(() => {
    if (interruptSequence === 0) return;
    const interruptedPlaybackId = sourcePlaybackId.current;
    const player = audio.current;
    stopFrameLoop();
    if (player) {
      player.pause();
      player.currentTime = 0;
    }
    if (interruptedPlaybackId) lifecycle.current?.({ type: "PLAYBACK_STOPPED", playbackId: interruptedPlaybackId });
  }, [interruptSequence, stopFrameLoop]);

  const play = () => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    console.info("speakmate_tts_event", { event: "manual_play_requested", playback_id: activeId });
    void player.play().catch(() => {
      setStatus("Chrome blocked playback. Click the player control to begin.");
      console.warn("speakmate_tts_event", { event: "browser_playback_blocked", reason: "manual_play_rejected", playback_id: activeId });
    });
  };

  const stop = () => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    stopFrameLoop();
    player.pause();
    player.currentTime = 0;
    setStatus("Tutor voice stopped.");
    if (activeId) lifecycle.current?.({ type: "PLAYBACK_STOPPED", playbackId: activeId });
    console.info("speakmate_tts_event", { event: "playback_stopped", playback_id: activeId });
  };

  const replay = () => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    player.currentTime = 0;
    console.info("speakmate_tts_event", { event: "replay_requested", playback_id: activeId });
    void player.play().catch(() => {
      setStatus("Click the player control to replay.");
      console.warn("speakmate_tts_event", { event: "browser_playback_blocked", reason: "replay_rejected", playback_id: activeId });
    });
  };

  const toggleMute = () => {
    const player = audio.current;
    if (!player) return;
    const activeId = sourcePlaybackId.current;
    player.muted = !muted;
    setMuted(!muted);
    setStatus(!muted ? "Tutor voice muted." : "Tutor voice unmuted.");
    console.info("speakmate_tts_event", { event: !muted ? "playback_muted" : "playback_unmuted", playback_id: activeId });
  };

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
        onPlay={(event) => {
          const activeId = sourcePlaybackId.current;
          if (!activeId) return;
          setStatus("Tutor voice is playing.");
          lifecycle.current?.({ type: "PLAYBACK_STARTED", playbackId: activeId });
          startFrameLoop(event.currentTarget, activeId);
          console.info("speakmate_tts_event", { event: "playback_started", playback_id: activeId, current_time_ms: event.currentTarget.currentTime * 1000 });
        }}
        onPause={() => {
          stopFrameLoop();
          if (ignoreNextPause.current) {
            ignoreNextPause.current = false;
            return;
          }
          const activeId = sourcePlaybackId.current;
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_PAUSED", playbackId: activeId });
          console.info("speakmate_tts_event", { event: "playback_paused", playback_id: activeId });
        }}
        onEnded={() => {
          stopFrameLoop();
          const activeId = sourcePlaybackId.current;
          setStatus("Tutor voice finished.");
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_ENDED", playbackId: activeId });
          console.info("speakmate_tts_event", { event: "playback_ended", playback_id: activeId });
        }}
        onError={() => {
          stopFrameLoop();
          const activeId = sourcePlaybackId.current;
          setStatus("Tutor audio could not be played.");
          if (activeId) lifecycle.current?.({ type: "PLAYBACK_ERROR", playbackId: activeId, errorCode: "browser_audio_error" });
          console.warn("speakmate_tts_event", { event: "browser_audio_error", playback_id: activeId });
        }}
        aria-label={showDiagnostics && spokenText ? `Tutor voice audio: ${spokenText}` : "Tutor voice audio"}
      />
      <div className="audio-actions">
        <button disabled={!speech} onClick={play}>Play tutor voice</button>
        <button aria-label="Stop tutor voice" disabled={!speech} onClick={stop}>Stop</button>
        <button aria-label="Replay tutor voice" disabled={!speech} onClick={replay}>Replay</button>
        <button aria-label={muted ? "Unmute tutor voice" : "Mute tutor voice"} disabled={!speech} aria-pressed={muted} onClick={toggleMute}>{muted ? "Unmute" : "Mute"}</button>
      </div>
      <p className={compact ? "sr-only" : undefined} role="status" aria-live="polite">{speech ? status : "No tutor audio yet."}</p>
      {showDiagnostics && speech && <p className="audio-evidence">Provider: {speech.provider} · Model: {speech.model} · Voice: {speech.voice}</p>}
    </section>
  );
}
