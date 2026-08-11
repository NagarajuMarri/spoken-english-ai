import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LanguageMode } from "../models";

export type RealtimeVoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "reconnecting" | "error";
export interface RealtimeVoiceEvent { type:string; transcript?:string; responseId?:string; itemId?:string; at:number }
type Context={conversationId:string;languageMode:LanguageMode;lessonId?:string};
const MAX_RECONNECTS=2;
const RECONNECT_DELAYS=[400,900];

function turnInstructions(languageMode:LanguageMode){
  if(languageMode==="ENGLISH")return "Respond in concise, friendly Indian English.";
  return "Begin exactly with ఇంగ్లీష్‌లో: followed immediately by one English target sentence. Then write తెలుగు వివరణ: followed by a primarily natural Telugu explanation in Telugu script. Never put an English planning phrase or filler first. తప్పనిసరిగా తెలుగు వివరణ ఇవ్వాలి; తెలుగు వివరణ లేకుండా సమాధానం పూర్తి చేయవద్దు. Example: ఇంగ్లీష్‌లో: How much is this? తెలుగు వివరణ: దీని ధర అడగడానికి ఈ sentence ఉపయోగించండి. Keep useful English grammar terms in English. Never give an English-only teaching explanation unless the learner explicitly requested English only.";
}

export function useRealtimeVoice(onEvent?: (event: RealtimeVoiceEvent) => void) {
  const [state,setState]=useState<RealtimeVoiceState>("idle");
  const [error,setError]=useState("");
  const peer=useRef<RTCPeerConnection|undefined>(undefined);const stream=useRef<MediaStream|undefined>(undefined);const audio=useRef<HTMLAudioElement|undefined>(undefined);const channel=useRef<RTCDataChannel|undefined>(undefined);
  const context=useRef<Context|undefined>(undefined);const reconnects=useRef(0);const generation=useRef(0);const reconnectTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const responseActive=useRef(false);const pendingResponse=useRef(false);
  const idleTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);const maximumTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);const idleMilliseconds=useRef(300_000);
  const scheduleReconnectRef=useRef<()=>void>(()=>undefined);
  const eventCallback=useRef(onEvent);const lastLearnerItem=useRef<string|undefined>(undefined);const persistence=useRef(Promise.resolve());
  useEffect(()=>{eventCallback.current=onEvent},[onEvent]);

  const release=useCallback(()=>{
    channel.current?.close();peer.current?.close();stream.current?.getTracks().forEach(track=>track.stop());audio.current?.pause();
    if(audio.current)audio.current.srcObject=null;
    channel.current=undefined;peer.current=undefined;stream.current=undefined;audio.current=undefined;responseActive.current=false;pendingResponse.current=false;
  },[]);
  const stop=useCallback(()=>{
    generation.current+=1;if(reconnectTimer.current)clearTimeout(reconnectTimer.current);reconnectTimer.current=undefined;
    if(idleTimer.current)clearTimeout(idleTimer.current);if(maximumTimer.current)clearTimeout(maximumTimer.current);idleTimer.current=undefined;maximumTimer.current=undefined;
    context.current=undefined;reconnects.current=0;lastLearnerItem.current=undefined;responseActive.current=false;pendingResponse.current=false;release();setState("idle");
  },[release]);
  useEffect(()=>stop,[stop]);
  const recordActivity=useCallback(()=>{if(idleTimer.current)clearTimeout(idleTimer.current);idleTimer.current=setTimeout(stop,idleMilliseconds.current)},[stop]);

  const connect=useCallback(async(ctx:Context,sendGreeting:boolean,run:number):Promise<boolean>=>{
    try{
      const media=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
      if(run!==generation.current){media.getTracks().forEach(track=>track.stop());return false}
      stream.current=media;const pc=new RTCPeerConnection();peer.current=pc;
      const remoteAudio=document.createElement("audio");audio.current=remoteAudio;remoteAudio.autoplay=true;remoteAudio.setAttribute("aria-label","Ananya realtime voice");
      remoteAudio.onplaying=()=>{if(run===generation.current){setState("speaking");eventCallback.current?.({type:"audio.playing",at:performance.now()})}};
      remoteAudio.onended=()=>{if(run===generation.current)setState("listening")};pc.ontrack=event=>{remoteAudio.srcObject=event.streams[0]};
      media.getTracks().forEach(track=>pc.addTrack(track,media));const dc=pc.createDataChannel("oai-events");channel.current=dc;
      const createResponse=()=>{if(dc.readyState!=="open")return;responseActive.current=true;dc.send(JSON.stringify({type:"response.create",response:{instructions:turnInstructions(ctx.languageMode)}}))};
      dc.onopen=()=>{if(sendGreeting&&run===generation.current){responseActive.current=true;dc.send(JSON.stringify({type:"response.create",response:{instructions:"Greet the learner warmly in one short sentence, then ask the current lesson question."}}))}};
      dc.onmessage=message=>{
        if(run!==generation.current)return;let event:Record<string,unknown>;try{event=JSON.parse(String(message.data)) as Record<string,unknown>}catch{return}
        recordActivity();
        const type=String(event.type??"");if(type==="input_audio_buffer.speech_started")setState("listening");if(type==="input_audio_buffer.speech_stopped")setState("thinking");
        if(type==="response.created")responseActive.current=true;if(type==="response.output_audio.delta")setState("speaking");if(type==="response.output_audio.done"||type==="response.done")setState("listening");
        const transcript=typeof event.transcript==="string"?event.transcript:undefined;const responseId=typeof event.response_id==="string"?event.response_id:undefined;
        const itemId=typeof event.item_id==="string"?event.item_id:undefined;
        if(type==="conversation.item.input_audio_transcription.completed"&&itemId&&transcript){lastLearnerItem.current=itemId;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"learner_transcript",learner_item_id:itemId,transcript})).then(()=>undefined).catch(()=>undefined);if(responseActive.current)pendingResponse.current=true;else createResponse()}
        if(type==="response.done"){const cancelled=(event.response as {status?:string}|undefined)?.status==="cancelled";responseActive.current=false;if(cancelled&&pendingResponse.current){pendingResponse.current=false;createResponse()}else pendingResponse.current=false}
        if(type==="response.output_audio_transcript.done"&&lastLearnerItem.current&&responseId&&transcript){const learnerItem=lastLearnerItem.current;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"tutor_transcript",learner_item_id:learnerItem,response_id:responseId,transcript})).then(()=>undefined).catch(()=>undefined)}
        if((type==="response.cancelled"||(type==="response.done"&&(event.response as {status?:string}|undefined)?.status==="cancelled"))&&lastLearnerItem.current){const learnerItem=lastLearnerItem.current;persistence.current=persistence.current.then(()=>api.realtimeEvent(ctx.conversationId,{event_type:"tutor_interrupted",learner_item_id:learnerItem,response_id:responseId})).then(()=>undefined).catch(()=>undefined)}
        eventCallback.current?.({type,transcript,responseId,itemId,at:performance.now()});
      };
      const offer=await pc.createOffer();await pc.setLocalDescription(offer);const answerSdp=await api.realtimeCall(ctx.conversationId,ctx.languageMode,ctx.lessonId,offer.sdp??"");
      if(run!==generation.current){release();return false}await pc.setRemoteDescription({type:"answer",sdp:answerSdp});setState("listening");return true;
    }catch{release();return false}
  },[recordActivity,release]);

  const scheduleReconnect=useCallback(()=>{
    const ctx=context.current;if(!ctx||reconnectTimer.current)return;
    if(reconnects.current>=MAX_RECONNECTS){release();context.current=undefined;setState("error");setError("Live voice is temporarily unavailable. Continue in standard voice or Text mode.");return}
    const attempt=reconnects.current++;setState("reconnecting");release();const run=++generation.current;
    reconnectTimer.current=setTimeout(async()=>{reconnectTimer.current=undefined;const ok=await connect(ctx,false,run);if(!ok&&run===generation.current)scheduleReconnectRef.current()},RECONNECT_DELAYS[attempt]);
  },[connect,release]);
  useEffect(()=>{scheduleReconnectRef.current=scheduleReconnect},[scheduleReconnect]);

  const start=useCallback(async(conversationId:string,languageMode:LanguageMode,lessonId?:string)=>{
    if(peer.current||context.current)return;const ctx={conversationId,languageMode,lessonId};context.current=ctx;reconnects.current=0;setState("connecting");setError("");const run=++generation.current;
    try{const limits=await api.realtimeCapability();idleMilliseconds.current=(limits.idle_session_seconds??300)*1000;maximumTimer.current=setTimeout(stop,(limits.maximum_session_seconds??1_800)*1000);recordActivity()}catch{maximumTimer.current=setTimeout(stop,1_800_000);recordActivity()}
    const ok=await connect(ctx,true,run);if(!ok&&run===generation.current){context.current=undefined;setState("error");setError("Hands-free voice could not connect. Retry or use text mode.")}return ok;
  },[connect,recordActivity,stop]);
  useEffect(()=>{const pc=peer.current;if(!pc)return;pc.onconnectionstatechange=()=>{if(pc===peer.current&&(pc.connectionState==="failed"||pc.connectionState==="disconnected"))scheduleReconnect()}},[state,scheduleReconnect]);
  const mute=useCallback((muted:boolean)=>stream.current?.getAudioTracks().forEach(track=>{track.enabled=!muted}),[]);
  return{state,error,start,stop,mute,active:state!=="idle"&&state!=="error"};
}
