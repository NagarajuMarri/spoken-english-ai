import{useEffect,useRef,useState}from"react";
import type{TutorSpeech}from"../models";

export function TutorAudioPlayer({speech,spokenText}:{speech:TutorSpeech|null;spokenText:string}){
 const audio=useRef<HTMLAudioElement>(null);const url=useRef("");
 const[status,setStatus]=useState("OpenAI audio ready.");const[muted,setMuted]=useState(false);
 useEffect(()=>{
 const player=audio.current;
  if(player&&url.current){player.pause();player.removeAttribute("src");player.load()}
  if(url.current){URL.revokeObjectURL(url.current);url.current=""}
  if(!speech||!player)return;
  url.current=URL.createObjectURL(speech.blob);player.src=url.current;player.load();
  void player.play().catch(error=>setStatus(error instanceof DOMException&&error.name==="NotAllowedError"?"Chrome blocked autoplay. Click Play tutor voice.":"Audio is ready. Click Play tutor voice."));
  return()=>{player.pause();if(url.current){URL.revokeObjectURL(url.current);url.current=""}}
 },[speech]);
 const play=()=>{const player=audio.current;if(!player)return;void player.play().catch(()=>setStatus("Chrome blocked playback. Click the player control to begin."))};
 const stop=()=>{const player=audio.current;if(!player)return;player.pause();player.currentTime=0;setStatus("Tutor voice stopped.")};
 const replay=()=>{const player=audio.current;if(!player)return;player.currentTime=0;void player.play().catch(()=>setStatus("Click the player control to replay."))};
 const toggleMute=()=>{const player=audio.current;if(!player)return;player.muted=!muted;setMuted(!muted);setStatus(!muted?"Tutor voice muted.":"Tutor voice unmuted.")};
 return <section className="tutor-audio" aria-label="OpenAI tutor voice player">
  <h3>Tutor voice</h3><p className="ai-disclosure">AI-generated voice · OpenAI</p>
  <audio ref={audio} controls preload="auto" muted={muted} onPlay={()=>setStatus("Tutor voice is playing.")} onEnded={()=>setStatus("Tutor voice finished.")} onError={()=>setStatus("Tutor audio could not be played.")} aria-label={`Tutor audio for: ${spokenText||"latest response"}`}/>
  <div className="audio-actions"><button disabled={!speech} onClick={play}>Play tutor voice</button><button disabled={!speech} onClick={stop}>Stop</button><button disabled={!speech} onClick={replay}>Replay</button><button disabled={!speech} aria-pressed={muted} onClick={toggleMute}>{muted?"Unmute":"Mute"}</button></div>
  <p role="status" aria-live="polite">{speech?status:"No tutor audio yet."}</p>
  {speech&&<p className="audio-evidence">Provider: {speech.provider} · Model: {speech.model} · Voice: {speech.voice}</p>}
 </section>
}
