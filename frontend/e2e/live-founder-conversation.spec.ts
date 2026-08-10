import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_FINAL_PROVIDER_ACCEPTANCE, "requires configured local OpenAI providers");
test.setTimeout(600_000);

test("live founder conversation accepts valid English and records real provider latency", async ({ page, request }) => {
  await assertSafeLiveTarget(request);
  const invitationCode = process.env.LIVE_REGISTRATION_INVITE;
  if (!invitationCode) throw new Error("LIVE_REGISTRATION_INVITE is required");
  const email = `live-founder-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const registered = await request.post("/api/v1/auth/register", { data: {
    display_name: "Founder Conversation",
    email,
    password: "StrongPassword123!",
    invitation_code: invitationCode,
    terms_privacy_accepted: true,
  } });
  expect(registered.status()).toBe(201);
  const registration = await registered.json() as { tokens: { access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number } };
  const authorization = { Authorization: `Bearer ${registration.tokens.access_token}` };
  const preference = await request.put("/api/v1/tutors/preference", {
    headers: authorization,
    data: { tutor_id: "ananya", language_mode: "ENGLISH_TELUGU" },
  });
  expect(preference.status()).toBe(200);

  await page.addInitScript((tokens) => {
    sessionStorage.setItem("speakmate.session.v1", JSON.stringify(tokens));
    HTMLMediaElement.prototype.play = function play() {
      this.dispatchEvent(new Event("playing"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function pause() { this.dispatchEvent(new Event("pause")); };
  }, registration.tokens);

  await page.goto("/app/conversation");
  await expect(page.getByRole("button", { name: "Start conversation" })).toBeEnabled({ timeout: 120_000 });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.getByRole("button", { name: "Text mode" }).click();

  const measured: Array<Record<string, unknown>> = [];
  const speechResponses: Array<{ at: number; serverTiming: string }> = [];
  page.on("response", (response) => {
    if (response.url().includes("/ai-turns/") && response.url().endsWith("/speech")) {
      speechResponses.push({ at: Date.now(), serverTiming: response.headers()["server-timing"] ?? "" });
    }
  });
  const send = async (message: string) => {
    const started = Date.now();
    const speechCount = speechResponses.length;
    let responsePromise = page.waitForResponse((response) => response.url().endsWith("/ai-turns") && response.request().method() === "POST");
    await page.getByLabel("Your message").fill(message);
    await page.getByRole("button", { name: "Send" }).click();
    let response = await responsePromise;
    if (response.status() !== 200) {
      const failure = await response.json() as { error?: { retryable?: boolean } };
      expect(failure.error?.retryable).toBe(true);
      await expect(page.getByRole("button", { name: "Retry tutor response" })).toBeVisible();
      responsePromise = page.waitForResponse((candidate) => candidate.url().endsWith("/ai-turns") && candidate.request().method() === "POST");
      await page.getByRole("button", { name: "Retry tutor response" }).click();
      response = await responsePromise;
    }
    const completed = Date.now();
    expect(response.status()).toBe(200);
    const body = await response.json() as Record<string, unknown>;
    const speechStarted = Date.now();
    await expect.poll(() => speechResponses.length, { timeout: 180_000 }).toBe(speechCount + 1);
    const speech = speechResponses.at(-1)!;
    measured.push({
      message,
      tutor_total_ms: completed - started,
      tts_total_ms: speech.at - speechStarted,
      tutor_server_timing: response.headers()["server-timing"] ?? "",
      tts_server_timing: speech.serverTiming,
      correction_type: body.correction_type,
      coaching_state: body.coaching_state,
    });
    return body;
  };

  const valid = await send("Yeah, hi Ananya. My day is good.");
  expect(valid.correction_type).not.toMatch(/ERROR$/);
  expect(valid.coaching_state).toBe("NORMAL_CONVERSATION");
  expect(valid.corrected_sentence).toBeNull();
  await expect(page.getByText(/Correct form:/)).toHaveCount(0);
  await expect(page.locator(".text-conversation-history p").filter({ hasText: "Yeah, hi Ananya. My day is good." })).toHaveCount(1);

  await send("I work mostly on developing this spoken English learning app from morning.");
  const telugu = await send("I need explanation in Telugu.");
  const teluguText = [telugu.tutor_message, telugu.correction_explanation, telugu.next_question].filter(Boolean).join(" ");
  expect(teluguText).toMatch(/[\u0c00-\u0c7f]/);
  expect(teluguText).not.toMatch(/[\u0600-\u06ff\u0c80-\u0cff\u0400-\u04ff]/);
  console.log("LIVE_FOUNDER_LATENCY", JSON.stringify(measured));
});
