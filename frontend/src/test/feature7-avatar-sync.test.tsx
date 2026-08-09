import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialTutorPresentation } from "../avatar/machine";
import { api } from "../api/client";
import { Avatar } from "../components/Avatar";
import type { TutorSpeech } from "../models";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { TutorAudioPlayer, type AudioLifecycleEvent } from "../voice/TutorAudioPlayer";
import { account, ananya } from "./fixtures";

const speech: TutorSpeech = {
  blob: new Blob([new Uint8Array(64)], { type: "audio/mpeg" }),
  provider: "openai",
  model: "gpt-4o-mini-tts",
  voice: "marin",
  cacheStatus: "MISS",
  inputCharacters: 70,
  providerRequests: 1,
  usageClassification: "provider-token-usage-unavailable",
};

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  vi.spyOn(window, "requestAnimationFrame").mockReturnValue(7);
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn().mockReturnValue("blob:feature-7") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

describe("Feature 7 audio-linked avatar", () => {
  it("emits speaking frames from the real audio element lifecycle", async () => {
    const events: AudioLifecycleEvent[] = [];
    render(<TutorAudioPlayer speech={speech} spokenText="Good work." playbackId="turn-7" onLifecycle={(event) => events.push(event)} />);
    await waitFor(() => expect(events).toContainEqual({ type: "SOURCE_READY", playbackId: "turn-7" }));
    const player = screen.getByLabelText(/Tutor audio for/);
    Object.defineProperty(player, "paused", { configurable: true, value: false });
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0.24 });
    Object.defineProperty(player, "duration", { configurable: true, value: 2 });
    fireEvent.play(player);
    expect(events).toContainEqual({ type: "PLAYBACK_STARTED", playbackId: "turn-7" });
    expect(events).toContainEqual({ type: "PLAYBACK_FRAME", playbackId: "turn-7", currentTimeMs: 240, durationMs: 2000 });
    fireEvent.pause(player);
    expect(events).toContainEqual({ type: "PLAYBACK_PAUSED", playbackId: "turn-7" });
  });

  it.each(["POSITIVE", "ENCOURAGING", "CORRECTIVE"] as const)("renders the %s expression through the neutral renderer contract", (expression) => {
    const presentation = { ...initialTutorPresentation, state: "SPEAKING" as const, expression, mouth: "MEDIUM" as const };
    const { getByLabelText } = render(<Avatar tutor={ananya} presentation={presentation} />);
    const avatar = getByLabelText(new RegExp(`expression: ${expression.toLowerCase()}`));
    expect(avatar).toHaveAttribute("data-expression", expression);
    expect(avatar).toHaveClass(`expression-${expression.toLowerCase()}`);
    expect(avatar).toHaveAttribute("data-mouth", "MEDIUM");
  });

  it("ties visible corrective speech and mouth movement to playback start and end", async () => {
    vi.spyOn(api, "conversation").mockResolvedValue({ id: "conversation-feature-7" });
    vi.spyOn(api, "turn").mockResolvedValue({
      turn_id: "turn-feature-7",
      tutor_message: "Good try. Use the past tense.",
      next_question: "Can you say it again?",
      correction_explanation: "Use went instead of go.",
      vocabulary_suggestions: [],
      expression_hint: "CORRECTIVE",
    });
    vi.spyOn(api, "speech")
      .mockResolvedValueOnce(speech)
      .mockResolvedValueOnce({ ...speech, blob: new Blob([new Uint8Array(96)], { type: "audio/mpeg" }) });
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);
    await waitFor(() => expect(api.conversation).toHaveBeenCalled());
    await userEvent.type(screen.getByLabelText("Your message"), "I go yesterday.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const player = await screen.findByLabelText(/Tutor audio for/);
    const avatar = screen.getByLabelText(/Ananya tutor status/);
    expect(avatar).toHaveAttribute("data-state", "THINKING");
    expect(avatar).toHaveAttribute("data-mouth", "REST");

    Object.defineProperty(player, "paused", { configurable: true, value: false });
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0.24 });
    Object.defineProperty(player, "duration", { configurable: true, value: 1.5 });
    fireEvent.play(player);
    expect(avatar).toHaveAttribute("data-state", "SPEAKING");
    expect(avatar).toHaveAttribute("data-expression", "CORRECTIVE");
    expect(avatar).toHaveAttribute("data-mouth", "WIDE");

    fireEvent.ended(player);
    expect(avatar).toHaveAttribute("data-state", "IDLE");
    expect(avatar).toHaveAttribute("data-mouth", "REST");

    await userEvent.click(screen.getByRole("button", { name: "Replay" }));
    fireEvent.play(player);
    expect(avatar).toHaveAttribute("data-state", "SPEAKING");
    expect(avatar).toHaveAttribute("data-mouth", "SMALL");

    fireEvent.error(player);
    expect(avatar).toHaveAttribute("data-state", "ERROR");
    expect(avatar).toHaveAttribute("data-mouth", "REST");
    expect(screen.getByRole("alert")).toHaveTextContent("Tutor audio could not be played");
    await userEvent.click(screen.getByRole("button", { name: "Retry OpenAI voice" }));
    await waitFor(() => expect(api.speech).toHaveBeenCalledTimes(2));
    fireEvent.play(player);
    expect(avatar).toHaveAttribute("data-state", "SPEAKING");
    expect(avatar).toHaveAttribute("data-mouth", "SMALL");
  });

  it("interrupts playback and resets the mouth immediately", async () => {
    const events: AudioLifecycleEvent[] = [];
    render(<TutorAudioPlayer speech={speech} spokenText="Keep going." playbackId="turn-stop" onLifecycle={(event) => events.push(event)} />);
    await waitFor(() => expect(events.some((event) => event.type === "SOURCE_READY")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(events).toContainEqual({ type: "PLAYBACK_STOPPED", playbackId: "turn-stop" });
  });
});
