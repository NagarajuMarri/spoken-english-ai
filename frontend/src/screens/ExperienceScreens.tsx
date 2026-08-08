import{useCallback,useEffect,useReducer,useRef,useState}from"react";import{ApiError,api}from"../api/client";import{transition,type AvatarMachine,type AvatarState}from"../avatar/machine";import{useMicrophone,type CapturedAudio}from"../voice/useMicrophone";import{TutorAudioPlayer}from"../voice/TutorAudioPlayer";import{Avatar}from"../components/Avatar";import type{Account,Dashboard,LanguageMode,Tutor,TutorSpeech}from"../models";import{useRouter}from"../routes/router";
export function DashboardScreen({data,tutor}:{data:Dashboard;tutor:Tutor}){const{navigate}=useRouter();return <section className="page"><h1>Ready for today’s conversation?</h1><div className="dashboard-grid"><article className="hero-card"><img src={tutor.avatar_profile} alt={`${tutor.display_name}, your tutor`}/><div><h2>{tutor.display_name}</h2><p>{tutor.teaching_style}</p><button onClick={()=>navigate("/app/conversation")}>Start speaking</button></div></article>{[[data.current_streak_days,"day streak"],[data.completed_sessions,"sessions"],[data.total_practice_minutes,"minutes"]].map(([value,label])=><article className="metric" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>}
export function DailyLessonScreen(){const{navigate}=useRouter();return <section className="page"><h1>A confident morning routine</h1><article className="lesson"><b>10 minutes · Indian English</b><h2>Describe your morning clearly</h2><p>Use usually, afterwards, and routine. Focus on present simple and natural sentence stress.</p><ol><li>Warm-up and listen</li><li>Speak naturally</li><li>Review grammar and vocabulary</li></ol><button onClick={()=>navigate("/app/conversation")}>Begin lesson</button></article></section>}
export function ProgressScreen({data}:{data:Dashboard}){return <section className="page"><h1>Small practice. Real momentum.</h1><div className="progress-grid">{[[data.current_streak_days,"Current streak"],[data.completed_sessions,"Completed sessions"],[data.total_practice_minutes,"Practice minutes"]].map(([value,label])=><article key={label}><strong>{value}</strong><span>{label}</span></article>)}</div></section>}
export function SettingsScreen({tutor,onChange}:{tutor:Tutor;onChange:()=>void}){const{logoutAll}=useAuthBridge();return <section className="page"><h1>Make practice feel like yours.</h1><article className="settings-card"><img src={tutor.avatar_profile} alt=""/><div><h2>{tutor.display_name}</h2><p>{tutor.voice_profile}</p><button onClick={onChange}>Change tutor</button></div></article><p>Subscription: FREE · provider integration ready. Payments are not enabled.</p><button onClick={()=>void logoutAll()}>Log out on all devices</button></section>}
function useAuthBridge(){return requireAuth()}
import{useAuth as requireAuth}from"../auth/AuthProvider";
function avatarReducer(machine:AvatarMachine,next:AvatarState){try{if(machine.state==="ERROR"&&next==="PROCESSING")return transition(transition(machine,"IDLE"),"PROCESSING");return transition(machine,next)}catch{return{state:"ERROR" as const}}}
function turnIdentity(){return globalThis.crypto?.randomUUID?.()??`turn-${Date.now()}-${Math.random().toString(16).slice(2)}`}
export function ConversationScreen({account,tutor,languageMode,telugu}:{account:Account;tutor:Tutor;languageMode?:LanguageMode;telugu?:boolean}){
 const selectedLanguageMode:LanguageMode=languageMode??(telugu?"ENGLISH_TELUGU":"ENGLISH");
 const[id,setId]=useState("");
 const[input,setInput]=useState("");
 const[lastTranscript,setLastTranscript]=useState("");
 const[turnError,setTurnError]=useState("");
 const[audioError,setAudioError]=useState("");
 const[audioPathStatus,setAudioPathStatus]=useState("Waiting for the first tutor response.");
 const[audioBusy,setAudioBusy]=useState(false);
 const[speech,setSpeech]=useState<TutorSpeech|null>(null);
 const[spokenText,setSpokenText]=useState("");
 const[lastSpeechTurn,setLastSpeechTurn]=useState("");
 const[pendingTurn,setPendingTurn]=useState<{text:string;key:string;retryable:boolean}|null>(null);
 const[turnBusy,setTurnBusy]=useState(false);
 const turnBusyRef=useRef(false);
 const[messages,setMessages]=useState<string[]>([`Namaste! I’m ${tutor.display_name}. Tell me about your day.`]);
 const[feedback,setFeedback]=useState({grammar:"Your correction will appear here.",words:[] as string[],telugu:""});
 const[languageReview,setLanguageReview]=useState({changed:false,reason:"Waiting for the first reviewed response.",terms:[] as string[]});
 const[machine,dispatch]=useReducer(avatarReducer,{state:"IDLE"});
 const[consent,setConsent]=useState(false);
 const reduced=window.matchMedia?.("(prefers-reduced-motion: reduce)").matches??false;

 useEffect(()=>{api.conversation(account.learner_id).then(x=>setId(x.id)).catch(()=>dispatch("ERROR"))},[account.learner_id]);

 const loadSpeech=useCallback(async(turnId:string)=>{
  if(!id||!turnId){
   setAudioPathStatus("TTS request not made: missing conversation or tutor turn identity.");
   console.warn("speakmate_tts_event",{event:"request_not_made",reason:"missing_identity"});
   return;
  }
  setAudioBusy(true);setAudioError("");
  setAudioPathStatus("Requesting OpenAI tutor audio from the backend…");
  console.info("speakmate_tts_event",{event:"request_started"});
  try{
   const nextSpeech=await api.speech(id,turnId);
   setSpeech(nextSpeech);
   setAudioPathStatus("OpenAI tutor audio received. Starting Chrome playback…");
   console.info("speakmate_tts_event",{event:"audio_fetch_succeeded",provider:nextSpeech.provider,model:nextSpeech.model,voice:nextSpeech.voice,content_type:nextSpeech.blob.type,size_bytes:nextSpeech.blob.size});
  }
  catch(error){
   const backendFailure=error instanceof ApiError;
   setAudioError(error instanceof Error?error.message:"Tutor voice is temporarily unavailable.");
   setAudioPathStatus(backendFailure?"Backend TTS request failed. Use Retry OpenAI voice.":"Audio fetch failed before a backend response. Check the browser network connection.");
   console.warn("speakmate_tts_event",backendFailure?{event:"backend_tts_failed",status:error.status,code:error.code,retryable:error.retryable}:{event:"audio_fetch_failed",reason:"network_or_browser"});
  }
  finally{setAudioBusy(false)}
 },[id]);

 const submit=useCallback(async(text:string,retryKey?:string)=>{
  const learnerText=text.trim();
  if(!learnerText||!id||turnBusyRef.current)return;
  const key=retryKey??turnIdentity();
  turnBusyRef.current=true;
  setTurnError("");
  setAudioError("");
  setAudioPathStatus("Waiting for the tutor text response before requesting audio…");
  setSpeech(null);
  setTurnBusy(true);
  if(!retryKey)setMessages(items=>[...items,`You: ${learnerText}`]);
  setInput("");
  dispatch("PROCESSING");
  try{
   dispatch("THINKING");
   const result=await api.turn(id,learnerText,selectedLanguageMode,key);
   const spoken=`${result.tutor_message} ${result.next_question}`.trim();
   dispatch("IDLE");
   setMessages(items=>[...items,`${tutor.display_name}: ${spoken}`]);
   setSpokenText(spoken);
   setFeedback({grammar:result.correction_explanation||"That sentence works well.",words:result.vocabulary_suggestions,telugu:result.telugu_explanation||"Telugu explanation will appear when the conversation provider supplies it."});
   setLanguageReview({changed:Boolean(result.review_changed),reason:result.review_reason_code||"NOT_REQUIRED",terms:result.preserved_learning_terms||[]});
   setPendingTurn(null);
   if(!result.turn_id){
    setAudioError("Tutor audio was not requested because the completed tutor turn identity is missing. Reload the latest frontend and retry.");
    setAudioPathStatus("TTS request not made: tutor response omitted its turn identity.");
    console.warn("speakmate_tts_event",{event:"request_not_made",reason:"missing_turn_id"});
   }else{
    setLastSpeechTurn(result.turn_id);
    await loadSpeech(result.turn_id);
   }
  }catch(error){
   dispatch("ERROR");
   const retryable=error instanceof ApiError?error.retryable:true;
   setPendingTurn({text:learnerText,key,retryable});
   setInput(learnerText);
   setTurnError(error instanceof Error?error.message:"The tutor is temporarily unavailable. Please try again.");
  }finally{
   turnBusyRef.current=false;
   setTurnBusy(false);
  }
 },[id,loadSpeech,selectedLanguageMode,tutor.display_name]);

 const handleCapture=useCallback(async(capture:CapturedAudio)=>{
  if(!id)throw new Error("The conversation is still loading. Please try again.");
  const result=await api.transcribe(id,{blob:capture.blob,durationMs:capture.durationMs});
  setLastTranscript(result.transcript);
  setInput(result.transcript);
  await submit(result.transcript);
 },[id,submit]);
 const mic=useMicrophone(consent,handleCapture);

 return <div className="conversation-layout"><section className="studio"><Avatar tutor={tutor} state={machine.state} reducedMotion={reduced}/><p className="capability-note"><strong>Language mode:</strong> {selectedLanguageMode.replaceAll("_"," + ")}</p><div className="transcript" aria-live="polite">{messages.map((m,i)=><p key={i}>{m}</p>)}</div><TutorAudioPlayer speech={speech} spokenText={spokenText}/><p className="audio-path-status" role="status" aria-live="polite"><strong>Audio path:</strong> {audioPathStatus}</p>{audioBusy&&<p role="status">Generating OpenAI tutor voice…</p>}{audioError&&<div><p role="alert">{audioError}</p>{lastSpeechTurn&&<button disabled={audioBusy} onClick={()=>void loadSpeech(lastSpeechTurn)}>Retry OpenAI voice</button>}</div>}<label htmlFor="message">Your message</label><div className="composer"><input id="message" value={input} disabled={turnBusy} onChange={e=>setInput(e.target.value)}/><button disabled={turnBusy} onClick={()=>void submit(input,pendingTurn?.retryable&&pendingTurn.text===input.trim()?pendingTurn.key:undefined)}>{turnBusy?"Waiting for tutor…":"Send"}</button></div>{turnError&&<div><p role="alert">{turnError}</p>{pendingTurn?.retryable&&<button disabled={turnBusy} onClick={()=>void submit(pendingTurn.text,pendingTurn.key)}>Retry tutor response</button>}</div>}<fieldset><legend>Voice controls</legend><label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I consent to voice processing for this turn</label><p aria-live="polite">Microphone: {mic.state}{mic.state==="recording"?` · ${Math.ceil(mic.elapsed/1000)} seconds`:""}</p><p>Browser permission: {mic.permission}</p><button disabled={!consent||!id||turnBusy||mic.state==="recording"||mic.state==="processing"} onClick={()=>void mic.start()}>{mic.state==="denied"?"Retry microphone":"Start microphone"}</button><button disabled={mic.state!=="recording"} onClick={mic.stop}>Stop and transcribe</button><button disabled={mic.state!=="recording"} onClick={mic.cancel}>Cancel</button>{lastTranscript&&<p aria-live="polite" aria-label="Recognized speech"><strong>We heard:</strong> {lastTranscript}</p>}{mic.errorMessage&&<p role="alert">{mic.errorMessage} {mic.state==="denied"&&"Enable microphone access in Chrome site settings, then retry."}</p>}</fieldset></section><aside className="coach" aria-live="polite"><h2>Live coaching</h2><h3>Grammar correction</h3><p>{feedback.grammar}</p><h3>Vocabulary</h3><div className="chips">{feedback.words.length?feedback.words.map(w=><span key={w}>{w}</span>):<span>No suggestions yet.</span>}</div>{selectedLanguageMode!=="ENGLISH"&&<><h3>Native Telugu quality review</h3><p>{feedback.telugu}</p><p><strong>Review:</strong> {languageReview.changed?languageReview.reason:"No wording change needed"}</p>{languageReview.terms.length>0&&<p><strong>Learning terms kept in English:</strong> {languageReview.terms.join(", ")}</p>}</>}</aside></div>}
