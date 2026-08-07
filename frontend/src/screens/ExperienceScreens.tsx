import{useCallback,useEffect,useReducer,useRef,useState}from"react";import{api}from"../api/client";import{transition,type AvatarMachine,type AvatarState}from"../avatar/machine";import{useMicrophone,type CapturedAudio}from"../voice/useMicrophone";import{Avatar}from"../components/Avatar";import type{Account,Dashboard,Tutor}from"../models";import{useRouter}from"../routes/router";
export function DashboardScreen({data,tutor}:{data:Dashboard;tutor:Tutor}){const{navigate}=useRouter();return <section className="page"><h1>Ready for today’s conversation?</h1><div className="dashboard-grid"><article className="hero-card"><img src={tutor.avatar_profile} alt={`${tutor.display_name}, your tutor`}/><div><h2>{tutor.display_name}</h2><p>{tutor.teaching_style}</p><button onClick={()=>navigate("/app/conversation")}>Start speaking</button></div></article>{[[data.current_streak_days,"day streak"],[data.completed_sessions,"sessions"],[data.total_practice_minutes,"minutes"]].map(([value,label])=><article className="metric" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>}
export function DailyLessonScreen(){const{navigate}=useRouter();return <section className="page"><h1>A confident morning routine</h1><article className="lesson"><b>10 minutes · Indian English</b><h2>Describe your morning clearly</h2><p>Use usually, afterwards, and routine. Focus on present simple and natural sentence stress.</p><ol><li>Warm-up and listen</li><li>Speak naturally</li><li>Review grammar and vocabulary</li></ol><button onClick={()=>navigate("/app/conversation")}>Begin lesson</button></article></section>}
export function ProgressScreen({data}:{data:Dashboard}){return <section className="page"><h1>Small practice. Real momentum.</h1><div className="progress-grid">{[[data.current_streak_days,"Current streak"],[data.completed_sessions,"Completed sessions"],[data.total_practice_minutes,"Practice minutes"]].map(([value,label])=><article key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>}
export function SettingsScreen({tutor,onChange}:{tutor:Tutor;onChange:()=>void}){const{logoutAll}=useAuthBridge();return <section className="page"><h1>Make practice feel like yours.</h1><article className="settings-card"><img src={tutor.avatar_profile} alt=""/><div><h2>{tutor.display_name}</h2><p>{tutor.voice_profile}</p><button onClick={onChange}>Change tutor</button></div></article><p>Subscription: FREE · provider integration ready. Payments are not enabled.</p><button onClick={()=>void logoutAll()}>Log out on all devices</button></section>}
function useAuthBridge(){return requireAuth()}
import{useAuth as requireAuth}from"../auth/AuthProvider";
function avatarReducer(machine:AvatarMachine,next:AvatarState){try{return transition(machine,next)}catch{return{state:"ERROR" as const}}}
export function ConversationScreen({account,tutor,telugu}:{account:Account;tutor:Tutor;telugu:boolean}){
 const[id,setId]=useState("");
 const[input,setInput]=useState("");
 const[lastTranscript,setLastTranscript]=useState("");
 const[turnError,setTurnError]=useState("");
 const[messages,setMessages]=useState<string[]>([`Namaste! I’m ${tutor.display_name}. Tell me about your day.`]);
 const[feedback,setFeedback]=useState({grammar:"Your correction will appear here.",words:[] as string[],telugu:""});
 const[machine,dispatch]=useReducer(avatarReducer,{state:"IDLE"});
 const[consent,setConsent]=useState(false);
 const timers=useRef<number[]>([]);
 const reduced=window.matchMedia?.("(prefers-reduced-motion: reduce)").matches??false;

 useEffect(()=>{const pending=timers.current;api.conversation(account.learner_id).then(x=>setId(x.id)).catch(()=>dispatch("ERROR"));return()=>pending.forEach(clearTimeout)},[account.learner_id]);

 const submit=useCallback(async(text:string)=>{
  const learnerText=text.trim();
  if(!learnerText||!id)return;
  setTurnError("");
  setMessages(items=>[...items,`You: ${learnerText}`]);
  setInput("");
  dispatch("PROCESSING");
  try{
   dispatch("THINKING");
   const result=await api.turn(id,learnerText,telugu);
   dispatch("SPEAKING");
   setMessages(items=>[...items,`${tutor.display_name}: ${result.tutor_message} ${result.next_question}`]);
   setFeedback({grammar:result.correction_explanation||"That sentence works well.",words:result.vocabulary_suggestions,telugu:result.telugu_explanation||"Telugu explanation will appear when the conversation provider supplies it."});
   timers.current.push(window.setTimeout(()=>dispatch("IDLE"),reduced?0:900));
  }catch(error){
   dispatch("ERROR");
   setTurnError(error instanceof Error?error.message:"The tutor is temporarily unavailable. Please try again.");
  }
 },[id,reduced,telugu,tutor.display_name]);

 const handleCapture=useCallback(async(capture:CapturedAudio)=>{
  if(!id)throw new Error("The conversation is still loading. Please try again.");
  const result=await api.transcribe(id,{blob:capture.blob,durationMs:capture.durationMs});
  setLastTranscript(result.transcript);
  setInput(result.transcript);
  await submit(result.transcript);
 },[id,submit]);
 const mic=useMicrophone(consent,handleCapture);

 return <div className="conversation-layout"><section className="studio"><Avatar tutor={tutor} state={machine.state} reducedMotion={reduced}/><div className="transcript" aria-live="polite">{messages.map((m,i)=><p key={i}>{m}</p>)}</div><label htmlFor="message">Your message</label><div className="composer"><input id="message" value={input} onChange={e=>setInput(e.target.value)}/><button onClick={()=>void submit(input)}>Send</button></div>{turnError&&<p role="alert">{turnError}</p>}<fieldset><legend>Voice controls</legend><label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I consent to voice processing for this turn</label><p aria-live="polite">Microphone: {mic.state}{mic.state==="recording"?` · ${Math.ceil(mic.elapsed/1000)} seconds`:""}</p><p>Browser permission: {mic.permission}</p><button disabled={!consent||!id||mic.state==="recording"||mic.state==="processing"} onClick={()=>void mic.start()}>{mic.state==="denied"?"Retry microphone":"Start microphone"}</button><button disabled={mic.state!=="recording"} onClick={mic.stop}>Stop and transcribe</button><button disabled={mic.state!=="recording"} onClick={mic.cancel}>Cancel</button>{lastTranscript&&<p aria-live="polite" aria-label="Recognized speech"><strong>We heard:</strong> {lastTranscript}</p>}{mic.errorMessage&&<p role="alert">{mic.errorMessage} {mic.state==="denied"&&"Enable microphone access in Chrome site settings, then retry."}</p>}</fieldset></section><aside className="coach" aria-live="polite"><h2>Live coaching</h2><h3>Grammar correction</h3><p>{feedback.grammar}</p><h3>Vocabulary</h3><div className="chips">{feedback.words.length?feedback.words.map(w=><span key={w}>{w}</span>):<span>No suggestions yet.</span>}</div>{telugu&&<><h3>Telugu explanation</h3><p>{feedback.telugu}</p></>}</aside></div>}
