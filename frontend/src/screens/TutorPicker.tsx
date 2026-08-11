import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LanguageMode, Tutor } from "../models";
import { useRouter } from "../routes/router";
import { tutorPortrait } from "../tutors/identity";

const LANGUAGE_MODES: {value: LanguageMode; label: string; description: string}[] = [
  {value:"ENGLISH",label:"English",description:"Tutor responses and explanations stay in English."},
  {value:"ENGLISH_TELUGU",label:"English + Telugu explanation",description:"English learning stays central, with natural Telugu help when useful."},
  {value:"TELUGU_DOMINANT",label:"Telugu-dominant explanation",description:"Explanations are mainly natural Telugu, with useful English learning terms retained."},
];

export function TutorPicker(){
  const {navigate}=useRouter();
  const [tutors,setTutors]=useState<Tutor[]>([]);
  const [selected,setSelected]=useState("");
  const [languageMode,setLanguageMode]=useState<LanguageMode>("ENGLISH");
  const [error,setError]=useState("");
  useEffect(()=>{api.tutors().then(setTutors).catch(()=>setError("Tutors are unavailable. Please retry."))},[]);
  async function save(){try{await api.savePreference(selected,languageMode);navigate("/app/dashboard",true)}catch{setError("Your tutor choice could not be saved.")}}
  return <main className="picker">
    <h1>Choose your Indian-English tutor</h1>
    {!tutors.length&&!error&&<p aria-live="polite">Loading tutors…</p>}
    <div className="tutor-grid" role="radiogroup" aria-label="Tutor choice">{tutors.map(t=><button type="button" role="radio" aria-checked={selected===t.tutor_id} key={t.tutor_id} className={`tutor-card ${selected===t.tutor_id?"selected":""}`} onClick={()=>setSelected(t.tutor_id)}><img src={tutorPortrait(t)} alt=""/><span><small>{t.accent}</small><strong>{t.display_name}</strong><p>{t.teaching_style}</p></span></button>)}</div>
    <fieldset className="language-mode-picker"><legend>Explanation language</legend>{LANGUAGE_MODES.map(mode=><label key={mode.value}><input type="radio" name="language-mode" value={mode.value} checked={languageMode===mode.value} onChange={()=>setLanguageMode(mode.value)}/><span><strong>{mode.label}</strong><small>{mode.description}</small></span></label>)}</fieldset>
    {languageMode!=="ENGLISH"&&<p className="capability-note"><strong>Native Telugu quality review:</strong> every response is reviewed for natural teacher-like Telugu before voice playback.</p>}
    <button disabled={!selected} aria-describedby={!selected?"choose-help":undefined} onClick={()=>void save()}>Continue with my tutor</button>
    {!selected&&<p id="choose-help">Choose one tutor to continue.</p>}<p role="alert">{error}</p>
  </main>
}
