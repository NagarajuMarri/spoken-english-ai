import { expect, test } from "@playwright/test";

test("20 turns continue hands-free in one WebRTC session with barge-in",async({page})=>{
  await page.addInitScript(()=>{
    const channel={onopen:null as null|(()=>void),onmessage:null as null|((event:{data:string})=>void),send:()=>undefined,close:()=>undefined};
    (window as unknown as {__realtimeChannel:typeof channel}).__realtimeChannel=channel;
    class Peer {
      ontrack=null;connectionState="connected";
      createDataChannel(){return channel}
      addTrack(){return {}}
      async createOffer(){return {type:"offer",sdp:"v=0\r\no=browser"}}
      async setLocalDescription(){return undefined}
      async setRemoteDescription(){channel.onopen?.();return undefined}
      close(){return undefined}
    }
    Object.defineProperty(window,"RTCPeerConnection",{value:Peer});
    Object.defineProperty(navigator,"mediaDevices",{value:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>undefined}],getAudioTracks:()=>[{enabled:true}]})}});
    sessionStorage.setItem("speakmate.session.v1",JSON.stringify({access_token:"access",refresh_token:"refresh-token-value-long-enough",token_type:"bearer",expires_in:900}));
  });
  let calls=0;
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/realtime/capability"))return route.fulfill({json:{enabled:true}});
    if(path.endsWith("/realtime/calls")){calls+=1;return route.fulfill({status:200,contentType:"application/sdp",body:"v=0\r\no=server"})}
    if(path.endsWith("/speech"))return route.fulfill({status:200,contentType:"audio/wav",body:Buffer.alloc(64)});
    if(path.endsWith("/me"))return route.fulfill({json:{id:"user-1",learner_id:"learner-1",email:"learner@example.invalid",status:"ACTIVE"}});
    if(path.endsWith("/preference"))return route.fulfill({json:{learner_id:"learner-1",tutor:{tutor_id:"ananya",display_name:"Ananya",gender:"female",avatar_profile:"/tutors/ananya.jpg",voice_profile:"ananya",accent:"Indian English",teaching_style:"patient",animation_profile:"animated-2d",prompt_profile:"supportive",vocabulary_profile:"practical",enabled:true},telugu_explanations_enabled:false,language_mode:"ENGLISH"}});
    if(path.endsWith("/conversations"))return route.fulfill({json:{id:"conversation-realtime",opening_prompt:"Hello",opening_turn_id:"opening-1"}});
    return route.fulfill({json:{}});
  });
  await page.goto("/app/conversation");
  await page.getByRole("button",{name:"Start conversation"}).click();
  await expect(page.getByRole("region",{name:"Hands-free voice controls"})).toBeVisible();
  await expect(page.getByRole("button",{name:/Speak/})).toHaveCount(0);
  for(let turn=0;turn<20;turn+=1){
    await page.evaluate(()=>((window as unknown as {__realtimeChannel:{onmessage:(event:{data:string})=>void}}).__realtimeChannel.onmessage({data:JSON.stringify({type:"input_audio_buffer.speech_started"})})));
    await expect(page.locator(".avatar")).toHaveAttribute("data-state","LISTENING");
    await page.evaluate(()=>((window as unknown as {__realtimeChannel:{onmessage:(event:{data:string})=>void}}).__realtimeChannel.onmessage({data:JSON.stringify({type:"input_audio_buffer.speech_stopped"})})));
    await expect(page.locator(".avatar")).toHaveAttribute("data-state","THINKING");
    await page.evaluate(()=>((window as unknown as {__realtimeChannel:{onmessage:(event:{data:string})=>void}}).__realtimeChannel.onmessage({data:JSON.stringify({type:"response.output_audio.delta"})})));
    await expect(page.locator(".avatar")).toHaveAttribute("data-state","SPEAKING");
    if(turn===9){
      await page.evaluate(()=>((window as unknown as {__realtimeChannel:{onmessage:(event:{data:string})=>void}}).__realtimeChannel.onmessage({data:JSON.stringify({type:"input_audio_buffer.speech_started"})})));
      await expect(page.locator(".avatar")).toHaveAttribute("data-state","LISTENING");
    }
    await page.evaluate(()=>((window as unknown as {__realtimeChannel:{onmessage:(event:{data:string})=>void}}).__realtimeChannel.onmessage({data:JSON.stringify({type:"response.done"})})));
  }
  expect(calls).toBe(1);
  await expect(page.getByRole("button",{name:"End conversation"})).toBeVisible();
});
