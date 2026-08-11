import type { Account, AiTurn, CurriculumLesson, Dashboard, LanguageMode, LessonSession, ProgressDetail, SubscriptionView, TokenPair, Tutor, TutorPreference, TutorSpeech, VoiceTranscription } from "../models";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
export class ApiError extends Error {
  constructor(
    public status:number,
    message:string,
    public code="request_failed",
    public retryable=false,
    public requestId?:string,
  ){super(message)}
}
type SessionHooks={get:()=>TokenPair|null;update:(tokens:TokenPair)=>void;clear:(expectedRefreshToken?:string)=>void};
let hooks:SessionHooks={get:()=>null,update:()=>undefined,clear:()=>undefined};
let refreshInFlight:{refreshToken:string;promise:Promise<TokenPair|null>}|null=null;
let lastRotation:{from:string;to:string}|null=null;
const loggingOutTokens=new Set<string>();
export function configureSession(next:SessionHooks){hooks=next}
async function refreshSession(staleTokens:TokenPair,allowDuringLogout=false):Promise<TokenPair|null>{
  const current=hooks.get();
  if(!current)return null;
  if(!allowDuringLogout&&(loggingOutTokens.has(staleTokens.refresh_token)||loggingOutTokens.has(current.refresh_token)))return null;
  if(current.refresh_token!==staleTokens.refresh_token){
    return lastRotation?.from===staleTokens.refresh_token&&lastRotation.to===current.refresh_token?current:null;
  }
  if(!refreshInFlight||refreshInFlight.refreshToken!==current.refresh_token){
    const refreshToken=current.refresh_token;
    const promise=(async()=>{
      try{
        const response=await fetch(`${API_BASE}/api/v1/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:refreshToken})});
        if(!response.ok){
          const latest=hooks.get();
          if(latest?.refresh_token===refreshToken)hooks.clear(refreshToken);
          return null;
        }
        const next=await response.json() as TokenPair;
        const latest=hooks.get();
        if(latest?.refresh_token!==refreshToken)return null;
        if(loggingOutTokens.has(refreshToken))loggingOutTokens.add(next.refresh_token);
        hooks.update(next);
        lastRotation={from:refreshToken,to:next.refresh_token};
        return next;
      }catch{
        return null;
      }finally{
        if(refreshInFlight?.refreshToken===refreshToken)refreshInFlight=null;
      }
    })();
    refreshInFlight={refreshToken,promise};
  }
  const refreshed=await refreshInFlight.promise;
  const latest=hooks.get();
  return refreshed
    &&latest?.refresh_token===refreshed.refresh_token
    &&(allowDuringLogout||!loggingOutTokens.has(refreshed.refresh_token))
    ?refreshed:null;
}
async function raw<T>(path:string,init:RequestInit={},retry=true):Promise<T>{
  const tokens=hooks.get(); const headers=new Headers(init.headers);
  if(!headers.has("Content-Type")&&!(init.body instanceof Blob))headers.set("Content-Type","application/json");
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers});
  if(response.status===401&&tokens&&retry&&path!=="/api/v1/auth/refresh"){
    const refreshed=await refreshSession(tokens);
    if(refreshed&&hooks.get()?.refresh_token===refreshed.refresh_token)return raw<T>(path,init,false);
  }
  if(!response.ok){const body=await response.json().catch(()=>({}));const message=response.status===401?"Your session could not be verified.":(body?.error?.message||body?.detail||"Request failed");throw new ApiError(response.status,message,body?.error?.code,Boolean(body?.error?.retryable),body?.error?.request_id)}
  return (response.status===204?undefined:await response.json()) as T;
}
async function speechRaw(path:string,retry=true):Promise<TutorSpeech>{
  const tokens=hooks.get();const headers=new Headers();
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{method:"POST",headers});
  if(response.status===401&&tokens&&retry){
    const refreshed=await refreshSession(tokens);
    if(refreshed&&hooks.get()?.refresh_token===refreshed.refresh_token)return speechRaw(path,false);
  }
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new ApiError(response.status,body?.error?.message||"Tutor voice request failed",body?.error?.code,Boolean(body?.error?.retryable),body?.error?.request_id)}
  const contentType=response.headers.get("Content-Type")?.split(";",1)[0]??"";
  if(contentType!=="audio/mpeg"&&contentType!=="audio/wav")throw new ApiError(502,"Tutor voice returned an unsupported audio format.","tts_invalid_audio",false);
  const blob=await response.blob();
  if(blob.size<32)throw new ApiError(502,"Tutor voice returned empty audio.","tts_invalid_audio",false);
  return{
    blob,provider:response.headers.get("X-TTS-Provider")??"unknown",
    model:response.headers.get("X-TTS-Model")??"unknown",
    voice:response.headers.get("X-TTS-Voice")??"unknown",
    cacheStatus:response.headers.get("X-TTS-Cache")??"unknown",
    inputCharacters:Number(response.headers.get("X-TTS-Input-Characters")??0),
    providerRequests:Number(response.headers.get("X-TTS-Provider-Requests")??0),
    usageClassification:response.headers.get("X-TTS-Usage-Classification")??"unavailable",
  };
}
async function sdpRaw(path:string,sdp:string,retry=true):Promise<string>{
  const tokens=hooks.get();const headers=new Headers({"Content-Type":"application/sdp"});
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{method:"POST",headers,body:sdp});
  if(response.status===401&&tokens&&retry){
    const refreshed=await refreshSession(tokens);
    if(refreshed&&hooks.get()?.refresh_token===refreshed.refresh_token)return sdpRaw(path,sdp,false);
  }
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new ApiError(response.status,body?.error?.message||"Live voice is temporarily unavailable.",body?.error?.code,Boolean(body?.error?.retryable),body?.error?.request_id)}
  const contentType=response.headers.get("Content-Type")?.split(";",1)[0]??"";
  if(contentType!=="application/sdp")throw new ApiError(502,"Live voice returned an invalid connection.","realtime_invalid_answer",true);
  return response.text();
}
async function endSession(initialRefreshToken:string,allDevices=false):Promise<void>{
  let refreshToken=initialRefreshToken;
  const ownedTokens=new Set([refreshToken]);
  loggingOutTokens.add(refreshToken);
  const own=(token:string)=>{ownedTokens.add(token);loggingOutTokens.add(token)};
  const send=async(token:string)=>{
    if(hooks.get()?.refresh_token!==token)return false;
    await raw<void>(
      allDevices?"/api/v1/auth/logout-all":"/api/v1/auth/logout",
      {method:"POST",...(allDevices?{}:{body:JSON.stringify({refresh_token:token})})},
      false,
    );
    return true;
  };
  try{
    let current=hooks.get();
    if(!current)return;
    if(current.refresh_token!==refreshToken){
      if(lastRotation?.from!==refreshToken||lastRotation.to!==current.refresh_token)return;
      refreshToken=current.refresh_token;
      own(refreshToken);
    }
    const activeRefresh=refreshInFlight?.refreshToken===refreshToken?refreshInFlight.promise:null;
    if(activeRefresh){
      const refreshed=await activeRefresh;
      if(!refreshed||hooks.get()?.refresh_token!==refreshed.refresh_token)return;
      refreshToken=refreshed.refresh_token;
      own(refreshToken);
    }
    try{
      if(!await send(refreshToken))return;
    }catch(error){
      if(!(error instanceof ApiError)||error.status!==401)throw error;
      current=hooks.get();
      if(!current||current.refresh_token!==refreshToken)throw error;
      const refreshed=await refreshSession(current,true);
      if(!refreshed)throw error;
      refreshToken=refreshed.refresh_token;
      own(refreshToken);
      if(!await send(refreshToken))return;
    }
  }finally{
    const latest=hooks.get();
    if(latest&&ownedTokens.has(latest.refresh_token))hooks.clear(latest.refresh_token);
    for(const token of ownedTokens)loggingOutTokens.delete(token);
  }
}
export const api={
  register:(body:{email:string;mobile_number:string;password:string;display_name:string;invitation_code?:string;terms_privacy_accepted:boolean})=>raw<Account&{tokens:TokenPair}>("/api/v1/auth/register",{method:"POST",body:JSON.stringify(body)}),
  login:(identifier:string,password:string)=>raw<TokenPair>("/api/v1/auth/login",{method:"POST",body:JSON.stringify({identifier,password})}),
  requestPasswordReset:(email:string)=>raw<{message:string}>("/api/v1/auth/password-reset/request",{method:"POST",body:JSON.stringify({email})}),
  validatePasswordReset:(email:string,code:string)=>raw<{valid:boolean}>("/api/v1/auth/password-reset/validate",{method:"POST",body:JSON.stringify({email,code})}),
  confirmPasswordReset:async(email:string,code:string,new_password?:string)=>{const session=hooks.get();const result=await raw<{message:string}>("/api/v1/auth/password-reset/confirm",{method:"POST",body:JSON.stringify({email,code,new_password:new_password??code})});const current=hooks.get();if(session&&current&&(current.refresh_token===session.refresh_token||(lastRotation?.from===session.refresh_token&&lastRotation.to===current.refresh_token)))hooks.clear(current.refresh_token);return result},
  me:()=>raw<Account>("/api/v1/auth/me"),
  logout:(refreshToken:string)=>endSession(refreshToken),
  logoutAll:()=>{const current=hooks.get();return current?endSession(current.refresh_token,true):Promise.resolve()},
  tutors:()=>raw<Tutor[]>("/api/v1/tutors"), preference:()=>raw<TutorPreference>("/api/v1/tutors/preference"),
  savePreference:(tutor_id:string,language_mode:LanguageMode)=>raw<TutorPreference>("/api/v1/tutors/preference",{method:"PUT",body:JSON.stringify({tutor_id,language_mode})}),
  dashboard:()=>raw<Dashboard>("/api/v1/tutors/dashboard"),
  dailyLesson:(learnerId:string)=>raw<CurriculumLesson>(`/api/v1/learners/${learnerId}/daily-lesson`),
  createLessonSession:(learner_id:string,lesson_id:string)=>raw<LessonSession>("/api/v1/lesson-sessions",{method:"POST",body:JSON.stringify({learner_id,lesson_id})}),
  completeLessonSession:(sessionId:string,duration_seconds:number)=>raw<LessonSession>(`/api/v1/lesson-sessions/${sessionId}/complete`,{method:"POST",body:JSON.stringify({duration_seconds})}),
  conversation:(learner_id:string,lesson?:Pick<CurriculumLesson,"id"|"scenario_id">)=>raw<{id:string;opening_prompt?:string;opening_turn_id?:string}>("/api/v1/conversations",{method:"POST",body:JSON.stringify({learner_id,scenario_id:lesson?.scenario_id??"daily-conversation",lesson_id:lesson?.id})}),
  realtimeCall:(conversationId:string,languageMode:LanguageMode,lessonId:string|undefined,sdp:string)=>sdpRaw(`/api/v1/realtime/calls?conversation_id=${encodeURIComponent(conversationId)}&language_mode=${encodeURIComponent(languageMode)}${lessonId?`&lesson_id=${encodeURIComponent(lessonId)}`:""}`,sdp),
  realtimeCapability:()=>raw<{enabled:boolean;maximum_session_seconds?:number;idle_session_seconds?:number}>("/api/v1/realtime/capability"),
  realtimeEvent:(conversationId:string,event:{event_type:"learner_transcript"|"tutor_transcript"|"tutor_interrupted";learner_item_id:string;response_id?:string;transcript?:string})=>raw<{accepted:boolean;turn_id:string;analysis_status:string}>(`/api/v1/realtime/events?conversation_id=${encodeURIComponent(conversationId)}`,{method:"POST",body:JSON.stringify(event)}),
  realtimeTurn:(conversationId:string,learnerItemId:string)=>raw<{turn_id:string;analysis_status:string;correction_summary:string|null;tutor_status:string}>(`/api/v1/realtime/turns/${encodeURIComponent(learnerItemId)}?conversation_id=${encodeURIComponent(conversationId)}`),
  transcribe:(id:string,capture:{blob:Blob;durationMs:number},idempotencyKey:string=globalThis.crypto?.randomUUID?.()??`voice-${Date.now()}-${Math.random().toString(16).slice(2)}`)=>raw<VoiceTranscription>(`/api/v1/conversations/${id}/transcriptions`,{method:"POST",headers:{"Content-Type":capture.blob.type,"X-Audio-Duration-Ms":String(capture.durationMs),"X-Voice-Processing-Consent":"accepted","Idempotency-Key":idempotencyKey},body:capture.blob}),
  turn:(id:string,message:string,_languageMode:LanguageMode,idempotencyKey:string,voice?:{detectedLanguage:string;confidence?:number|null})=>raw<AiTurn>(`/api/v1/conversations/${id}/ai-turns`,{method:"POST",headers:{"Idempotency-Key":idempotencyKey},body:JSON.stringify({message,input_source:voice?"VOICE":"TEXT",detected_language:voice?.detectedLanguage,stt_confidence:voice?.confidence})}),
  speech:(id:string,turnId:string)=>speechRaw(`/api/v1/conversations/${id}/ai-turns/${turnId}/speech`),
  feedback:(body:{rating:number;category:string;severity:string;message:string;contact_allowed:boolean;screenshot_name?:string})=>raw<{accepted:boolean;message:string}>("/api/v1/launch/feedback",{method:"POST",body:JSON.stringify(body)}),
  subscription:()=>raw<SubscriptionView>("/api/v1/launch/subscription"),
  startTrial:()=>raw<{status:string;payment_mode:string}>("/api/v1/launch/subscription/trial",{method:"POST"}),
  requestUpgrade:()=>raw<{status:string;payment_mode:string;real_charge:boolean}>("/api/v1/launch/subscription/upgrade",{method:"POST"}),
  progressDetail:()=>raw<ProgressDetail>("/api/v1/launch/progress"),
  founderDashboard:()=>raw<Record<string,unknown>>("/api/v1/launch/founder-dashboard"),
};
