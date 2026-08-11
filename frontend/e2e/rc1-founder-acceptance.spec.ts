import { expect, test, type Locator, type Page } from "@playwright/test";

const token = {
  access_token: "access",
  refresh_token: "refresh-token-value-long-enough",
  token_type: "bearer",
  expires_in: 900,
};
const account = {
  id: "user-1",
  learner_id: "learner-1",
  email: "founder-acceptance@example.invalid",
  status: "ACTIVE",
};
const ananya = {
  tutor_id: "ananya",
  display_name: "Ananya",
  gender: "female",
  avatar_profile: "/tutors/ananya.jpg",
  voice_profile: "indian-english-ananya",
  accent: "Indian English",
  teaching_style: "patient and encouraging",
  animation_profile: "volumetric-3d",
  prompt_profile: "supportive",
  vocabulary_profile: "practical",
  enabled: true,
};
const openingPrompt = "Hi, I\u2019m Ananya. I\u2019m ready to practise English with you.";

type MediaProbe = {
  source: string;
  userActivation: boolean;
  gestureDispatch: boolean;
};

type ThreeMetric = {
  event?: string;
  average_fps?: number;
  initialization_ms?: number;
  load_ms?: number;
  memory_usage_mb?: number | null;
  profile?: string;
};

declare global {
  interface Window {
    __speakmateMediaPlayCalls?: MediaProbe[];
    __speakmateGestureDispatch?: boolean;
    __speakmateThreeMetrics?: ThreeMetric[];
  }
}

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

async function installDeterministicMedia(page: Page, hardwareConcurrency = 2) {
  await page.addInitScript((cores) => {
    type ProbedMediaElement = HTMLMediaElement & { __speakmatePaused?: boolean };
    Object.defineProperty(navigator, "hardwareConcurrency", { configurable: true, value: cores });
    Object.defineProperty(navigator, "connection", { configurable: true, value: { saveData: false } });
    window.__speakmateMediaPlayCalls = [];
    window.__speakmateThreeMetrics = [];
    const originalConsoleInfo = console.info.bind(console);
    console.info = (...values: unknown[]) => {
      if (values[0] === "speakmate_3d_metric" && values[1] && typeof values[1] === "object") {
        window.__speakmateThreeMetrics?.push(values[1] as ThreeMetric);
      }
      originalConsoleInfo(...values);
    };
    window.__speakmateGestureDispatch = false;
    document.addEventListener("click", () => {
      window.__speakmateGestureDispatch = true;
      window.setTimeout(() => {
        window.__speakmateGestureDispatch = false;
      }, 0);
    }, true);
    Object.defineProperty(HTMLMediaElement.prototype, "paused", {
      configurable: true,
      get(this: ProbedMediaElement) {
        return this.__speakmatePaused ?? true;
      },
    });
    HTMLMediaElement.prototype.play = function play(this: ProbedMediaElement) {
      this.__speakmatePaused = false;
      window.__speakmateMediaPlayCalls?.push({
        source: this.currentSrc || this.src,
        userActivation: navigator.userActivation?.isActive ?? false,
        gestureDispatch: window.__speakmateGestureDispatch ?? false,
      });
      this.dispatchEvent(new Event("play"));
      this.dispatchEvent(new Event("playing"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function pause(this: ProbedMediaElement) {
      if (this.__speakmatePaused !== false) return;
      this.__speakmatePaused = true;
      this.dispatchEvent(new Event("pause"));
    };
  }, hardwareConcurrency);
}

async function installAuthenticatedApi(page: Page) {
  let speechRequests = 0;
  await page.addInitScript(({ session, lessonTitle }) => {
    sessionStorage.setItem("speakmate.session.v1", JSON.stringify(session));
    sessionStorage.setItem("speakmate.active-lesson-title.v1", lessonTitle);
  }, { session: token, lessonTitle: "A confident morning routine" });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/speech")) {
      speechRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "audio/wav",
        headers: {
          "X-TTS-Provider": "openai",
          "X-TTS-Model": "gpt-4o-mini-tts",
          "X-TTS-Voice": "marin",
          "X-TTS-Cache": "MISS",
          "X-Request-ID": "engineering-only-request-id",
        },
        body: wavFixture(),
      });
      return;
    }

    let body: unknown = {};
    if (path.endsWith("/me")) body = account;
    else if (path === "/api/v1/tutors") body = [ananya];
    else if (path.endsWith("/preference")) {
      body = {
        learner_id: "learner-1",
        tutor: ananya,
        telugu_explanations_enabled: true,
        language_mode: "ENGLISH_TELUGU",
      };
    } else if (path.endsWith("/dashboard")) {
      body = {
        learner_id: "learner-1",
        completed_sessions: 3,
        current_streak_days: 2,
        total_practice_minutes: 8,
        preferred_tutor_id: "ananya",
        subscription_tier: "FREE",
        subscription_status: "FREE",
      };
    } else if (path.endsWith("/conversations")) {
      body = {
        id: "conversation-rc1",
        opening_prompt: openingPrompt,
        opening_turn_id: "opening-turn-rc1",
      };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  return { speechRequests: () => speechRequests };
}

async function finishCurrentAudio(page: Page) {
  await page.getByLabel("Tutor voice audio").evaluate((element) => {
    const player = element as HTMLAudioElement & { __speakmatePaused?: boolean };
    player.__speakmatePaused = true;
    player.dispatchEvent(new Event("ended"));
  });
}

async function expectHorizontalContainment(page: Page, locators: Locator[]) {
  const viewportWidth = await page.evaluate(() => window.innerWidth);
  for (const locator of locators) {
    const box = await locator.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(-1);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewportWidth + 1);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
}

test.describe("RC1 founder acceptance: live Ananya voice lesson", () => {
  test.setTimeout(240_000);

  for (const [viewportName, width, height] of [
    ["mobile", 390, 844],
    ["desktop", 1440, 900],
  ] as const) {
    test(`${viewportName} live lesson contains its actions and uses the exact-once opening path`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await installDeterministicMedia(page);
      const apiProbe = await installAuthenticatedApi(page);

      await page.goto("/app/conversation");
      expect(await page.evaluate(() => ({
        cores: navigator.hardwareConcurrency,
        saveData: (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData,
        webgl: typeof WebGLRenderingContext !== "undefined" || typeof WebGL2RenderingContext !== "undefined",
      }))).toEqual({ cores: 2, saveData: false, webgl: true });

      const experience = page.locator(".conversation-experience");
      const lesson = page.getByRole("region", { name: "Ananya live lesson" });
      const avatar = page.locator(".avatar");
      const portrait = avatar.getByRole("img", { name: /friendly Indian-English tutor/ });
      const exchange = page.getByRole("region", { name: "Current conversation" });
      const dock = page.locator(".voice-control-dock");
      const start = page.getByRole("button", { name: "Start conversation" });

      await expect(page.getByText("A confident morning routine")).toBeVisible();
      await expect(page.getByLabel("Current tutor response")).toContainText(openingPrompt, { timeout: 30_000 });
      await expect(avatar).toHaveAttribute("data-renderer", "portrait", { timeout: 30_000 });
      await expect(avatar).toHaveAttribute("data-renderer-profile", "portrait", { timeout: 30_000 });
      await expect(portrait).toBeVisible();
      await expect(portrait).toHaveAttribute("src", "/tutors/ananya.jpg");
      await expect(page.locator("canvas")).toHaveCount(0);
      if (width === 390) {
        const modeSwitchBox = await page.locator(".practice-mode-switch").boundingBox();
        const lessonContextBox = await page.locator(".lesson-context").boundingBox();
        expect(modeSwitchBox).not.toBeNull();
        expect(lessonContextBox).not.toBeNull();
        expect(modeSwitchBox!.y + modeSwitchBox!.height).toBeLessThanOrEqual(lessonContextBox!.y);
      }

      await expect(start).toBeEnabled({ timeout: 45_000 });
      expect(await page.evaluate(() => window.__speakmateMediaPlayCalls?.length ?? -1)).toBe(0);
      expect(apiProbe.speechRequests()).toBe(1);
      await start.scrollIntoViewIfNeeded();
      await start.click();

      await expect(avatar).toHaveAttribute("data-state", "SPEAKING");
      const playCalls = await page.evaluate(() => window.__speakmateMediaPlayCalls ?? []);
      expect(playCalls).toHaveLength(1);
      expect(playCalls[0].source).toMatch(/^blob:/);
      expect(playCalls[0].gestureDispatch).toBe(true);
      await expect(start).toHaveCount(0);

      await finishCurrentAudio(page);
      await expect(experience).toHaveAttribute("data-greeting-completed", "true");
      await expect(avatar).toHaveAttribute("data-state", "LISTENING");

      const microphone = page.getByRole("group", { name: "Speak to Ananya" });
      const startMicrophone = page.getByRole("button", { name: "Start microphone" });
      const stopMicrophone = page.getByRole("button", { name: "Stop and transcribe now" });
      const replay = page.getByRole("button", { name: "Replay tutor voice" });
      const mute = page.getByRole("button", { name: "Mute tutor voice" });
      await expect(microphone).toBeVisible();
      await expect(startMicrophone).toBeVisible();
      await expect(stopMicrophone).toBeVisible();
      await expect(replay).toBeVisible();
      await expect(mute).toBeVisible();
      await expect(replay).toBeEnabled();
      await expect(mute).toBeEnabled();
      await page.getByLabel(/consent to voice processing/).check();
      await expect(startMicrophone).toBeEnabled();
      await expect(stopMicrophone).toBeDisabled();

      const visibleLearnerText = await experience.innerText();
      expect(visibleLearnerText).not.toMatch(/Provider:|OpenAI|gpt-|X-TTS|Request ID|request-id|Audio duration|playback_id|diagnostic/i);
      await expect(page.locator(".conversation-history")).not.toHaveAttribute("open", "");

      const avatarBox = await avatar.boundingBox();
      const exchangeBox = await exchange.boundingBox();
      const dockBox = await dock.boundingBox();
      expect(avatarBox).not.toBeNull();
      expect(exchangeBox).not.toBeNull();
      expect(dockBox).not.toBeNull();
      expect(avatarBox!.y).toBeLessThan(exchangeBox!.y);
      expect(exchangeBox!.y).toBeLessThan(dockBox!.y);
      if (width === 390) {
        expect(avatarBox!.width).toBeGreaterThan(250);
        expect(avatarBox!.width).toBeLessThanOrEqual(390);
      } else {
        expect(avatarBox!.width).toBeGreaterThan(450);
      }
      await expectHorizontalContainment(page, [lesson, avatar, exchange, dock, microphone, replay, mute]);
      await page.screenshot({ path: `test-results/rc1-voice-${viewportName}.png`, fullPage: true });

      await page.getByRole("button", { name: "Text mode" }).click();
      await expect(page.locator(".text-conversation-history p").filter({ hasText: openingPrompt })).toHaveCount(1);
      await page.getByRole("button", { name: "Voice mode" }).click();
      expect(await page.evaluate(() => window.__speakmateMediaPlayCalls?.length ?? -1)).toBe(1);
      expect(apiProbe.speechRequests()).toBe(1);
      expect(await portrait.evaluate((image) => (image as HTMLImageElement).complete)).toBe(true);
    });
  }

  test("desktop loads the polished Ananya portrait without a WebGL dependency", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await installDeterministicMedia(page, 8);
    await installAuthenticatedApi(page);
    await page.goto("/app/conversation");
    const avatar = page.locator(".avatar");
    const portrait = avatar.getByRole("img", { name: /friendly Indian-English tutor/ });
    await expect(avatar).toHaveAttribute("data-renderer", "portrait");
    await expect(portrait).toBeVisible();
    const renderedPortrait = await avatar.screenshot({ path: "test-results/rc1-voice-portrait.png" });
    expect(renderedPortrait.byteLength).toBeGreaterThan(10_000);
    await expect(page.locator("canvas")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Start conversation" })).toBeEnabled();
  });
});
