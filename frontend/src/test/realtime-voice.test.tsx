import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { useRealtimeVoice } from "../voice/useRealtimeVoice";

class FakeChannel {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  sent: string[] = [];
  send(value: string) { this.sent.push(value); }
  close() { return undefined; }
}

class FakePeer {
  static last: FakePeer;
  static instances: FakePeer[]=[];
  channel = new FakeChannel();
  ontrack: ((event: RTCTrackEvent) => void) | null = null;
  onconnectionstatechange: (()=>void)|null=null;
  connectionState:RTCPeerConnectionState="new";
  constructor() { FakePeer.last = this;FakePeer.instances.push(this); }
  addTrack() { return {} as RTCRtpSender; }
  createDataChannel() { return this.channel as unknown as RTCDataChannel; }
  async createOffer() { return {type:"offer",sdp:"v=0\r\no=fake"} as RTCSessionDescriptionInit; }
  async setLocalDescription() { return undefined; }
  async setRemoteDescription() { return undefined; }
  close() { return undefined; }
}

const stopTrack=vi.fn();
const media={getTracks:()=>[{stop:stopTrack}],getAudioTracks:()=>[{enabled:true}]} as unknown as MediaStream;

beforeEach(()=>{
  stopTrack.mockClear();
  FakePeer.instances=[];
  Object.defineProperty(window,"RTCPeerConnection",{configurable:true,value:FakePeer});
  Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(media)}});
  vi.spyOn(HTMLMediaElement.prototype,"pause").mockImplementation(()=>undefined);
});

describe("hands-free realtime voice",()=>{
  it("opens one persistent session and follows server VAD state events",async()=>{
    vi.spyOn(api,"realtimeCall").mockResolvedValue("v=0\r\no=answer");
    const events=vi.fn();
    const{result}=renderHook(()=>useRealtimeVoice(events));
    await act(async()=>expect(await result.current.start("conversation-1","ENGLISH","lesson-01")).toBe(true));
    expect(api.realtimeCall).toHaveBeenCalledOnce();
    await act(async()=>expect(await result.current.start("conversation-1","ENGLISH","lesson-01")).toBeUndefined());
    expect(api.realtimeCall).toHaveBeenCalledOnce();
    act(()=>FakePeer.last.channel.onmessage?.({data:JSON.stringify({type:"input_audio_buffer.speech_stopped"})} as MessageEvent));
    await waitFor(()=>expect(result.current.state).toBe("thinking"));
    act(()=>FakePeer.last.channel.onmessage?.({data:JSON.stringify({type:"input_audio_buffer.speech_started"})} as MessageEvent));
    await waitFor(()=>expect(result.current.state).toBe("listening"));
    expect(events).toHaveBeenCalledWith(expect.objectContaining({type:"input_audio_buffer.speech_started"}));
  });

  it("falls back with a learner-safe error and releases microphone media",async()=>{
    vi.spyOn(api,"realtimeCall").mockRejectedValue(new Error("provider secret detail"));
    const{result}=renderHook(()=>useRealtimeVoice());
    await act(async()=>expect(await result.current.start("conversation-1","ENGLISH")).toBe(false));
    expect(result.current.state).toBe("error");
    expect(result.current.error).not.toContain("provider");
    expect(stopTrack).toHaveBeenCalled();
  });

  it("persists completed transcript pairs serially with stable provider ids",async()=>{
    vi.spyOn(api,"realtimeCall").mockResolvedValue("v=0\r\no=answer");
    const persisted=vi.spyOn(api,"realtimeEvent").mockResolvedValue({accepted:true,turn_id:"turn-1",analysis_status:"PENDING"});
    const{result}=renderHook(()=>useRealtimeVoice());
    await act(async()=>{await result.current.start("conversation-1","ENGLISH")});
    act(()=>FakePeer.last.channel.onmessage?.({data:JSON.stringify({type:"conversation.item.input_audio_transcription.completed",item_id:"learner-item-1",transcript:"I am ready."})} as MessageEvent));
    act(()=>FakePeer.last.channel.onmessage?.({data:JSON.stringify({type:"response.output_audio_transcript.done",response_id:"response-1",transcript:"Let us begin."})} as MessageEvent));
    await waitFor(()=>expect(persisted).toHaveBeenCalledTimes(2));
    expect(persisted.mock.calls[0][1]).toEqual(expect.objectContaining({event_type:"learner_transcript",learner_item_id:"learner-item-1"}));
    expect(persisted.mock.calls[1][1]).toEqual(expect.objectContaining({event_type:"tutor_transcript",response_id:"response-1"}));
  });

  it("reconnects once without replaying the opening greeting",async()=>{
    vi.useFakeTimers();vi.spyOn(api,"realtimeCall").mockResolvedValue("v=0\r\no=answer");
    const{result}=renderHook(()=>useRealtimeVoice());
    await act(async()=>{await result.current.start("conversation-1","ENGLISH")});
    const initial=FakePeer.last;act(()=>initial.channel.onopen?.());expect(initial.channel.sent).toHaveLength(1);
    await act(async()=>{initial.connectionState="failed";initial.onconnectionstatechange?.();await vi.advanceTimersByTimeAsync(400)});
    expect(api.realtimeCall).toHaveBeenCalledTimes(2);act(()=>FakePeer.last.channel.onopen?.());expect(FakePeer.last.channel.sent).toHaveLength(0);
    expect(FakePeer.instances).toHaveLength(2);vi.useRealTimers();
  });
});
