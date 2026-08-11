import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LanguageMode } from "../models";

export type RealtimeVoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "reconnecting" | "error";
export interface RealtimeVoiceEvent { type:string; transcript?:string; responseId?:string; at:number }
type Context={conversationId:string;languageMode:LanguageMode;lessonId?:string};
const MAX_RECONNECTS=2;
const RECONNECT_DELAYS=[400,900];

export function useRealtimeVoice(onEvent?: (event: RealtimeVoiceEvent) => void) {
  const [state,setState]=useState<RealtimeVoiceState>("idle");
  const [error,setError]=useState("");
  const peer=useRef<RTCPeerConnection|undefined>(undefined);const stream=useRef<MediaStream|undefined>(undefined);const audio=useRef<HTMLAudioElement|undefined>(undefined);const channel=useRef<RTCDataChannel|undefined>(undefined);
  const context=useRef<Context|undefined>(undefined);const reconnects=useRef(0);const generation=useRef(0);const reconnectTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const eventCallback=useRef(onEvent);const lastLearnerItem=useRef<string|undefined>(undefined);const persistence=useRef(Promise.resolve());
  useEffect(()=>{eventCallback.current=onEvent},[onEvent]);

  const release=useCallback(()=>{
    channel.current?.close();peer.current?.close();stream.current?.getTracks().forEach(track=>track.stop());audio.current?.pause();
    if(audio.current)audio.current.srcObject=null;
    channel.current=undefined;peer.current=undefined;stream.current=undefined;audio.current=undefined;
  },[]);
  const stop=useCallback(()=>{
    generation.current+=1;if(reconnectTimer.current)clearTimeout(reconnectTimer.current);reconnectTimer.current=undefined;
    context.current=undefined;reconnects.current=0;lastLearnerItem.current=undefined;release();setState("idle");
  },[release]);
  useEffect(()=>stop,[stop]);

  const connect=useCallback(async(ctx:Context,sendGreeting:boolean,run:number):Promise<boolean>=>{
    try{
      const media=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
      if(run!==generation.current){media.getTracks().forEach(track=>track.stop());return false}
      stream.current=media;const pc=new RTCPeerConnection();peer.current=pc;
      const remoteAudio=document.createElement("audio");audio.current=remoteAudio;remoteAudio.autoplay=true;remoteAudio.setAttribute("aria-label","Ananya realtime voice");
      remoteAudio.onplaying=()=>{if(run===generation.current){setState("speaking");eventCallback.current?.({type:"audio.playing",at:performance.now()})}};
      remoteAudio.onended=()=>{if(run===generation.current)setState("listening")};pc.ontrack=event=>{remoteAudio.srcObject=event.streams[0]};
      media.getTracks().forEach(track=>pc.addTrack(track,media));const dc=pc.createDataChannel("oai-events");channel.current=dc;
      dc.onopen=()=>{if(sendGreeting&&run===generation.current)dc.send(JSON.stringify({type:"response.create",response:{instructions:"Greet the learner warmly in one short sentence, then ask the current lesson question."}}))};
      dc.onmessage=message=>{
        if(run!==generation.current)return;let event:Record<string,unknown>;try{event=JSON.parse(String(message.data)) as Record<string,unknown>}catch{return}
        const type=String(event.type??"");if(type==="input_audio_buffer.speech_started")setState("listening");if(type==="input_audio_buffer.speech_stopped")setState("thinking");
        if(type==="response.output_audio.delta")setState("speaking");if(type==="response.output_audio.done"||type==="response.done")setState("listening");
        const transcript=typeof event.transcript==="string"?event.transcript:undefined;const responseId=typeof event.response_id==="string"?event.response_id:undefined;
        const itemId=typeof event.item_id==="string"?event.item_id:undefined;
        if(type==="conversation.item.input_audio_transcription.completed"&&itemId&&transcript){lastLearnerItem.current=itemId;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"learner_transcript",learner_item_id:itemId,transcript})).then(()=>undefined).catch(()=>undefined)}
        if(type==="response.output_audio_transcript.done"&&lastLearnerItem.current&&responseId&&transcript){const learnerItem=lastLearnerItem.current;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"tutor_transcript",learner_item_id:learnerItem,response_id:responseId,transcript})).then(()=>undefined).catch(()=>undefined)}
        if((type==="response.cancelled"||(type==="response.done"&&(event.response as {status?:string}|undefined)?.status==="cancelled"))&&lastLearnerItem.current){const learnerItem=lastLearnerItem.current;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"tutor_interrupted",learner_item_id:learnerItem,response_id:responseId})).then(()=>undefined).catch(()=>undefined)}
        eventCallback.current?.({type,transcript,responseId,at:performance.now()});
      };
      const offer=await pc.createOffer();await pc.setLocalDescription(offer);const answerSdp=await api.realtimeCall(ctx.conversationId,ctx.languageMode,ctx.lessonId,offer.sdp??"");
      if(run!==generation.current){release();return false}await pc.setRemoteDescription({type:"answer",sdp:answerSdp});setState("listening");return true;
    }catch{release();return false}
  },[release]);

  const scheduleReconnect=useCallback(()=>{
    const ctx=context.current;if(!ctx||reconnectTimer.current)return;
    if(reconnects.current>=MAX_RECONNECTS){release();context.current=undefined;setState("error");setError("Hands-free voice disconnected. Retry or use text mode.");return}
    const attempt=reconnects.current++;setState("reconnecting");release();const run=++generation.current;
    reconnectTimer.current=setTimeout(async()=>{reconnectTimer.current=undefined;const ok=await connect(ctx,false,run);if(!ok&&run===generation.current)scheduleReconnect()},RECONNECT_DELAYS[attempt]);
  },[connect,release]);

  const start=useCallback(async(conversationId:string,languageMode:LanguageMode,lessonId?:string)=>{
    if(peer.current||context.current)return;const ctx={conversationId,languageMode,lessonId};context.current=ctx;reconnects.current=0;setState("connecting");setError("");const run=++generation.current;
    const ok=await connect(ctx,true,run);if(!ok&&run===generation.current){context.current=undefined;setState("error");setError("Hands-free voice could not connect. Retry or use text mode.")}return ok;
  },[connect]);
  useEffect(()=>{const pc=peer.current;if(!pc)return;pc.onconnectionstatechange=()=>{if(pc===peer.current&&(pc.connectionState==="failed"||pc.connectionState==="disconnected"))scheduleReconnect()}},[state,scheduleReconnect]);
  const mute=useCallback((muted:boolean)=>stream.current?.getAudioTracks().forEach(track=>{track.enabled=!muted}),[]);
  return{state,error,start,stop,mute,active:state!=="idle"&&state!=="error"};
}
