import type { Account, AiTurn, Dashboard, ProgressDetail, SubscriptionView, TokenPair, Tutor, TutorPreference } from "../models";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
export class ApiError extends Error { constructor(public status:number, message:string){super(message)} }
type SessionHooks={get:()=>TokenPair|null;update:(tokens:TokenPair)=>void;clear:()=>void};
let hooks:SessionHooks={get:()=>null,update:()=>undefined,clear:()=>undefined};
export function configureSession(next:SessionHooks){hooks=next}
async function raw<T>(path:string,init:RequestInit={},retry=true):Promise<T>{
  const tokens=hooks.get(); const headers=new Headers(init.headers); headers.set("Content-Type","application/json");
  if(tokens)headers.set("Authorization",`Bearer ${tokens.access_token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers});
  if(response.status===401&&tokens&&retry&&path!=="/api/v1/auth/refresh"){
    const refreshed=await fetch(`${API_BASE}/api/v1/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:tokens.refresh_token})});
    if(refreshed.ok){hooks.update(await refreshed.json() as TokenPair);return raw<T>(path,init,false)} hooks.clear();
  }
  if(!response.ok){const body=await response.json().catch(()=>({}));const message=response.status===401?"Your session could not be verified.":(body?.error?.message||body?.detail||"Request failed");throw new ApiError(response.status,message)}
  return (response.status===204?undefined:await response.json()) as T;
}
export const api={
  register:(body:{email:string;password:string;display_name:string;invitation_code?:string;terms_privacy_accepted:boolean})=>raw<Account&{tokens:TokenPair}>("/api/v1/auth/register",{method:"POST",body:JSON.stringify(body)}),
  login:(email:string,password:string)=>raw<TokenPair>("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})}),
  me:()=>raw<Account>("/api/v1/auth/me"),
  logout:(refresh_token:string)=>raw<void>("/api/v1/auth/logout",{method:"POST",body:JSON.stringify({refresh_token})}),
  logoutAll:()=>raw<void>("/api/v1/auth/logout-all",{method:"POST"}),
  tutors:()=>raw<Tutor[]>("/api/v1/tutors"), preference:()=>raw<TutorPreference>("/api/v1/tutors/preference"),
  savePreference:(tutor_id:string,telugu_explanations_enabled:boolean)=>raw<TutorPreference>("/api/v1/tutors/preference",{method:"PUT",body:JSON.stringify({tutor_id,telugu_explanations_enabled})}),
  dashboard:()=>raw<Dashboard>("/api/v1/tutors/dashboard"),
  conversation:(learner_id:string)=>raw<{id:string}>("/api/v1/conversations",{method:"POST",body:JSON.stringify({learner_id,scenario_id:"daily-conversation"})}),
  turn:(id:string,message:string,include_telugu_explanation:boolean)=>raw<AiTurn>(`/api/v1/conversations/${id}/ai-turns`,{method:"POST",body:JSON.stringify({message,include_telugu_explanation})}),
  feedback:(body:{rating:number;category:string;severity:string;message:string;contact_allowed:boolean;screenshot_name?:string})=>raw<{accepted:boolean;message:string}>("/api/v1/launch/feedback",{method:"POST",body:JSON.stringify(body)}),
  subscription:()=>raw<SubscriptionView>("/api/v1/launch/subscription"),
  startTrial:()=>raw<{status:string;payment_mode:string}>("/api/v1/launch/subscription/trial",{method:"POST"}),
  requestUpgrade:()=>raw<{status:string;payment_mode:string;real_charge:boolean}>("/api/v1/launch/subscription/upgrade",{method:"POST"}),
  progressDetail:()=>raw<ProgressDetail>("/api/v1/launch/progress"),
  founderDashboard:()=>raw<Record<string,unknown>>("/api/v1/launch/founder-dashboard"),
};
