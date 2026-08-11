import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LanguageMode } from "../models";

export type RealtimeVoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "reconnecting" | "error";

export interface RealtimeVoiceEvent {
  type: string;
  transcript?: string;
  responseId?: string;
  at: number;
}

export function useRealtimeVoice(onEvent?: (event: RealtimeVoiceEvent) => void) {
  const [state, setState] = useState<RealtimeVoiceState>("idle");
  const [error, setError] = useState("");
  const peer = useRef<RTCPeerConnection | undefined>(undefined);
  const stream = useRef<MediaStream | undefined>(undefined);
  const audio = useRef<HTMLAudioElement | undefined>(undefined);
  const channel = useRef<RTCDataChannel | undefined>(undefined);
  const reconnects = useRef(0);
  const eventCallback = useRef(onEvent);
  useEffect(() => { eventCallback.current = onEvent; }, [onEvent]);

  const stop = useCallback(() => {
    channel.current?.close();
    peer.current?.close();
    stream.current?.getTracks().forEach((track) => track.stop());
    audio.current?.pause();
    if (audio.current) audio.current.srcObject = null;
    channel.current = undefined;peer.current = undefined;stream.current = undefined;audio.current = undefined;
    reconnects.current = 0;
    setState("idle");
  }, []);

  useEffect(() => stop, [stop]);

  const start = useCallback(async (conversationId: string, languageMode: LanguageMode, lessonId?: string) => {
    if (peer.current) return;
    setState(reconnects.current ? "reconnecting" : "connecting");setError("");
    try {
      const media = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
      stream.current=media;
      const pc = new RTCPeerConnection();
      peer.current=pc;
      const remoteAudio = document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.setAttribute("aria-label", "Ananya realtime voice");
      remoteAudio.onplaying = () => { setState("speaking");eventCallback.current?.({type:"audio.playing",at:performance.now()}); };
      remoteAudio.onended = () => setState("listening");
      pc.ontrack = (event) => { remoteAudio.srcObject = event.streams[0]; };
      media.getTracks().forEach((track) => pc.addTrack(track,media));
      const dc = pc.createDataChannel("oai-events");
      dc.onopen = () => dc.send(JSON.stringify({type:"response.create",response:{instructions:"Greet the learner warmly in one short sentence, then ask the current lesson question."}}));
      dc.onmessage = (message) => {
        let event: Record<string,unknown>;
        try { event=JSON.parse(String(message.data)) as Record<string,unknown>; } catch { return; }
        const type=String(event.type??"");
        if(type==="input_audio_buffer.speech_started")setState("listening");
        if(type==="input_audio_buffer.speech_stopped")setState("thinking");
        if(type==="response.output_audio.delta")setState("speaking");
        if(type==="response.output_audio.done"||type==="response.done")setState("listening");
        const transcript=typeof event.transcript==="string"?event.transcript:undefined;
        eventCallback.current?.({type,transcript,responseId:typeof event.response_id==="string"?event.response_id:undefined,at:performance.now()});
      };
      const offer=await pc.createOffer();await pc.setLocalDescription(offer);
      const answerSdp=await api.realtimeCall(conversationId,languageMode,lessonId,offer.sdp??"");
      await pc.setRemoteDescription({type:"answer",sdp:answerSdp});
      audio.current=remoteAudio;channel.current=dc;
      reconnects.current=0;setState("listening");
      return true;
    } catch {
      stop();setState("error");setError("Hands-free voice could not connect. Retry or use text mode.");
      return false;
    }
  }, [stop]);

  const mute = useCallback((muted: boolean) => stream.current?.getAudioTracks().forEach((track) => { track.enabled=!muted; }), []);
  return {state,error,start,stop,mute,active:state!=="idle"&&state!=="error"};
}
