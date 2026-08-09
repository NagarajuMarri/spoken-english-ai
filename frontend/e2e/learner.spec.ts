import { expect, test, type Page } from "@playwright/test";

const token = { access_token: "access", refresh_token: "refresh-token-value-long-enough", token_type: "bearer", expires_in: 900 };
const account = { id: "user-1", learner_id: "learner-1", email: "browser@example.invalid", status: "ACTIVE" };
const tutor = (id: "ananya" | "arjun") => ({ tutor_id: id, display_name: id === "ananya" ? "Ananya" : "Arjun", gender: id === "ananya" ? "female" : "male", avatar_profile: `/tutors/${id}.jpg`, voice_profile: `indian-english-${id}`, accent: "Indian English", teaching_style: "patient and encouraging", animation_profile: "animated-2d", prompt_profile: "supportive", vocabulary_profile: "practical", enabled: true });

function wavFixture(durationSeconds = 1.4) {
  const sampleRate = 8000;
  const sampleCount = Math.floor(sampleRate * durationSeconds);
  const bytes = Buffer.alloc(44 + sampleCount * 2);
  bytes.write("RIFF", 0);
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * 2, 28);
  bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36);
  bytes.writeUInt32LE(sampleCount * 2, 40);
  for (let index = 0; index < sampleCount; index += 1) {
    bytes.writeInt16LE(Math.round(Math.sin(index / 8) * 2500), 44 + index * 2);
  }
  return bytes;
}

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/speech")) {
      await route.fulfill({
        status: 200,
        contentType: "audio/wav",
        headers: {
          "X-TTS-Provider": "openai",
          "X-TTS-Model": "gpt-4o-mini-tts",
          "X-TTS-Voice": "marin",
          "X-TTS-Cache": "MISS",
        },
        body: wavFixture(),
      });
      return;
    }
    let body: unknown = {};
    if (path.endsWith("/login")) body = token;
    else if (path.endsWith("/me")) body = account;
    else if (path === "/api/v1/tutors") body = [tutor("ananya"), tutor("arjun")];
    else if (path.endsWith("/preference")) body = { learner_id: "learner-1", tutor: tutor("ananya"), telugu_explanations_enabled: true, language_mode: "ENGLISH_TELUGU" };
    else if (path.endsWith("/dashboard")) body = { learner_id: "learner-1", completed_sessions: 3, current_streak_days: 2, total_practice_minutes: 8, preferred_tutor_id: "ananya", subscription_tier: "FREE", subscription_status: "READY_FOR_PROVIDER_INTEGRATION" };
    else if (path.endsWith("/conversations")) body = { id: "conversation-1" };
    else if (path.endsWith("/ai-turns")) body = { turn_id: "feature-7-turn", tutor_message: "Thanks for sharing.", next_question: "What happened next?", correction_explanation: "Use the past tense here.", vocabulary_suggestions: ["confident", "routine"], telugu_explanation: "ఇక్కడ భూతకాలం ఉపయోగించండి.", expression_hint: "CORRECTIVE" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function authenticated(page: Page) {
  await page.addInitScript((value) => sessionStorage.setItem("speakmate.session.v1", JSON.stringify(value)), token);
  await mockApi(page);
}

for (const [name, width] of [["mobile", 390], ["tablet", 768], ["desktop", 1440]] as const) {
  test(`${name} login viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await mockApi(page);
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Continue learning" })).toBeVisible();
  });
}

test("protected redirect and login", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("browser@example.invalid");
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.getByText("Ready for today’s conversation?")).toBeVisible();
});

test("tutor selection and Settings change", async ({ page }) => {
  await authenticated(page);
  await page.goto("/onboarding");
  await page.getByRole("radio", { name: /Ananya/ }).click();
  await expect(page.getByRole("radio", { name: /Ananya/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: /Arjun/ }).click();
  await page.getByRole("button", { name: "Continue with my tutor" }).click();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Change tutor" }).click();
  await expect(page.getByRole("radio", { name: /Arjun/ })).toBeVisible();
});

test("lesson, conversation feedback, Telugu, reduced motion, and clean console", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await authenticated(page);
  await page.goto("/app/daily-lesson");
  await expect(page.getByText("A confident morning routine")).toBeVisible();
  await page.getByRole("button", { name: "Begin lesson" }).click();
  await page.getByLabel("Your message").fill("I go yesterday");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Use the past tense here.")).toBeVisible();
  await expect(page.getByText("confident")).toBeVisible();
  await expect(page.getByText(/భూతకాలం/)).toBeVisible();
  await expect(page.locator(".avatar")).toHaveClass(/reduced-motion/);
  expect(errors).toEqual([]);
});

test("Feature 7 uses real audio lifecycle for speaking, reset, replay, and recovery", async ({ page }) => {
  await authenticated(page);
  await page.addInitScript(() => {
    const nativePlay = HTMLMediaElement.prototype.play;
    let blockFirstAutoplay = true;
    HTMLMediaElement.prototype.play = function playWithOneAutoplayBlock() {
      if (blockFirstAutoplay) {
        blockFirstAutoplay = false;
        return Promise.reject(new DOMException("autoplay blocked for acceptance test", "NotAllowedError"));
      }
      return nativePlay.call(this);
    };
  });
  await page.goto("/app/conversation");
  await page.getByLabel("Your message").fill("I go yesterday");
  await page.getByRole("button", { name: "Send" }).click();
  const avatar = page.locator(".avatar");
  await expect(page.getByText(/Provider: openai/)).toBeVisible();
  await expect(avatar).toHaveAttribute("data-state", "THINKING");
  await expect(avatar).toHaveAttribute("data-mouth", "REST");
  await page.getByRole("button", { name: "Play tutor voice" }).click();
  await expect(avatar).toHaveAttribute("data-state", "SPEAKING");
  await expect(avatar).toHaveAttribute("data-expression", "CORRECTIVE");
  await expect.poll(async () => avatar.getAttribute("data-mouth")).not.toBe("REST");
  await page.screenshot({ path: "test-results/feature7-speaking-runtime.png", fullPage: true });
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(avatar).toHaveAttribute("data-state", "IDLE");
  await expect(avatar).toHaveAttribute("data-mouth", "REST");
  await page.getByRole("button", { name: "Replay" }).click();
  await expect(avatar).toHaveAttribute("data-state", "SPEAKING");
  await expect.poll(async () => avatar.getAttribute("data-mouth")).not.toBe("REST");
  await page.getByLabel(/Tutor audio for/).dispatchEvent("error");
  await expect(avatar).toHaveAttribute("data-state", "ERROR");
  await expect(avatar).toHaveAttribute("data-mouth", "REST");
  await expect(page.getByRole("alert")).toContainText("Tutor audio could not be played");
  await page.getByRole("button", { name: "Retry OpenAI voice" }).click();
  await expect(page.locator(".audio-path-status")).toContainText("OpenAI tutor audio received");
  await page.getByRole("button", { name: "Play tutor voice" }).click();
  await expect(avatar).toHaveAttribute("data-state", "SPEAKING");
  await expect.poll(async () => avatar.getAttribute("data-mouth")).not.toBe("REST");
});

test("microphone denial remains recoverable with text", async ({ page }) => {
  await authenticated(page);
  await page.addInitScript(() => Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: () => Promise.reject(new DOMException("denied", "NotAllowedError")) } }));
  await page.goto("/app/conversation");
  await page.getByLabel(/consent to voice processing/).check();
  await page.getByRole("button", { name: "Start microphone" }).click();
  await expect(page.getByRole("alert")).toContainText("permission was denied");
  await expect(page.getByLabel("Your message")).toBeEnabled();
});

test("real MediaRecorder bytes become a transcript and learner message", async ({ page }) => {
  let capturedBytes = 0;
  let submitted = "";
  await authenticated(page);
  await page.route("**/api/v1/conversations/*/transcriptions", async (route) => {
    const body = route.request().postDataBuffer();
    capturedBytes = body?.byteLength ?? 0;
    expect(route.request().headers()["content-type"]).toContain("audio/webm");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ transcript: "I practise English every morning.", detected_language: "en", duration_ms: 500, size_bytes: capturedBytes }) });
  });
  await page.route("**/api/v1/conversations/*/ai-turns", async (route) => {
    submitted = JSON.parse(route.request().postData() ?? "{}").message;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tutor_message: "Thank you.", next_question: "What next?", vocabulary_suggestions: [] }) });
  });
  await page.goto("/app/conversation");
  await page.getByLabel(/consent to voice processing/).check();
  await page.getByRole("button", { name: "Start microphone" }).click();
  await expect(page.getByText(/Microphone: recording/)).toBeVisible();
  await expect(page.locator(".avatar")).toHaveAttribute("data-state", "LISTENING");
  await page.waitForTimeout(750);
  await page.getByRole("button", { name: "Stop and transcribe" }).click();
  await expect(page.getByLabel("Recognized speech")).toContainText("I practise English every morning.");
  await expect(page.getByText("You: I practise English every morning.")).toBeVisible();
  expect(capturedBytes).toBeGreaterThan(0);
  expect(submitted).toBe("I practise English every morning.");
});
