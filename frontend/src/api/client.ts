import type { Account, AiTurn, Dashboard, LanguageMode, ProgressDetail, SubscriptionView, TokenPair, Tutor, TutorPreference, TutorSpeech, VoiceTranscription } from "../models";

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
type SessionHooks={get:()=>TokenPair|null;update:(tokens:TokenPair)=>void;clear:()=>void};
let hooks:SessionHooks={get:()=>null,update:()=>undefined,clear:()=>undefined};
export function configureSession(next:SessionHooks){hooks=next}
async function raw<T>(path:string,init:RequestInit={},retry=true):Promise<T>{
  const tokens=hooks.get(); const headers=new Headers(init.headers);
  if(!headers.has("Content-Type")&&!(init.body instanceof Blob))headers.set("Content-Type","application/json");
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers});
  if(response.status===401&&tokens&&retry&&path!=="/api/v1/auth/refresh"){
    const refreshed=await fetch(`${API_BASE}/api/v1/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:tokens.refresh_token})});
    if(refreshed.ok){hooks.update(await refreshed.json() as TokenPair);return raw<T>(path,init,false)} hooks.clear();
  }
  if(!response.ok){const body=await response.json().catch(()=>({}));const message=response.status===401?"Your session could not be verified.":(body?.error?.message||body?.detail||"Request failed");throw new ApiError(response.status,message,body?.error?.code,Boolean(body?.error?.retryable),body?.error?.request_id)}
  return (response.status===204?undefined:await response.json()) as T;
}
async function speechRaw(path:string,retry=true):Promise<TutorSpeech>{
  const tokens=hooks.get();const headers=new Headers();
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{method:"POST",headers});
  if(response.status===401&&tokens&&retry){
    const refreshed=await fetch(`${API_BASE}/api/v1/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:tokens.refresh_token})});
    if(refreshed.ok){hooks.update(await refreshed.json() as TokenPair);return speechRaw(path,false)}hooks.clear();
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
export const api={
  register:(body:{email:string;password:string;display_name:string;invitation_code?:string;terms_privacy_accepted:boolean})=>raw<Account&{tokens:TokenPair}>("/api/v1/auth/register",{method:"POST",body:JSON.stringify(body)}),
  login:(email:string,password:string)=>raw<TokenPair>("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})}),
  requestPasswordReset:(email:string)=>raw<{message:string}>("/api/v1/auth/password-reset/request",{method:"POST",body:JSON.stringify({email})}),
  validatePasswordReset:(token:string)=>raw<{valid:boolean}>("/api/v1/auth/password-reset/validate",{method:"POST",body:JSON.stringify({token})}),
  confirmPasswordReset:async(token:string,new_password:string)=>{const result=await raw<{message:string}>("/api/v1/auth/password-reset/confirm",{method:"POST",body:JSON.stringify({token,new_password})});hooks.clear();return result},
  me:()=>raw<Account>("/api/v1/auth/me"),
  logout:(refresh_token:string)=>raw<void>("/api/v1/auth/logout",{method:"POST",body:JSON.stringify({refresh_token})}),
  logoutAll:()=>raw<void>("/api/v1/auth/logout-all",{method:"POST"}),
  tutors:()=>raw<Tutor[]>("/api/v1/tutors"), preference:()=>raw<TutorPreference>("/api/v1/tutors/preference"),
  savePreference:(tutor_id:string,language_mode:LanguageMode)=>raw<TutorPreference>("/api/v1/tutors/preference",{method:"PUT",body:JSON.stringify({tutor_id,language_mode})}),
  dashboard:()=>raw<Dashboard>("/api/v1/tutors/dashboard"),
  conversation:(learner_id:string)=>raw<{id:string}>("/api/v1/conversations",{method:"POST",body:JSON.stringify({learner_id,scenario_id:"daily-conversation"})}),
  transcribe:(id:string,capture:{blob:Blob;durationMs:number})=>raw<VoiceTranscription>(`/api/v1/conversations/${id}/transcriptions`,{method:"POST",headers:{"Content-Type":capture.blob.type,"X-Audio-Duration-Ms":String(capture.durationMs),"X-Voice-Processing-Consent":"accepted"},body:capture.blob}),
  turn:(id:string,message:string,_languageMode:LanguageMode,idempotencyKey:string,voice?:{detectedLanguage:string;confidence?:number|null})=>raw<AiTurn>(`/api/v1/conversations/${id}/ai-turns`,{method:"POST",headers:{"Idempotency-Key":idempotencyKey},body:JSON.stringify({message,input_source:voice?"VOICE":"TEXT",detected_language:voice?.detectedLanguage,stt_confidence:voice?.confidence})}),
  speech:(id:string,turnId:string)=>speechRaw(`/api/v1/conversations/${id}/ai-turns/${turnId}/speech`),
  feedback:(body:{rating:number;category:string;severity:string;message:string;contact_allowed:boolean;screenshot_name?:string})=>raw<{accepted:boolean;message:string}>("/api/v1/launch/feedback",{method:"POST",body:JSON.stringify(body)}),
  subscription:()=>raw<SubscriptionView>("/api/v1/launch/subscription"),
  startTrial:()=>raw<{status:string;payment_mode:string}>("/api/v1/launch/subscription/trial",{method:"POST"}),
  requestUpgrade:()=>raw<{status:string;payment_mode:string;real_charge:boolean}>("/api/v1/launch/subscription/upgrade",{method:"POST"}),
  progressDetail:()=>raw<ProgressDetail>("/api/v1/launch/progress"),
  founderDashboard:()=>raw<Record<string,unknown>>("/api/v1/launch/founder-dashboard"),
};
