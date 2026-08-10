import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSpeakMateMultimediaRuntime, type LipSyncProvider } from "../multimedia";

function BridgeHarness({
  reducedMotion = false,
  lipSyncProvider,
}: {
  reducedMotion?: boolean;
  lipSyncProvider?: LipSyncProvider;
}) {
  const multimedia = useSpeakMateMultimediaRuntime(reducedMotion, {
    createLipSyncProvider: lipSyncProvider ? () => lipSyncProvider : undefined,
  });
  return <>
    <output aria-label="Tutor state">{multimedia.presentation.state}</output>
    <output aria-label="Tutor mouth">{multimedia.presentation.mouth}</output>
    <output aria-label="Playback identity">{multimedia.playbackSignal.current.playbackId}</output>
    <button onClick={() => multimedia.dispatchAudioLifecycle({ type: "SOURCE_READY", playbackId: "bridge-turn" })}>Source</button>
    <button onClick={() => multimedia.dispatchAudioLifecycle({ type: "PLAYBACK_STARTED", playbackId: "bridge-turn" })}>Play</button>
    <button onClick={() => multimedia.dispatchAudioLifecycle({
      type: "PLAYBACK_FRAME",
      playbackId: "bridge-turn",
      currentTimeMs: 120,
      durationMs: 900,
      amplitude: 0.24,
    })}>Frame</button>
  </>;
}

describe("React multimedia runtime bridge", () => {
  it("publishes semantic audio lifecycle state and playback evidence to React", async () => {
    render(<BridgeHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: "Frame" }));

    await waitFor(() => expect(screen.getByLabelText("Tutor state")).toHaveTextContent("SPEAKING"));
    expect(screen.getByLabelText("Tutor mouth")).toHaveTextContent("WIDE");
    expect(screen.getByLabelText("Playback identity")).toHaveTextContent("bridge-turn");
  });

  it("reacts to reduced-motion preference changes without replacing conversation state", async () => {
    const view = render(<BridgeHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: "Frame" }));
    await waitFor(() => expect(screen.getByLabelText("Tutor mouth")).toHaveTextContent("WIDE"));

    view.rerender(<BridgeHarness reducedMotion />);

    await waitFor(() => expect(screen.getByLabelText("Tutor mouth")).toHaveTextContent("REST"));
    expect(screen.getByLabelText("Tutor state")).toHaveTextContent("SPEAKING");
    expect(screen.getByLabelText("Playback identity")).toHaveTextContent("bridge-turn");
  });

  it("publishes the selected replaceable provider pose instead of remapping amplitude", async () => {
    const provider: LipSyncProvider = {
      id: "test-viseme-provider",
      reset: () => undefined,
      sample: () => ({ mouth: "SMALL", confidence: 0.98, source: "PROVIDER_VISEME" }),
    };
    render(<BridgeHarness lipSyncProvider={provider} />);
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: "Frame" }));

    await waitFor(() => expect(screen.getByLabelText("Tutor mouth")).toHaveTextContent("SMALL"));
    expect(screen.getByLabelText("Playback identity")).toHaveTextContent("bridge-turn");
  });
});
