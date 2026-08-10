import { expect, test, type Page, type Route } from "@playwright/test";

const token = { access_token: "acceptance", refresh_token: "acceptance-refresh-token-long-enough", token_type: "bearer", expires_in: 900 };
const account = { id: "user-final", learner_id: "learner-final", email: "final@example.invalid", status: "ACTIVE" };
const tutor = { tutor_id: "ananya", display_name: "Ananya", gender: "female", avatar_profile: "/tutors/ananya.jpg", voice_profile: "indian-english-ananya", accent: "Indian English", teaching_style: "patient and encouraging", animation_profile: "animated-2d", prompt_profile: "supportive", vocabulary_profile: "practical", enabled: true };

const turns = [
  "Yeah, hi Ananya. My day is good.",
  "I work mostly on developing this spoken English learning app from morning.",
  "I have been working on it since this morning.",
  "What do you like to do in the morning?",
  "I usually drink tea and read the news.",
  "నాకు explanation తెలుగులో కావాలి.",
  "Can you give me a short example?",
  "Yesterday I went to the market.",
  "She don't like coffee.",
  "She doesn't like coffee.",
  "Let's talk about travel now.",
  "I want to visit Hyderabad next month.",
  "Market లో price ఎలా అడగాలి?",
  "How much is this?",
  "It costs five hundred rupees.",
  "Please explain that in English.",
  "I am happy with this practice.",
  "Hey Ananya, why are you not responding?",
  "My brother has two cars.",
  "Thank you. What should I practise next?",
];

function wavFixture() {
  const bytes = Buffer.alloc(44 + 8000);
  bytes.write("RIFF", 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(8000, 24); bytes.writeUInt32LE(16000, 28); bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34); bytes.write("data", 36); bytes.writeUInt32LE(8000, 40);
  return bytes;
}

async function installMedia(page: Page) {
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = function play() {
      this.dispatchEvent(new Event("playing"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function pause() { this.dispatchEvent(new Event("pause")); };
  });
}

test("20-turn end-user loop has exact-once messages and recoverable tutor failure", async ({ page }) => {
  test.setTimeout(600_000);
  await installMedia(page);
  await page.addInitScript((session) => sessionStorage.setItem("speakmate.session.v1", JSON.stringify(session)), token);
  const keysByMessage = new Map<string, Set<string>>();
  const callsByMessage = new Map<string, number>();

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/speech")) {
      await route.fulfill({ status: 200, contentType: "audio/wav", body: wavFixture() });
      return;
    }
    if (path.endsWith("/ai-turns")) {
      const message = String((request.postDataJSON() as { message?: string }).message ?? "");
      const key = request.headers()["idempotency-key"] ?? "";
      keysByMessage.set(message, (keysByMessage.get(message) ?? new Set()).add(key));
      const call = (callsByMessage.get(message) ?? 0) + 1;
      callsByMessage.set(message, call);
      if (message === turns[17] && call === 1) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "llm_connection_error", message: "Ananya couldn't respond just now. Tap Retry.", retryable: true } }) });
        return;
      }
      const validFounderSentence = message === turns[0];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        turn_id: `turn-${turns.indexOf(message)}`,
        tutor_message: validFounderSentence ? "That's correct. My day is going well is only an optional alternative." : `I understood turn ${turns.indexOf(message) + 1}.`,
        next_question: "What would you like to say next?",
        correction_type: validFounderSentence ? "VALID_SENTENCE" : "VALID_SENTENCE",
        corrected_sentence: null,
        correction_explanation: null,
        vocabulary_suggestions: [],
        spoken_text: validFounderSentence ? "That's correct. What did you do this morning?" : `I understood turn ${turns.indexOf(message) + 1}. What would you like to say next?`,
        coaching_mode: "NO_CORRECTION",
        coaching_state: "NORMAL_CONVERSATION",
        expression_hint: "ENCOURAGING",
      }) });
      return;
    }
    let body: unknown = {};
    if (path.endsWith("/me")) body = account;
    else if (path === "/api/v1/tutors") body = [tutor];
    else if (path.endsWith("/preference")) body = { learner_id: account.learner_id, tutor, telugu_explanations_enabled: true, language_mode: "ENGLISH_TELUGU" };
    else if (path.endsWith("/dashboard")) body = { learner_id: account.learner_id, completed_sessions: 0, current_streak_days: 0, total_practice_minutes: 0, preferred_tutor_id: "ananya", subscription_tier: "FREE", subscription_status: "FREE" };
    else if (path.endsWith("/conversations")) body = { id: "conversation-final", opening_prompt: "Hello! How has your day been so far?", opening_turn_id: "opening-final" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.goto("/app/conversation");
  await expect(page.getByRole("button", { name: "Start conversation" })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.getByRole("button", { name: "Text mode" }).click();

  for (const message of turns) {
    await page.getByLabel("Your message").fill(message);
    await page.getByRole("button", { name: "Send" }).click();
    if (message === turns[17]) {
      await expect(page.getByRole("alert")).toContainText("Tap Retry");
      await expect(page.locator(".text-conversation-history p").filter({ hasText: message })).toHaveCount(1);
      await page.getByRole("button", { name: "Retry tutor response" }).click();
    }
    const expectedTutor = message === turns[0]
      ? "That's correct. What did you do this morning?"
      : `I understood turn ${turns.indexOf(message) + 1}. What would you like to say next?`;
    await expect(page.locator(".text-conversation-history p").filter({ hasText: expectedTutor })).toHaveCount(1);
    await expect(page.locator(".text-conversation-history p").filter({ hasText: message })).toHaveCount(1);
  }

  expect(callsByMessage.get(turns[17])).toBe(2);
  expect(keysByMessage.get(turns[17])?.size).toBe(1);
  expect([...keysByMessage.values()].every((keys) => keys.size === 1)).toBe(true);
  expect(callsByMessage.size).toBe(20);
  await expect(page.getByText(/Correct form:/)).toHaveCount(0);
});
