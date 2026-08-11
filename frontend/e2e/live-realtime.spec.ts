import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_REALTIME_ACCEPTANCE,"requires an isolated backend with Realtime enabled");
test.setTimeout(180_000);

test("live Realtime establishes one hands-free WebRTC session and produces tutor audio",async({page,request})=>{
  await assertSafeLiveTarget(request);
  const email=`live-realtime-${Date.now()}@example.com`;
  const registered=await request.post("/api/v1/auth/register",{data:{
    display_name:"Realtime Acceptance",email,mobile_number:`6${String(Date.now()).slice(-9)}`,password:"StrongPassword123!",
    invitation_code:process.env.LIVE_REGISTRATION_INVITE,terms_privacy_accepted:true,
  }});
  expect(registered.status()).toBe(201);
  const body=await registered.json() as {tokens:{access_token:string;refresh_token:string;token_type:string;expires_in:number}};
  const headers={Authorization:`Bearer ${body.tokens.access_token}`};
  expect((await request.put("/api/v1/tutors/preference",{headers,data:{tutor_id:"ananya",language_mode:"ENGLISH"}})).status()).toBe(200);
  await page.addInitScript(tokens=>sessionStorage.setItem("speakmate.session.v1",JSON.stringify(tokens)),body.tokens);
  let callCount=0;
  page.on("request",req=>{if(new URL(req.url()).pathname.endsWith("/realtime/calls"))callCount+=1});
  await page.goto("/app/conversation");
  await expect(page.getByRole("button",{name:"Start conversation"})).toBeEnabled({timeout:60_000});
  const started=Date.now();
  await page.getByRole("button",{name:"Start conversation"}).click();
  await expect(page.getByRole("region",{name:"Hands-free voice controls"})).toBeVisible({timeout:30_000});
  await expect(page.locator(".avatar")).toHaveAttribute("data-state","SPEAKING",{timeout:60_000});
  console.log("LIVE_REALTIME_INITIAL_AUDIO_MS",Date.now()-started);
  expect(callCount).toBe(1);
  await expect(page.getByRole("button",{name:/Speak/})).toHaveCount(0);
  await page.getByRole("button",{name:"End conversation"}).click();
});
