import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { account, ananya } from "./fixtures";

let play: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sessionStorage.clear();
  play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn().mockReturnValue("blob:voice-mode") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
  vi.spyOn(api, "conversation").mockResolvedValue({ id: "conversation-defect-10" });
  vi.spyOn(api, "turn").mockResolvedValue({
    turn_id: "turn-defect-10",
    tutor_message: "Good try.",
    next_question: "What did you do next?",
    incorrect_span: "go",
    corrected_form: "went",
    correction_explanation: "Use the past tense: went.",
    telugu_explanation: "గత కాలంలో went అని చెప్పండి.",
    vocabulary_suggestions: ["afterwards"],
    review_changed: true,
    review_reason_code: "INTERNAL_REVIEW_SENTINEL",
  });
  vi.spyOn(api, "speech").mockResolvedValue({
    blob: new Blob([new Uint8Array(64)], { type: "audio/mpeg" }),
    provider: "PROVIDER_SENTINEL",
    model: "MODEL_SENTINEL",
    voice: "VOICE_SENTINEL",
    cacheStatus: "CACHE_SENTINEL",
    inputCharacters: 123,
    providerRequests: 7,
    usageClassification: "USAGE_SENTINEL",
  });
});

async function completeCorrectiveTurn() {
  await waitFor(() => expect(api.conversation).toHaveBeenCalledOnce());
  await userEvent.click(screen.getByText("Type instead"));
  fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "I go yesterday." } });
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByLabelText("Current tutor response");
}

describe("RC1 Defect 10 focused voice mode", () => {
  it("hides engineering metadata while keeping the essential live lesson visible", async () => {
    sessionStorage.setItem("speakmate.active-lesson-title.v1", "A confident morning routine");
    const { container } = render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH_TELUGU" /></RouterProvider>);
    await completeCorrectiveTurn();

    expect(screen.getByRole("group", { name: "Practice mode" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Voice mode" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Ananya live lesson" })).toBeVisible();
    expect(screen.getByText("A confident morning routine")).toBeVisible();
    expect(screen.getByLabelText("Latest learner message")).toHaveTextContent("I go yesterday.");
    expect(screen.getByLabelText("Current tutor response")).toHaveTextContent("Good try. What did you do next?");
    expect(screen.getByLabelText("Current grammar correction")).toHaveTextContent("went");
    expect(screen.getByLabelText("Telugu explanation")).toHaveTextContent("గత కాలంలో went అని చెప్పండి.");
    expect(screen.getByRole("button", { name: "Start microphone" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Replay tutor voice" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Stop tutor voice" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Mute tutor voice" })).toBeVisible();

    for (const diagnostic of [
      /PROVIDER_SENTINEL/,
      /MODEL_SENTINEL/,
      /VOICE_SENTINEL/,
      /CACHE_SENTINEL/,
      /USAGE_SENTINEL/,
      /INTERNAL_REVIEW_SENTINEL/,
      /Audio path/i,
      /Browser permission/i,
      /playback id/i,
    ]) {
      expect(screen.queryByText(diagnostic)).not.toBeInTheDocument();
    }
    expect(container.querySelector(".avatar-sync-evidence")).not.toBeInTheDocument();
    expect(container.querySelector(".conversation-history")).not.toHaveAttribute("open");
  }, 20_000);

  it("preserves one conversation and one audio source across Voice and Text mode switches", async () => {
    sessionStorage.setItem("speakmate.active-lesson-title.v1", "A confident morning routine");
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH_TELUGU" /></RouterProvider>);
    await completeCorrectiveTurn();
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    expect(screen.getByText("A confident morning routine")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Text mode" }));
    const textHistory = screen.getByLabelText("Conversation history");
    expect(textHistory.querySelectorAll("p")).toHaveLength(3);
    expect(textHistory).toHaveTextContent("I go yesterday.");
    expect(textHistory).toHaveTextContent("Good try. What did you do next?");
    expect(screen.getByLabelText("Live coaching")).toHaveTextContent("went");
    expect(screen.getByText("A confident morning routine")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Voice mode" }));
    expect(screen.getAllByText("I go yesterday.")).toHaveLength(1);
    expect(screen.getAllByText("Good try. What did you do next?")).toHaveLength(1);
    expect(screen.getByLabelText("Current grammar correction")).toHaveTextContent("went");
    expect(screen.getByText("A confident morning routine")).toBeVisible();
    expect(api.conversation).toHaveBeenCalledTimes(1);
    expect(api.turn).toHaveBeenCalledTimes(1);
    expect(api.speech).toHaveBeenCalledTimes(1);
    expect(play).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Replay tutor voice" }));
    expect(play).toHaveBeenCalledTimes(2);
    expect(api.speech).toHaveBeenCalledTimes(1);
  });

  it("provides accessible labels without serious voice-screen violations", async () => {
    const { container } = render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);
    await waitFor(() => expect(api.conversation).toHaveBeenCalledOnce());
    expect(screen.getByRole("group", { name: "Practice mode" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Speak to Ananya" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Tutor voice controls" })).toBeVisible();
    expect(screen.queryByLabelText("Live coaching")).not.toBeInTheDocument();
    const result = await axe.run(container);
    expect(result.violations.filter((item) => item.impact === "critical" || item.impact === "serious")).toEqual([]);
  });
});
