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
  void player.play().then(()=>console.info("speakmate_tts_event",{event:"autoplay_started"})).catch(error=>{
   const blocked=error instanceof DOMException&&error.name==="NotAllowedError";
   setStatus(blocked?"Chrome blocked autoplay. Click Play tutor voice.":"Audio is ready. Click Play tutor voice.");
   console.warn("speakmate_tts_event",{event:blocked?"browser_playback_blocked":"browser_playback_failed",reason:blocked?"autoplay_policy":"media_error"});
  });
  return()=>{player.pause();if(url.current){URL.revokeObjectURL(url.current);url.current=""}}
 },[speech]);
 const play=()=>{const player=audio.current;if(!player)return;console.info("speakmate_tts_event",{event:"manual_play_requested"});void player.play().catch(()=>{setStatus("Chrome blocked playback. Click the player control to begin.");console.warn("speakmate_tts_event",{event:"browser_playback_blocked",reason:"manual_play_rejected"})})};
 const stop=()=>{const player=audio.current;if(!player)return;player.pause();player.currentTime=0;setStatus("Tutor voice stopped.");console.info("speakmate_tts_event",{event:"playback_stopped"})};
 const replay=()=>{const player=audio.current;if(!player)return;player.currentTime=0;console.info("speakmate_tts_event",{event:"replay_requested"});void player.play().catch(()=>{setStatus("Click the player control to replay.");console.warn("speakmate_tts_event",{event:"browser_playback_blocked",reason:"replay_rejected"})})};
 const toggleMute=()=>{const player=audio.current;if(!player)return;player.muted=!muted;setMuted(!muted);setStatus(!muted?"Tutor voice muted.":"Tutor voice unmuted.");console.info("speakmate_tts_event",{event:!muted?"playback_muted":"playback_unmuted"})};
 return <section className="tutor-audio" aria-label="OpenAI tutor voice player">
  <h3>Tutor voice</h3><p className="ai-disclosure">AI-generated voice · OpenAI</p>
  <audio ref={audio} controls preload="auto" muted={muted} onPlay={()=>{setStatus("Tutor voice is playing.");console.info("speakmate_tts_event",{event:"playback_started"})}} onEnded={()=>{setStatus("Tutor voice finished.");console.info("speakmate_tts_event",{event:"playback_ended"})}} onError={()=>{setStatus("Tutor audio could not be played.");console.warn("speakmate_tts_event",{event:"browser_audio_error"})}} aria-label={`Tutor audio for: ${spokenText||"latest response"}`}/>
  <div className="audio-actions"><button disabled={!speech} onClick={play}>Play tutor voice</button><button disabled={!speech} onClick={stop}>Stop</button><button disabled={!speech} onClick={replay}>Replay</button><button disabled={!speech} aria-pressed={muted} onClick={toggleMute}>{muted?"Unmute":"Mute"}</button></div>
  <p role="status" aria-live="polite">{speech?status:"No tutor audio yet."}</p>
  {speech&&<p className="audio-evidence">Provider: {speech.provider} · Model: {speech.model} · Voice: {speech.voice}</p>}
 </section>
}
