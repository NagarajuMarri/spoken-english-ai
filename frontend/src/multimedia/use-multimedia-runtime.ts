import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { initialTutorPresentation, type TutorPresentation } from "../avatar/machine";
import type { TutorPlaybackSignal } from "../avatar/renderer";
import type { AudioLifecycleEvent } from "../voice/TutorAudioPlayer";
import { MultimediaAudioController } from "./audio-controller";
import { multimediaAudioEventFromLifecycle } from "./audio-lifecycle-adapter";
import type {
  LipSyncProvider,
  MultimediaAudioTransport,
  MultimediaRenderer,
  MultimediaRuntimeEvent,
} from "./contracts";
import { EventDrivenAnimationClock } from "./event-driven-animation-clock";
import { AmplitudeLipSyncProvider } from "./lip-sync-providers";
import { SpeakMateMultimediaRuntime } from "./runtime";

function samePresentation(left: TutorPresentation, right: TutorPresentation) {
  return left.state === right.state
    && left.expression === right.expression
    && left.mouth === right.mouth
    && left.activePlaybackId === right.activePlaybackId
    && left.lastCompletedPlaybackId === right.lastCompletedPlaybackId
    && left.errorCode === right.errorCode;
}

export interface SpeakMateMultimediaBridge {
  presentation: TutorPresentation;
  playbackSignal: MutableRefObject<TutorPlaybackSignal>;
  dispatch: (event: MultimediaRuntimeEvent) => void;
  dispatchAudioLifecycle: (event: AudioLifecycleEvent) => void;
  attachAudioTransport: (transport: MultimediaAudioTransport | null) => void;
  playAudio: () => Promise<boolean>;
  replayAudio: () => Promise<boolean>;
  pauseAudio: () => void;
  stopAudio: () => void;
  setAudioMuted: (muted: boolean) => void;
}

export interface SpeakMateMultimediaBridgeOptions {
  createLipSyncProvider?: () => LipSyncProvider;
}

function createDefaultLipSyncProvider() {
  return new AmplitudeLipSyncProvider();
}

/** React adapter used by the learner conversation without coupling the runtime to React or Three.js. */
export function useSpeakMateMultimediaRuntime(
  reducedMotion: boolean,
  options: SpeakMateMultimediaBridgeOptions = {},
): SpeakMateMultimediaBridge {
  const [presentation, setPresentation] = useState<TutorPresentation>(initialTutorPresentation);
  const playbackSignal = useRef<TutorPlaybackSignal>({
    playbackId: "",
    amplitude: 0,
    currentTimeMs: 0,
    durationMs: 0,
  });
  const publishedPresentation = useRef<TutorPresentation>(initialTutorPresentation);
  const runtime = useRef<SpeakMateMultimediaRuntime | null>(null);
  const audioController = useRef(new MultimediaAudioController());
  const createLipSyncProvider = useRef(options.createLipSyncProvider ?? createDefaultLipSyncProvider);

  useEffect(() => {
    const reactRenderer: MultimediaRenderer = {
      id: "react-tutor-presentation",
      profile: "CUSTOM",
      render: (output) => {
        Object.assign(playbackSignal.current, output.playback);
        if (!samePresentation(publishedPresentation.current, output.presentation)) {
          publishedPresentation.current = { ...output.presentation };
          setPresentation(publishedPresentation.current);
        }
      },
    };
    const activeRuntime = new SpeakMateMultimediaRuntime({
      renderers: [reactRenderer],
      lipSyncProvider: createLipSyncProvider.current(),
      animationClock: new EventDrivenAnimationClock(),
      reducedMotion: false,
    });
    runtime.current = activeRuntime;
    activeRuntime.attachAudio(audioController.current);
    activeRuntime.start();
    return () => {
      if (runtime.current === activeRuntime) runtime.current = null;
      activeRuntime.dispose();
    };
  }, []);

  useEffect(() => {
    runtime.current?.handle({ type: "REDUCED_MOTION_CHANGED", reducedMotion });
  }, [reducedMotion]);

  const dispatch = useCallback((event: MultimediaRuntimeEvent) => {
    runtime.current?.handle(event);
  }, []);
  const dispatchAudioLifecycle = useCallback((event: AudioLifecycleEvent) => {
    audioController.current.publish(multimediaAudioEventFromLifecycle(event));
  }, []);
  const attachAudioTransport = useCallback((transport: MultimediaAudioTransport | null) => {
    audioController.current.attachTransport(transport);
  }, []);
  const playAudio = useCallback(
    () => runtime.current?.playAudio() ?? Promise.resolve(false),
    [],
  );
  const replayAudio = useCallback(
    () => runtime.current?.replayAudio() ?? Promise.resolve(false),
    [],
  );
  const pauseAudio = useCallback(() => runtime.current?.pauseAudio(), []);
  const stopAudio = useCallback(() => runtime.current?.stopAudio(), []);
  const setAudioMuted = useCallback((muted: boolean) => runtime.current?.setAudioMuted(muted), []);

  return {
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
  };
}
