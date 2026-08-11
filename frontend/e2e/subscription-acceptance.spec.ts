import { expect, test, type Page } from "@playwright/test";

const token={access_token:"subscription-access",refresh_token:"subscription-refresh-token-long-enough",token_type:"bearer",expires_in:900};
const account={id:"subscription-user",learner_id:"subscription-learner",email:"subscriber@example.invalid",status:"ACTIVE"};
const tutor={tutor_id:"ananya",display_name:"Ananya",gender:"female",avatar_profile:"/tutors/ananya.jpg",voice_profile:"indian-english-ananya",accent:"Indian English",teaching_style:"patient and encouraging",animation_profile:"animated-2d",prompt_profile:"supportive",vocabulary_profile:"practical",enabled:true};

const plans=[
  {code:"FREE",name:"Free",price_inr:0,billing_period:"No charge",features:["5 AI tutor conversations each day","5 voice minutes each day","40 structured English lessons","Basic progress tracking"]},
  {code:"PREMIUM_MONTHLY",name:"Premium Monthly",price_inr:299,billing_period:"per month",features:["Up to 200 tutor requests each day","120 voice minutes each day","Detailed progress and conversation history"]},
  {code:"PREMIUM_YEARLY",name:"Premium Yearly",price_inr:2999,billing_period:"per year",features:["Everything in Premium Monthly","One annual billing period"]},
];

async function install(page:Page,state:"FREE"|"ACTIVE"){
  await page.addInitScript(value=>sessionStorage.setItem("speakmate.session.v1",JSON.stringify(value)),token);
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown={};
    if(path.endsWith("/me"))body=account;
    else if(path.endsWith("/preference"))body={learner_id:account.learner_id,tutor,language_mode:"ENGLISH_TELUGU",telugu_explanations_enabled:true};
    else if(path.endsWith("/dashboard"))body={learner_id:account.learner_id,completed_sessions:2,current_streak_days:2,total_practice_minutes:12,preferred_tutor_id:"ananya",subscription_tier:state==="ACTIVE"?"PREMIUM_MONTHLY":"FREE",subscription_status:state};
    else if(path.endsWith("/launch/subscription"))body={plan_id:state==="ACTIVE"?"PREMIUM_MONTHLY":"FREE",plan_name:state==="ACTIVE"?"Premium Monthly":"Free",status:state,trial_remaining_days:0,payment_mode:"test",started_at:state==="ACTIVE"?"2026-08-01T00:00:00Z":null,current_period_end:state==="ACTIVE"?"2026-09-01T00:00:00Z":null,entitlements:{daily_conversations:state==="ACTIVE"?200:5,voice_minutes:state==="ACTIVE"?120:5,progress_history:true,conversation_history:state==="ACTIVE"},active_features:["AI tutor conversations","40 structured English lessons","Progress and practice history"],available_plans:plans,can_start_trial:state==="FREE",can_preview_upgrade:true,payment_notice:"Closed-beta payment preview only. No real subscription or charge will be created.",fair_use:"Daily limits are measured and enforced by the server."};
    else if(path.endsWith("/subscription/upgrade"))body={status:"UPGRADE_PREVIEW",payment_mode:"test",real_charge:false};
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
  });
}

for(const [viewport,width] of [["mobile",390],["desktop",1440]] as const){
  test(`${viewport} free subscription is readable and preview-only`,async({page})=>{
    await page.setViewportSize({width,height:900});await install(page,"FREE");await page.goto("/app/subscription");
    await expect(page.getByRole("region",{name:"Current subscription"})).toContainText("Free");
    await expect(page.getByText("₹299")).toBeVisible();await expect(page.getByText("₹2,999")).toBeVisible();
    await expect(page.getByText(/No real payment will be collected/)).toBeVisible();
    await page.getByRole("button",{name:"Preview Premium Monthly"}).click();
    await expect(page.getByRole("status")).toContainText("No subscription or charge was created");
    await page.locator(".skip-link").evaluate((element)=>(element as HTMLElement).blur());
    await page.screenshot({path:`test-results/subscription-free-${viewport}.png`,fullPage:true});
  });
}

test("active subscriber sees status, period, and no duplicate trial",async({page})=>{
  await install(page,"ACTIVE");await page.goto("/app/subscription");
  await expect(page.getByRole("region",{name:"Current subscription"})).toContainText("Premium Monthly");
  await expect(page.getByText("ACTIVE")).toBeVisible();await expect(page.getByText("200 conversations")).toBeVisible();
  await expect(page.getByRole("button",{name:/Start 7-day/})).toHaveCount(0);
  await page.screenshot({path:"test-results/subscription-active-desktop.png",fullPage:true});
});
