import { useEffect, useRef, type MutableRefObject } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import type { TutorPlaybackSignal, TutorRendererFrame } from "../avatar/renderer";
import {
  createModelTutorRig,
  disposeModelTutorRig,
  updateModelTutorRig,
  type ModelTutorRig,
} from "../avatar/model-tutor";
import { createThreeTutorRig, disposeThreeTutorRig, updateThreeTutorRig, type ThreeTutorRig } from "../avatar/three-tutor";
import {
  engineeringDiagnosticInfo,
  engineeringDiagnosticWarning,
} from "../telemetry/engineering-diagnostics";
import { selectTutorRenderTier } from "../multimedia/device-fallback";

interface ThreeAvatarProps {
  frame: TutorRendererFrame;
  playbackSignal: MutableRefObject<TutorPlaybackSignal>;
  reducedMotion: boolean;
  onReady: (initializationMs: number, profile: "model" | "lite") => void;
  onUnavailable: () => void;
}

function configureLiteCamera(camera: THREE.PerspectiveCamera) {
  camera.near = 0.1;
  camera.far = 30;
  camera.position.set(0, 0.12, 6.4);
  camera.lookAt(0, -0.05, 0);
  camera.updateProjectionMatrix();
}

function configureModelCamera(camera: THREE.PerspectiveCamera, rig: ModelTutorRig) {
  const lessonCenter = rig.height * 0.82;
  camera.near = Math.max(0.01, rig.height * 0.01);
  camera.far = rig.height * 12;
  camera.position.set(0, lessonCenter, rig.height * 0.98);
  camera.lookAt(0, lessonCenter, 0);
  camera.updateProjectionMatrix();
}

export default function ThreeAvatar({
  frame,
  playbackSignal,
  reducedMotion,
  onReady,
  onUnavailable,
}: ThreeAvatarProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(frame);
  const reducedMotionRef = useRef(reducedMotion);
  const readyCallback = useRef(onReady);
  const unavailableCallback = useRef(onUnavailable);
  const renderOnce = useRef<(() => void) | undefined>(undefined);
  const controlContinuousMotion = useRef<((enabled: boolean) => void) | undefined>(undefined);

  useEffect(() => {
    frameRef.current = frame;
    reducedMotionRef.current = reducedMotion;
    controlContinuousMotion.current?.(!reducedMotion);
    if (reducedMotion && !controlContinuousMotion.current) renderOnce.current?.();
  }, [frame, reducedMotion]);

  useEffect(() => {
    readyCallback.current = onReady;
    unavailableCallback.current = onUnavailable;
  }, [onReady, onUnavailable]);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const started = performance.now();
    engineeringDiagnosticInfo("speakmate_3d_metric", { event: "renderer_initializing" });
    const lowPower = selectTutorRenderTier("ananya") === "LIGHTWEIGHT_3D";
    if (typeof WebGLRenderingContext === "undefined" && typeof WebGL2RenderingContext === "undefined") {
      unavailableCallback.current();
      return;
    }

    const contextAttributes: WebGLContextAttributes = {
      alpha: true,
      antialias: !lowPower,
      powerPreference: lowPower ? "low-power" : "high-performance",
      preserveDrawingBuffer: false,
    };
    let context: WebGLRenderingContext | WebGL2RenderingContext | null = null;
    let renderer: THREE.WebGLRenderer;
    try {
      context = element.getContext("webgl2", contextAttributes)
        ?? element.getContext("webgl", contextAttributes);
      if (!context) {
        unavailableCallback.current();
        return;
      }
      renderer = new THREE.WebGLRenderer({
        canvas: element,
        context,
        alpha: true,
        antialias: !lowPower,
        powerPreference: lowPower ? "low-power" : "high-performance",
      });
    } catch {
      unavailableCallback.current();
      return;
    }

    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    renderer.shadowMap.enabled = !lowPower;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, lowPower ? 1 : 1.5));
    const debugInfo = context.getExtension("WEBGL_debug_renderer_info") as {
      UNMASKED_RENDERER_WEBGL: number;
    } | null;
    const rendererName = debugInfo
      ? String(context.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) ?? "unknown")
      : "unavailable";
    engineeringDiagnosticInfo("speakmate_3d_metric", {
      event: "renderer_capability",
      renderer: rendererName.slice(0, 160),
      software_rendering: /swiftshader|llvmpipe|software/i.test(rendererName),
      webgl_version: context instanceof WebGL2RenderingContext ? 2 : 1,
      device_pixel_ratio: window.devicePixelRatio || 1,
      effective_pixel_ratio: renderer.getPixelRatio(),
      profile: lowPower ? "lite" : "model-capable",
    });

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(27, 1, 0.1, 30);
    configureLiteCamera(camera);

    const hemisphere = new THREE.HemisphereLight(0xfff4e8, 0x274558, 2.4);
    scene.add(hemisphere);
    const key = new THREE.DirectionalLight(0xffe5d1, 4.2);
    key.position.set(3.4, 4.5, 5.2);
    key.castShadow = !lowPower;
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x9ed5e8, 2.1);
    fill.position.set(-4, 2.2, 3.4);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xffd2b4, 1.6);
    rim.position.set(0, 3, -4);
    scene.add(rim);

    let liteRig: ThreeTutorRig | null = null;
    try {
      liteRig = createThreeTutorRig();
      scene.add(liteRig.root);
    } catch {
      renderer.dispose();
      unavailableCallback.current();
      return;
    }
    let modelRig: ModelTutorRig | null = null;
    const animationStartedAt = performance.now();
    let animationFrame = 0;
    let loopRunning = false;
    let disposed = false;
    let fatal = false;
    let readyReported = false;
    let lastRenderedAt = -Infinity;
    let modelDeadline = 0;
    let firstRenderedAt = 0;
    let renderedFrames = 0;
    let frameRateReported = false;
    const frameTimes: number[] = [];
    let previousRenderedAt = 0;

    const reportReady = (profile: "model" | "lite") => {
      if (disposed || fatal) return;
      const initializationMs = performance.now() - started;
      if (readyReported) {
        if (profile === "model") {
          engineeringDiagnosticInfo("speakmate_3d_metric", {
            event: "renderer_upgraded",
            initialization_ms: Math.round(initializationMs * 10) / 10,
            profile,
          });
          readyCallback.current(initializationMs, profile);
        }
        return;
      }
      readyReported = true;
      engineeringDiagnosticInfo("speakmate_3d_metric", {
        event: "renderer_ready",
        initialization_ms: Math.round(initializationMs * 10) / 10,
        profile,
        low_power: lowPower,
        pixel_ratio: renderer.getPixelRatio(),
      });
      readyCallback.current(initializationMs, profile);
    };

    const failSafely = () => {
      if (fatal || disposed) return;
      fatal = true;
      window.cancelAnimationFrame(animationFrame);
      unavailableCallback.current();
    };

    const resize = () => {
      if (disposed) return;
      const width = Math.max(1, element.clientWidth);
      const height = Math.max(1, element.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (reducedMotionRef.current) renderOnce.current?.();
    };
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver === "function") {
      observer = new ResizeObserver(resize);
      observer.observe(element);
    } else {
      window.addEventListener("resize", resize);
    }
    resize();

    const draw = () => {
      if (disposed || fatal) return;
      try {
        const elapsed = Math.max(0, (performance.now() - animationStartedAt) / 1_000);
        if (modelRig) {
          updateModelTutorRig(modelRig, frameRef.current, playbackSignal.current, elapsed, reducedMotionRef.current);
        } else if (liteRig) {
          updateThreeTutorRig(liteRig, frameRef.current, playbackSignal.current, elapsed, reducedMotionRef.current);
        }
        renderer.render(scene, camera);
        const renderedAt = performance.now();
        if (previousRenderedAt > 0) frameTimes.push(renderedAt - previousRenderedAt);
        previousRenderedAt = renderedAt;
        if (firstRenderedAt === 0) firstRenderedAt = renderedAt;
        renderedFrames += 1;
        const measurementWindowMs = renderedAt - firstRenderedAt;
        if (!frameRateReported && measurementWindowMs >= 5_000) {
          frameRateReported = true;
          const memory = (performance as Performance & {
            memory?: { usedJSHeapSize?: number };
          }).memory;
          const orderedFrameTimes = [...frameTimes].sort((left, right) => left - right);
          const p90FrameTime = orderedFrameTimes[Math.floor(orderedFrameTimes.length * 0.9)] ?? 0;
          engineeringDiagnosticInfo("speakmate_3d_metric", {
            event: "renderer_performance",
            average_fps: Math.round((renderedFrames / (measurementWindowMs / 1_000)) * 10) / 10,
            profile: modelRig ? "model" : "lite",
            p10_fps: p90FrameTime > 0 ? Math.round((1000 / p90FrameTime) * 10) / 10 : null,
            p90_frame_time_ms: Math.round(p90FrameTime * 10) / 10,
            memory_usage_mb: memory?.usedJSHeapSize === undefined
              ? null
              : Math.round((memory.usedJSHeapSize / (1024 * 1024)) * 10) / 10,
          });
        }
      } catch {
        failSafely();
      }
    };
    renderOnce.current = draw;

    const stopRenderLoop = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      loopRunning = false;
    };
    const renderLoop = (timestamp: number) => {
      if (disposed || fatal || reducedMotionRef.current) {
        loopRunning = false;
        return;
      }
      if (timestamp - lastRenderedAt >= 1000 / 30) {
        lastRenderedAt = timestamp;
        draw();
      }
      animationFrame = window.requestAnimationFrame(renderLoop);
    };
    const startRenderLoop = () => {
      if (loopRunning || disposed || fatal || reducedMotionRef.current) return;
      loopRunning = true;
      animationFrame = window.requestAnimationFrame(renderLoop);
    };
    controlContinuousMotion.current = (enabled) => {
      if (enabled) startRenderLoop();
      else {
        stopRenderLoop();
        draw();
      }
    };
    draw();
    if (!fatal) reportReady("lite");
    startRenderLoop();

    if (!lowPower && !fatal) {
      const loader = new GLTFLoader();
      loader.setMeshoptDecoder(MeshoptDecoder);
      const modelLoadStartedAt = performance.now();
      modelDeadline = window.setTimeout(() => {
        engineeringDiagnosticWarning("speakmate_3d_metric", { event: "model_load_slow", fallback: "volumetric_lite" });
        reportReady("lite");
      }, 8_000);
      loader.load(
        `${import.meta.env.BASE_URL}models/ananya-mpfb-cc0.glb`,
        (gltf) => {
          if (disposed || fatal) {
            try {
              disposeModelTutorRig(createModelTutorRig(gltf.scene));
            } catch {
              // A discarded late model must not revive or destabilize the fallback.
            }
            return;
          }
          let candidate: ModelTutorRig | null = null;
          try {
            window.clearTimeout(modelDeadline);
            engineeringDiagnosticInfo("speakmate_3d_metric", {
              event: "model_loaded",
              load_ms: Math.round((performance.now() - modelLoadStartedAt) * 10) / 10,
            });
            candidate = createModelTutorRig(gltf.scene);
            scene.add(candidate.root);
            if (liteRig) liteRig.root.visible = false;
            configureModelCamera(camera, candidate);
            updateModelTutorRig(
              candidate,
              frameRef.current,
              playbackSignal.current,
              Math.max(0, (performance.now() - animationStartedAt) / 1_000),
              reducedMotionRef.current,
            );
            renderer.render(scene, camera);
            modelRig = candidate;
            candidate = null;
            if (liteRig) {
              const replacedLiteRig = liteRig;
              liteRig = null;
              scene.remove(replacedLiteRig.root);
              try {
                disposeThreeTutorRig(replacedLiteRig);
              } catch {
                // The model is already rendered; stale lite cleanup cannot undo the upgrade.
              }
            }
            reportReady("model");
          } catch {
            if (candidate) {
              scene.remove(candidate.root);
              try {
                disposeModelTutorRig(candidate);
              } catch {
                // Restore the retained lite rig even if candidate cleanup is incomplete.
              }
              candidate = null;
            }
            modelRig = null;
            configureLiteCamera(camera);
            if (liteRig) liteRig.root.visible = true;
            engineeringDiagnosticWarning("speakmate_3d_metric", { event: "model_initialization_failed", fallback: "volumetric_lite" });
            draw();
            reportReady("lite");
          }
        },
        undefined,
        () => {
          if (disposed) return;
          window.clearTimeout(modelDeadline);
          engineeringDiagnosticWarning("speakmate_3d_metric", { event: "model_load_failed", fallback: "volumetric_lite" });
          reportReady("lite");
        },
      );
    }

    const handleContextLost = (event: Event) => {
      event.preventDefault();
      failSafely();
    };
    element.addEventListener("webglcontextlost", handleContextLost);

    return () => {
      disposed = true;
      renderOnce.current = undefined;
      controlContinuousMotion.current = undefined;
      stopRenderLoop();
      window.clearTimeout(modelDeadline);
      element.removeEventListener("webglcontextlost", handleContextLost);
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      if (modelRig) disposeModelTutorRig(modelRig);
      if (liteRig) disposeThreeTutorRig(liteRig);
      renderer.dispose();
    };
  }, [playbackSignal]);

  return (
    <canvas
      ref={canvas}
      className="three-avatar-canvas"
      aria-hidden="true"
      data-testid="ananya-3d-canvas"
    />
  );
}
