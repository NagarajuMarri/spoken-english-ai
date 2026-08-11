import { useCallback, useEffect, useRef, useState } from "react";

export type MicrophoneState =
  | "permission_required"
  | "requesting_permission"
  | "ready"
  | "recording"
  | "processing"
  | "denied"
  | "unavailable"
  | "cancelled"
  | "no_speech"
  | "too_large"
  | "error";
export type MicrophonePermission = "prompt" | "granted" | "denied" | "unsupported";
export interface CapturedAudio {
  blob: Blob;
  mimeType: string;
  sizeBytes: number;
  durationMs: number;
  finishedAtMonotonicMs?: number;
}

const ACCEPTED = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
];
const MAX_MS = 60_000;
const MAX_BYTES = 5 * 1024 * 1024;
const SILENCE_MS = 1_250;
const MIN_SPEECH_MS = 220;
const SPEECH_RMS = 0.025;

function captureAvailable() {
  return navigator.mediaDevices !== undefined && typeof MediaRecorder !== "undefined" && window.isSecureContext !== false;
}

export function useMicrophone(consent: boolean, onCaptured?: (capture: CapturedAudio) => Promise<void> | void) {
  const [state, setState] = useState<MicrophoneState>(captureAvailable() ? "permission_required" : "unavailable");
  const [permission, setPermission] = useState<MicrophonePermission>("unsupported");
  const [elapsed, setElapsed] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const stream = useRef<MediaStream | undefined>(undefined);
  const recorder = useRef<MediaRecorder | undefined>(undefined);
  const timer = useRef<number | undefined>(undefined);
  const voiceFrame = useRef<number | undefined>(undefined);
  const audioContext = useRef<AudioContext | undefined>(undefined);
  const chunks = useRef<Blob[]>([]);
  const bytes = useRef(0);
  const startedAt = useRef(0);
  const finishedAt = useRef(0);
  const cancelled = useRef(false);
  const abortReason = useRef<"too_large" | "error" | undefined>(undefined);
  const callback = useRef(onCaptured);
  const mounted = useRef(true);

  useEffect(() => {
    callback.current = onCaptured;
  }, [onCaptured]);

  const cleanup = useCallback(() => {
    if (timer.current !== undefined) window.clearInterval(timer.current);
    if (voiceFrame.current !== undefined) window.cancelAnimationFrame(voiceFrame.current);
    timer.current = undefined;
    voiceFrame.current = undefined;
    void audioContext.current?.close();
    audioContext.current = undefined;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = undefined;
    recorder.current = undefined;
  }, []);

  useEffect(() => {
    mounted.current = true;
    let permissionStatus: PermissionStatus | undefined;
    const updatePermission = () => setPermission((permissionStatus?.state as MicrophonePermission) ?? "unsupported");
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: "microphone" } as PermissionDescriptor).then((status) => {
        permissionStatus = status;
        updatePermission();
        status.addEventListener("change", updatePermission);
      }).catch(() => setPermission("unsupported"));
    }
    return () => {
      mounted.current = false;
      permissionStatus?.removeEventListener("change", updatePermission);
      cleanup();
    };
  }, [cleanup]);

  const cancel = useCallback(() => {
    cancelled.current = true;
    setErrorMessage("");
    if (recorder.current?.state === "recording") recorder.current.stop();
    else cleanup();
    if (mounted.current) setState("cancelled");
  }, [cleanup]);

  const stop = useCallback(() => {
    if (recorder.current?.state !== "recording") return;
    if (timer.current !== undefined) window.clearInterval(timer.current);
    timer.current = undefined;
    finishedAt.current = performance.now();
    setState("processing");
    recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (!consent) {
      setErrorMessage("Voice-processing consent is required before recording.");
      setState("error");
      return;
    }
    if (!captureAvailable()) {
      setErrorMessage("Microphone recording requires Chrome on localhost or another secure HTTPS page.");
      setState("unavailable");
      return;
    }
    setErrorMessage("");
    setState("requesting_permission");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      setPermission("granted");
      const mimeType = ACCEPTED.find((type) => MediaRecorder.isTypeSupported(type));
      if (!mimeType) {
        cleanup();
        setErrorMessage("This browser does not provide a supported recording format.");
        setState("unavailable");
        return;
      }
      const next = new MediaRecorder(stream.current, { mimeType });
      recorder.current = next;
      chunks.current = [];
      bytes.current = 0;
      cancelled.current = false;
      abortReason.current = undefined;
      finishedAt.current = 0;
      next.ondataavailable = (event) => {
        if (!event.data.size || cancelled.current) return;
        chunks.current.push(event.data);
        bytes.current += event.data.size;
        if (bytes.current > MAX_BYTES && next.state === "recording") {
          abortReason.current = "too_large";
          next.stop();
        }
      };
      next.onerror = () => {
        abortReason.current = "error";
        if (next.state === "recording") next.stop();
      };
      next.onstop = async () => {
        const durationMs = Math.max(100, Math.min(MAX_MS, Date.now() - startedAt.current));
        const capturedChunks = chunks.current;
        const reason = abortReason.current;
        cleanup();
        chunks.current = [];
        if (!mounted.current || cancelled.current) return;
        if (reason) {
          setErrorMessage(reason === "too_large" ? "Recording exceeded the 5 MB limit." : "Recording failed.");
          setState(reason);
          return;
        }
        const blob = new Blob(capturedChunks, { type: next.mimeType || mimeType });
        if (!blob.size) {
          setErrorMessage("No audio was captured. Please speak clearly and try again.");
          setState("no_speech");
          return;
        }
        setState("processing");
        try {
          await callback.current?.({
            blob,
            mimeType: blob.type,
            sizeBytes: blob.size,
            durationMs,
            finishedAtMonotonicMs: finishedAt.current || performance.now(),
          });
          if (mounted.current) setState("ready");
        } catch (error) {
          if (mounted.current) {
            setErrorMessage(error instanceof Error ? error.message : "Speech recognition failed.");
            setState("error");
          }
        }
      };
      startedAt.current = Date.now();
      next.start(250);
      setElapsed(0);
      setState("recording");

      const AudioContextConstructor = window.AudioContext;
      if (AudioContextConstructor) {
        const context = new AudioContextConstructor();
        audioContext.current = context;
        const analyser = context.createAnalyser();
        analyser.fftSize = 512;
        context.createMediaStreamSource(stream.current).connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        let heardSpeech = false;
        let speechStartedAt = 0;
        let lastVoiceAt = performance.now();
        const listenForSilence = () => {
          if (next.state !== "recording") return;
          analyser.getByteTimeDomainData(samples);
          let energy = 0;
          for (const sample of samples) {
            const normalized = (sample - 128) / 128;
            energy += normalized * normalized;
          }
          const now = performance.now();
          const rms = Math.sqrt(energy / samples.length);
          if (rms >= SPEECH_RMS) {
            if (!heardSpeech) speechStartedAt = now;
            heardSpeech = true;
            lastVoiceAt = now;
          }
          if (heardSpeech && now - speechStartedAt >= MIN_SPEECH_MS && now - lastVoiceAt >= SILENCE_MS) {
            stop();
            return;
          }
          voiceFrame.current = window.requestAnimationFrame(listenForSilence);
        };
        voiceFrame.current = window.requestAnimationFrame(listenForSilence);
      }
      timer.current = window.setInterval(() => {
        const duration = Date.now() - startedAt.current;
        setElapsed(Math.min(MAX_MS, duration));
        if (duration >= MAX_MS && next.state === "recording") stop();
      }, 250);
    } catch (error) {
      cleanup();
      const denied = error instanceof DOMException && ["NotAllowedError", "SecurityError"].includes(error.name);
      if (denied) setPermission("denied");
      setErrorMessage(denied ? "Microphone permission was denied." : "The microphone could not be started.");
      setState(denied ? "denied" : "error");
    }
  }, [cleanup, consent, stop]);

  return {
    state,
    permission,
    errorMessage,
    elapsed,
    maxDuration: MAX_MS,
    start,
    stop,
    cancel,
    retry: () => {
      setErrorMessage("");
      setState("permission_required");
    },
  };
}
