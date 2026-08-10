import { describe, expect, it, vi } from "vitest";
import {
  conversationLatencyMetric,
  createConversationLatencyTrace,
  emitConversationLatency,
  markConversationLatency,
  subscribeConversationLatency,
} from "../telemetry/conversation-latency";

describe("privacy-safe conversational latency telemetry", () => {
  it("reports T0-T8 stage durations without text, audio, or identifiers", () => {
    const trace = createConversationLatencyTrace("VOICE", 100);
    markConversationLatency(trace, "uiFeedbackAt", 140);
    markConversationLatency(trace, "t1", 150);
    markConversationLatency(trace, "t2", 950);
    markConversationLatency(trace, "t3", 960);
    markConversationLatency(trace, "t4", 1_700);
    markConversationLatency(trace, "t5", 1_850);
    markConversationLatency(trace, "t6", 1_860);
    markConversationLatency(trace, "t7", 2_500);
    markConversationLatency(trace, "t8", 2_620);

    expect(conversationLatencyMetric(trace)).toEqual({
      event: "conversation_playback_started",
      source: "VOICE",
      ui_state_transition_ms: 40,
      stt_latency_ms: 800,
      time_to_first_tutor_output_ms: 750,
      full_tutor_generation_latency_ms: 890,
      tts_audio_ready_latency_ms: 640,
      audio_ready_after_input_ms: 1_550,
      time_to_first_audio_ms: 1_670,
      total_conversational_latency_ms: 2_520,
      first_output_delivery: "complete_response",
      stage_coverage: {
        t0: true,
        t1: true,
        t2: true,
        t3: true,
        t4: true,
        t5: true,
        t6: true,
        t7: true,
        t8: true,
      },
    });
    expect(JSON.stringify(conversationLatencyMetric(trace))).not.toMatch(/transcript|message|audio_blob|turn_id/i);
  });

  it("emits a completed trace once and labels non-streaming first output honestly", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeConversationLatency(listener);
    const trace = createConversationLatencyTrace("TEXT", 10);
    markConversationLatency(trace, "t8", 50);
    emitConversationLatency(trace);
    emitConversationLatency(trace);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      first_output_delivery: "complete_response",
      total_conversational_latency_ms: 40,
    }));
    unsubscribe();
  });
});
