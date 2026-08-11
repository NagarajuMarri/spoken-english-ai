import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

type Category="english"|"telugu"|"mixed"|"correction";
const corpus:Array<{category:Category;text:string}>=[
  {category:"english",text:"My day is good."},{category:"english",text:"I am Nagaraj."},{category:"english",text:"My hometown is Guntur."},
  {category:"english",text:"I practise English every morning."},{category:"english",text:"I work from home on Fridays."},
  {category:"english",text:"I enjoy reading short stories."},{category:"english",text:"Please ask me about my work."},
  {category:"english",text:"I cooked dinner yesterday."},{category:"english",text:"My hometown is Kanpur."},{category:"english",text:"I want to speak more confidently."},
  {category:"telugu",text:"దీని ధర ఎంత అని English లో ఎలా చెప్పాలి?"},{category:"telugu",text:"నేను ఇక్కడ నుంచి హైదరాబాద్ వెళ్లాలనుకుంటున్నాను. దీన్ని English లో ఎలా చెప్పాలి?"},
  {category:"telugu",text:"నాకు ఒక గ్లాసు నీళ్లు కావాలి అని ఇంగ్లీషులో ఎలా చెప్పాలి?"},{category:"telugu",text:"రేపు నేను ఆఫీసుకు ఆలస్యంగా వస్తాను అని ఎలా చెప్పాలి?"},
  {category:"telugu",text:"ఈ బస్సు రైల్వే స్టేషన్‌కు వెళ్తుందా అని ఎలా అడగాలి?"},{category:"telugu",text:"నాకు ఈ పదం అర్థం కాలేదు. తెలుగులో వివరించండి."},
  {category:"telugu",text:"నేను ఉద్యోగ ఇంటర్వ్యూకి సిద్ధమవుతున్నాను. సహాయం చేయండి."},{category:"telugu",text:"డాక్టర్ అపాయింట్మెంట్ కావాలి అని ఎలా చెప్పాలి?"},
  {category:"telugu",text:"నా పని పూర్తయింది అని మేనేజర్‌కు ఎలా చెప్పాలి?"},{category:"telugu",text:"దయచేసి నెమ్మదిగా మాట్లాడండి అని ఇంగ్లీషులో ఎలా చెప్పాలి?"},
  {category:"mixed",text:"Today meeting లో project update ఎలా చెప్పాలి?"},{category:"mixed",text:"Bus stop ఎక్కడ ఉంది అని English లో అడగాలి."},
  {category:"mixed",text:"I finished my పని, now what should I say to my manager?"},{category:"mixed",text:"Tomorrow leave కావాలి, polite English sentence చెప్పండి."},
  {category:"mixed",text:"This word meaning తెలుగులో explain చేయండి."},
  {category:"correction",text:"She go to office every day."},{category:"correction",text:"I am having two brothers."},
  {category:"correction",text:"Yesterday I go to market."},{category:"correction",text:"He don't like coffee."},{category:"correction",text:"I did not went there."},
];

test.skip(!process.env.LIVE_REALTIME_CAMPAIGN,"requires isolated live Realtime and TTS provider access");
test.setTimeout(1_800_000);

test("30 spoken turns meet Realtime latency and language gates",async({page,request})=>{
  await assertSafeLiveTarget(request);
  const key=process.env.SPOKEN_ENGLISH_OPENAI_API_KEY;if(!key)throw new Error("OpenAI key is required");
  const registered=await request.post("/api/v1/auth/register",{data:{display_name:"Realtime Corpus",email:`realtime-corpus-${Date.now()}@example.com`,mobile_number:`9${String(Date.now()).slice(-9)}`,password:"StrongPassword123!",invitation_code:process.env.LIVE_REGISTRATION_INVITE,terms_privacy_accepted:true}});
  expect(registered.status()).toBe(201);const account=await registered.json() as {tokens:{access_token:string;refresh_token:string;token_type:string;expires_in:number}};
  await request.put("/api/v1/tutors/preference",{headers:{Authorization:`Bearer ${account.tokens.access_token}`},data:{tutor_id:"ananya",language_mode:"ENGLISH_TELUGU"}});
  await page.addInitScript(tokens=>{
    sessionStorage.setItem("speakmate.session.v1",JSON.stringify(tokens));
    const original=RTCPeerConnection.prototype.createDataChannel;
    RTCPeerConnection.prototype.createDataChannel=function(...args){
      const dc=original.apply(this,args as Parameters<typeof original>);(window as unknown as {__liveDC:RTCDataChannel}).__liveDC=dc;
      dc.addEventListener("message",message=>{try{const event=JSON.parse(String(message.data));(window as unknown as {__liveEvents:Array<{at:number;event:Record<string,unknown>}>}).__liveEvents.push({at:performance.now(),event})}catch{return}});return dc;
    };
    (window as unknown as {__liveEvents:Array<{at:number;event:Record<string,unknown>}>}).__liveEvents=[];
  },account.tokens);
  await page.goto("/app/conversation");await page.getByRole("button",{name:"Start conversation"}).click();
  await expect(page.getByRole("region",{name:"Hands-free voice controls"})).toBeVisible({timeout:30_000});
  await page.waitForFunction(()=>(window as unknown as {__liveDC?:RTCDataChannel}).__liveDC?.readyState==="open");
  await page.waitForFunction(()=>(window as unknown as {__liveEvents:Array<{event:{type?:string}}>}).__liveEvents.some(item=>item.event.type==="response.done"),undefined,{timeout:60_000});

  const synth=async(text:string)=>{
    const spokenText=text.replace(/[.,?!।]/g," ");const response=await fetch("https://api.openai.com/v1/audio/speech",{method:"POST",headers:{Authorization:`Bearer ${key}`,"Content-Type":"application/json"},body:JSON.stringify({model:"gpt-4o-mini-tts",voice:"marin",input:spokenText,instructions:"Speak clearly and continuously in one breath, without dramatic pauses.",response_format:"pcm"})});
    if(!response.ok)throw new Error(`TTS synthesis failed (${response.status})`);return Buffer.from(await response.arrayBuffer()).toString("base64");
  };
  const results:Array<Record<string,unknown>>=[];const offset=Number(process.env.LIVE_REALTIME_CAMPAIGN_OFFSET??0);const activeCorpus=corpus.slice(offset,offset+Number(process.env.LIVE_REALTIME_CAMPAIGN_TURNS??corpus.length));
  for(const [localIndex,turn] of activeCorpus.entries()){
    console.log("LIVE_REALTIME_TURN_START",offset+localIndex+1,turn.category);
    const pcm=await synth(turn.text);const marker=await page.evaluate(()=>(window as unknown as {__liveEvents:unknown[]}).__liveEvents.length);
    const sendEnd=await page.evaluate(async audio=>{
      const dc=(window as unknown as {__liveDC:RTCDataChannel}).__liveDC;const bytes=Uint8Array.from(atob(audio),character=>character.charCodeAt(0));
      for(let offset=0;offset<bytes.length;offset+=4800){const chunk=bytes.subarray(offset,offset+4800);let binary="";for(const value of chunk)binary+=String.fromCharCode(value);dc.send(JSON.stringify({type:"input_audio_buffer.append",audio:btoa(binary)}));await new Promise(resolve=>setTimeout(resolve,35))}
      const speechEnd=performance.now();const silence=new Uint8Array(48_000);for(let offset=0;offset<silence.length;offset+=4800){const chunk=silence.subarray(offset,offset+4800);let binary="";for(const value of chunk)binary+=String.fromCharCode(value);dc.send(JSON.stringify({type:"input_audio_buffer.append",audio:btoa(binary)}));await new Promise(resolve=>setTimeout(resolve,35))}return speechEnd;
    },pcm);
    await page.waitForFunction(({from,after})=>(window as unknown as {__liveEvents:Array<{at:number;event:{type?:string}}>}).__liveEvents.slice(from).some(item=>item.at>=after&&item.event.type==="response.output_audio_transcript.done"),{from:marker,after:sendEnd},{timeout:90_000});
    const activeResponseId=await page.evaluate(({from,after})=>{const item=(window as unknown as {__liveEvents:Array<{at:number;event:{type?:string;response_id?:string}}>}).__liveEvents.slice(from).find(entry=>entry.at>=after&&entry.event.type==="response.output_audio_transcript.done");return item?.event.response_id??""},{from:marker,after:sendEnd});
    await page.waitForFunction(({from,responseId})=>(window as unknown as {__liveEvents:Array<{event:{type?:string;response?:{id?:string}}}>}).__liveEvents.slice(from).some(item=>item.event.type==="response.done"&&item.event.response?.id===responseId),{from:marker,responseId:activeResponseId},{timeout:90_000});
    const observed=await page.evaluate(({from,end,responseId})=>{
      const events=(window as unknown as {__liveEvents:Array<{at:number;event:Record<string,unknown>}>}).__liveEvents.slice(from);
      const forResponse=(item:{event:Record<string,unknown>})=>item.event.response_id===responseId||(item.event.response as {id?:string}|undefined)?.id===responseId;
      const at=(type:string)=>events.find(item=>item.event.type===type&&(type.startsWith("response.")?forResponse(item):true))?.at;const transcript=events.find(item=>item.event.type==="response.output_audio_transcript.done"&&forResponse(item))?.event.transcript;
      const learner=events.find(item=>item.event.type==="conversation.item.input_audio_transcription.completed")?.event.transcript;
      const responseIds=new Set(events.filter(item=>item.at>=end&&item.event.type==="response.done"&&(item.event.response as {status?:string}|undefined)?.status!=="cancelled").map(item=>String((item.event.response as {id?:string}|undefined)?.id??"")));
      const responseAt=at("response.created")??NaN;const vadAt=events.filter(item=>item.event.type==="input_audio_buffer.speech_stopped"&&item.at<=responseAt).at(-1)?.at??NaN;const audioAt=events.find(item=>item.event.type==="output_audio_buffer.started"&&item.at>=responseAt)?.at??NaN;return{vad_detection_vs_pcm_end_ms:vadAt-end,response_event_ms:responseAt-vadAt,first_audio_ms:audioAt-vadAt,complete_ms:(at("response.done")??NaN)-vadAt,transcript,learner,response_count:responseIds.size,cancelled_responses:events.filter(item=>item.event.type==="response.done"&&(item.event.response as {status?:string}|undefined)?.status==="cancelled").length,event_types:events.map(item=>item.event.type),errors:events.filter(item=>item.event.type==="error").map(item=>item.event)};
    },{from:marker,end:sendEnd,responseId:activeResponseId});
    results.push({...turn,...observed});if(!Number.isFinite(Number(observed.first_audio_ms)))console.log("LIVE_REALTIME_TURN_FAILURE",JSON.stringify(observed));expect(Number(observed.first_audio_ms)).toBeGreaterThanOrEqual(0);expect(observed.response_count).toBe(1);
  }
  const latency=results.map(item=>Number(item.first_audio_ms)).sort((a,b)=>a-b);const percentile=(p:number)=>latency[Math.ceil(p*latency.length)-1];
  const outputs=results.map(item=>String(item.transcript??"")).join(" ");const silent=results.filter(item=>!item.transcript).length;const duplicates=results.filter(item=>item.response_count!==1).length;
  const sendExactText=async(text:string)=>{const marker=await page.evaluate(()=>(window as unknown as {__liveEvents:unknown[]}).__liveEvents.length);await page.evaluate(value=>{const dc=(window as unknown as {__liveDC:RTCDataChannel}).__liveDC;dc.send(JSON.stringify({type:"conversation.item.create",item:{type:"message",role:"user",content:[{type:"input_text",text:value}]}}));dc.send(JSON.stringify({type:"response.create"}))},text);await page.waitForFunction(from=>(window as unknown as {__liveEvents:Array<{event:{type?:string}}>}).__liveEvents.slice(from).some(item=>item.event.type==="response.output_audio_transcript.done"),marker,{timeout:90_000});return page.evaluate(from=>String((window as unknown as {__liveEvents:Array<{event:{type?:string;transcript?:string}}>}).__liveEvents.slice(from).find(item=>item.event.type==="response.output_audio_transcript.done")?.event.transcript??""),marker)};
  const exactQuality:string[]=[];
  if(activeCorpus.some(item=>item.category==="telugu")){exactQuality.push(await sendExactText("దీని ధర ఎంత అని English లో ఎలా చెప్పాలి?"));exactQuality.push(await sendExactText("నేను ఇక్కడ నుంచి హైదరాబాద్ వెళ్లాలనుకుంటున్నాను. దీన్ని English లో ఎలా చెప్పాలి?"));expect(exactQuality.join(" ")).toMatch(/[\u0c00-\u0c7f]/);expect(exactQuality[0]).toMatch(/how much|price/i);expect(exactQuality[1]).toMatch(/Hyderabad/i)}
  if(activeCorpus.some(item=>item.category==="mixed")){exactQuality.push(await sendExactText("Today meeting లో project update ఎలా చెప్పాలి?"));expect(exactQuality.at(-1)).toMatch(/[\u0c00-\u0c7f]/)}
  const report={turns:results.length,categories:Object.fromEntries(["english","telugu","mixed","correction"].map(category=>[category,results.filter(item=>item.category===category).length])),latency_ms:{min:latency[0],p50:percentile(.5),p95:percentile(.95),max:latency.at(-1)},silent,duplicates,exact_quality:exactQuality,results};
  console.log("LIVE_REALTIME_CAMPAIGN",JSON.stringify(report));expect(silent).toBe(0);expect(duplicates).toBe(0);expect(percentile(.5)).toBeLessThanOrEqual(3000);expect(percentile(.95)).toBeLessThanOrEqual(5000);
  expect(outputs).not.toMatch(/[\u0c80-\u0cff\u0400-\u04ff\u0600-\u06ff\u4e00-\u9fff]/);
});
