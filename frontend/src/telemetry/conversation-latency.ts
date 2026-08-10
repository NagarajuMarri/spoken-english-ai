import { engineeringDiagnosticInfo } from "./engineering-diagnostics";

export type LatencySource = "VOICE" | "TEXT";

export interface ConversationLatencyTrace {
  source: LatencySource;
  t0: number;
  uiFeedbackAt?: number;
  t1?: number;
  t2?: number;
  t3?: number;
  t4?: number;
  t5?: number;
  t6?: number;
  t7?: number;
  t8?: number;
  reported: boolean;
}

type TimedStage = "uiFeedbackAt" | "t1" | "t2" | "t3" | "t4" | "t5" | "t6" | "t7" | "t8";
type ConversationLatencyMetric = ReturnType<typeof conversationLatencyMetric>;
const metricListeners = new Set<(metric: ConversationLatencyMetric) => void>();

function monotonicNow() {
  return performance.now();
}

function elapsed(start?: number, end?: number) {
  if (start === undefined || end === undefined || end < start) return null;
  return Math.round((end - start) * 10) / 10;
}

export function createConversationLatencyTrace(source: LatencySource, t0 = monotonicNow()): ConversationLatencyTrace {
  return { source, t0, reported: false };
}

export function markConversationLatency(
  trace: ConversationLatencyTrace,
  stage: TimedStage,
  timestamp = monotonicNow(),
) {
  if (trace[stage] === undefined) trace[stage] = timestamp;
}

export function conversationLatencyMetric(trace: ConversationLatencyTrace) {
  const transcriptReady = trace.t2 ?? trace.t0;
  return {
    event: "conversation_playback_started",
    source: trace.source,
    ui_state_transition_ms: elapsed(trace.t0, trace.uiFeedbackAt),
    stt_latency_ms: elapsed(trace.t1, trace.t2),
    time_to_first_tutor_output_ms: elapsed(transcriptReady, trace.t4),
    full_tutor_generation_latency_ms: elapsed(trace.t3, trace.t5),
    tts_audio_ready_latency_ms: elapsed(trace.t6, trace.t7),
    audio_ready_after_input_ms: elapsed(transcriptReady, trace.t7),
    time_to_first_audio_ms: elapsed(transcriptReady, trace.t8),
    total_conversational_latency_ms: elapsed(trace.t0, trace.t8),
    first_output_delivery: "complete_response",
    stage_coverage: {
      t0: true,
      t1: trace.t1 !== undefined,
      t2: trace.t2 !== undefined,
      t3: trace.t3 !== undefined,
      t4: trace.t4 !== undefined,
      t5: trace.t5 !== undefined,
      t6: trace.t6 !== undefined,
      t7: trace.t7 !== undefined,
      t8: trace.t8 !== undefined,
    },
  };
}

export function emitConversationLatency(trace: ConversationLatencyTrace) {
  if (trace.reported || trace.t8 === undefined) return;
  trace.reported = true;
  const metric = conversationLatencyMetric(trace);
  for (const listener of metricListeners) listener(metric);
  engineeringDiagnosticInfo("speakmate_conversation_latency", metric);
}

/** Explicit privacy-safe sink boundary for product telemetry or engineering diagnostics. */
export function subscribeConversationLatency(
  listener: (metric: ConversationLatencyMetric) => void,
) {
  metricListeners.add(listener);
  return () => metricListeners.delete(listener);
}
