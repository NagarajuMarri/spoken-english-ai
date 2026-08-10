import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { TutorSpeech } from "../models";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { account, ananya } from "./fixtures";

const openingSpeech: TutorSpeech = {
  blob: new Blob([new Uint8Array(96)], { type: "audio/mpeg" }),
  provider: "openai",
  model: "gpt-4o-mini-tts",
  voice: "marin",
  cacheStatus: "MISS",
  inputCharacters: 54,
  providerRequests: 1,
  usageClassification: "provider-token-usage-unavailable",
};

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn().mockReturnValue("blob:opening") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(api, "conversation").mockResolvedValue({
    id: "conversation-opening",
    opening_prompt: "Namaste! I’m Ananya. Tell me about your day.",
    opening_turn_id: "opening-turn",
  });
  vi.spyOn(api, "speech").mockResolvedValue(openingSpeech);
});

describe("opening greeting audio session", () => {
  it("uses the server greeting, speaks it once after Start, and settles into listening", async () => {
    const play = vi.mocked(HTMLMediaElement.prototype.play);
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);

    expect(await screen.findByLabelText("Current tutor response")).toHaveTextContent(
      "Namaste! I’m Ananya. Tell me about your day.",
    );
    await waitFor(() => expect(api.speech).toHaveBeenCalledWith("conversation-opening", "opening-turn"));
    expect(api.speech).toHaveBeenCalledTimes(1);
    expect(play).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Start conversation" }));
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    const player = screen.getByLabelText("Tutor voice audio");
    Object.defineProperty(player, "paused", { configurable: true, value: false });
    fireEvent.playing(player);
    expect(screen.getByLabelText(/Ananya tutor status/)).toHaveAttribute("data-state", "SPEAKING");
    fireEvent.ended(player);
    expect(screen.getByLabelText(/Ananya tutor status/)).toHaveAttribute("data-state", "LISTENING");
    expect(document.querySelector(".conversation-experience")).toHaveAttribute("data-greeting-completed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Text mode" }));
    await userEvent.click(screen.getByRole("button", { name: "Voice mode" }));
    expect(api.speech).toHaveBeenCalledTimes(1);
    expect(play).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Replay tutor voice" }));
    expect(play).toHaveBeenCalledTimes(2);
    expect(api.speech).toHaveBeenCalledTimes(1);
  });

  it("keeps one clean Start action available when the browser rejects playback", async () => {
    vi.mocked(HTMLMediaElement.prototype.play)
      .mockRejectedValueOnce(new DOMException("Gesture required", "NotAllowedError"))
      .mockResolvedValueOnce(undefined);
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);
    await waitFor(() => expect(api.speech).toHaveBeenCalledTimes(1));
    const start = screen.getByRole("button", { name: "Start conversation" });
    await userEvent.click(start);
    expect(start).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Select Start conversation to try again");
    await userEvent.click(start);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Start conversation" })).not.toBeInTheDocument());
    expect(api.speech).toHaveBeenCalledTimes(1);
  });

  it("guards rapid Start clicks so the opening playback is requested once", async () => {
    let resolvePlayback: (() => void) | undefined;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementation(() => new Promise<void>((resolve) => {
      resolvePlayback = resolve;
    }));
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);
    await waitFor(() => expect(api.speech).toHaveBeenCalledTimes(1));
    const start = screen.getByRole("button", { name: "Start conversation" });
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    fireEvent.click(start);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    resolvePlayback?.();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Start conversation" })).not.toBeInTheDocument());
  });

  it("reuses one conversation request under React StrictMode effect replay", async () => {
    render(
      <StrictMode>
        <RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(api.speech).toHaveBeenCalledTimes(1));
    expect(api.conversation).toHaveBeenCalledTimes(1);
  });

  it("offers an honest text-capable escape when opening TTS remains unavailable", async () => {
    vi.mocked(api.speech).mockRejectedValue(new Error("Tutor voice is temporarily unavailable."));
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH" /></RouterProvider>);
    await waitFor(
      () => expect(screen.getByRole("alert")).toHaveTextContent("temporarily unavailable"),
      { timeout: 5_000 },
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue without audio" }));
    expect(screen.queryByRole("button", { name: "Start conversation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text mode" })).toBeEnabled();
  });
});
