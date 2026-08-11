import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_LATENCY_DISTRIBUTION, "requires isolated configured OpenAI providers");
test.setTimeout(1_800_000);

const cases = [
  ...["My day is going well.", "I drank tea this morning.", "I enjoy learning English.", "I work on a learning app.", "I live in Hyderabad.", "Today is a busy day.", "I like reading the news.", "My brother works nearby.", "I practise every evening.", "I feel confident today."].map((message) => ({ kind: "english", message })),
  ...["Please explain this sentence in Telugu: I have finished my work.", "ఈ sentence అర్థం తెలుగులో చెప్పండి: I am ready.", "Explain present tense in simple Telugu.", "Why do we use 'for' here? Explain in Telugu.", "ఈ English sentence ని తెలుగులో explain చేయండి: She is cooking.", "Tell me in Telugu when to use 'since'.", "ఈ sentence correct ఆ? I went home yesterday.", "Explain 'How much is this?' in Telugu.", "తెలుగులో చిన్న explanation ఇవ్వండి: I can swim.", "Explain the word confidence in Telugu."].map((message) => ({ kind: "telugu_assisted", message })),
  ...["She don't like coffee.", "I go to office yesterday.", "He have two cars.", "I am living here since five years.", "They was happy yesterday."].map((message) => ({ kind: "grammar", message })),
  ...["నేను Hyderabad వెళ్లాలని అనుకుంటున్నాను. How do I say it naturally?", "దీని ధర ఎంత? Give me the English sentence.", "Today నేను office కి late గా వెళ్లాను.", "Market లో price ఎలా అడగాలి?", "I finished my పని. Is this sentence okay?"].map((message) => ({ kind: "mixed", message })),
];

test("30-turn live latency distribution has no silent or duplicate turns", async ({ request }) => {
  await assertSafeLiveTarget(request);
  const invitationCode = process.env.LIVE_REGISTRATION_INVITE;
  if (!invitationCode) throw new Error("LIVE_REGISTRATION_INVITE is required");
  const email = `latency-${Date.now()}@example.com`;
  const registration = await request.post("/api/v1/auth/register", { data: {
    display_name: "Latency Distribution",
    email,
    password: "StrongPassword123!",
    invitation_code: invitationCode,
    terms_privacy_accepted: true,
  } });
  expect(registration.status()).toBe(201);
  const registered = await registration.json() as { tokens: { access_token: string } };
  const headers = { Authorization: `Bearer ${registered.tokens.access_token}` };
  const me = await request.get("/api/v1/auth/me", { headers });
  expect(me.ok()).toBe(true);
  const account = await me.json() as { learner_id: string };
  const preference = await request.put("/api/v1/tutors/preference", {
    headers,
    data: { tutor_id: "ananya", language_mode: "ENGLISH_TELUGU" },
  });
  expect(preference.ok()).toBe(true);
  const conversationResponse = await request.post("/api/v1/conversations", {
    headers,
    data: { learner_id: account.learner_id, scenario_id: "daily-conversation" },
  });
  expect(conversationResponse.status()).toBe(201);
  const conversation = await conversationResponse.json() as { id: string };
  const results: Array<Record<string, unknown>> = [];
  const turnIds = new Set<string>();
  for (const [index, item] of cases.entries()) {
    const turnStarted = Date.now();
    const turnUrl = `/api/v1/conversations/${conversation.id}/ai-turns`;
    const turnOptions = {
      headers: { ...headers, "Idempotency-Key": `live-distribution-${index}` },
      data: { message: item.message },
      timeout: 120_000,
    };
    let turn = await request.post(turnUrl, turnOptions);
    const initialStatus = turn.status();
    if (initialStatus !== 200) turn = await request.post(turnUrl, turnOptions);
    const turnMs = Date.now() - turnStarted;
    expect(turn.status(), `turn ${index + 1}`).toBe(200);
    const body = await turn.json() as { turn_id: string; spoken_text?: string; language_review_status?: string };
    expect(body.spoken_text?.trim(), `silent turn ${index + 1}`).toBeTruthy();
    expect(turnIds.has(body.turn_id), `duplicate turn ${index + 1}`).toBe(false);
    turnIds.add(body.turn_id);
    const speechStarted = Date.now();
    const speech = await request.post(`/api/v1/conversations/${conversation.id}/ai-turns/${body.turn_id}/speech`, {
      headers,
      timeout: 120_000,
    });
    const speechMs = Date.now() - speechStarted;
    expect(speech.status(), `speech ${index + 1}`).toBe(200);
    results.push({
      kind: item.kind,
      turn_ms: turnMs,
      speech_ms: speechMs,
      total_ms: turnMs + speechMs,
      turn_server_timing: turn.headers()["server-timing"] ?? "",
      speech_server_timing: speech.headers()["server-timing"] ?? "",
      language_review_status: body.language_review_status,
      initial_status: initialStatus,
    });
  }
  expect(turnIds.size).toBe(30);
  console.log("LIVE_LATENCY_DISTRIBUTION", JSON.stringify(results));
});
