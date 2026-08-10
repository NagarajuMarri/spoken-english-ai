import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { selectTutorRenderTier, useTutorRendererFallback } from "../multimedia";

function RendererHarness({
  enabled,
  onReady,
}: {
  enabled: boolean;
  onReady: (profile: "model" | "lite" | "portrait", initializationMs: number) => void;
}) {
  const renderer = useTutorRendererFallback({ threeDimensionsEnabled: enabled, onReady });
  return <>
    <output aria-label="Renderer">{renderer.renderer}</output>
    <output aria-label="Renderer profile">{renderer.profile}</output>
    <button onClick={() => renderer.rendererReady(25, "lite")}>Lite ready</button>
    <button onClick={() => renderer.rendererReady(80, "model")}>Model ready</button>
    <button onClick={renderer.rendererUnavailable}>Renderer failed</button>
  </>;
}

describe("multimedia device and renderer fallback controller", () => {
  it("selects full, lightweight, and static tiers without coupling to an avatar asset", () => {
    expect(selectTutorRenderTier("ananya", { hardwareConcurrency: 8 }, true)).toBe("FULL_3D");
    expect(selectTutorRenderTier("ananya", { hardwareConcurrency: 2 }, true)).toBe("LIGHTWEIGHT_3D");
    expect(selectTutorRenderTier("ananya", { hardwareConcurrency: 8, connection: { saveData: true } }, true))
      .toBe("LIGHTWEIGHT_3D");
    expect(selectTutorRenderTier("ananya", { hardwareConcurrency: 8 }, false)).toBe("STATIC_FALLBACK");
    expect(selectTutorRenderTier("another-tutor", { hardwareConcurrency: 8 }, true)).toBe("STATIC_FALLBACK");
  });

  it("owns the model to lite to portrait production fallback state", async () => {
    const onReady = vi.fn();
    render(<RendererHarness enabled onReady={onReady} />);
    expect(screen.getByLabelText("Renderer")).toHaveTextContent("loading");

    fireEvent.click(screen.getByRole("button", { name: "Lite ready" }));
    expect(screen.getByLabelText("Renderer")).toHaveTextContent("three");
    expect(screen.getByLabelText("Renderer profile")).toHaveTextContent("lite");
    expect(onReady).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "Model ready" }));
    expect(screen.getByLabelText("Renderer profile")).toHaveTextContent("model");
    expect(onReady).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "Renderer failed" }));
    expect(screen.getByLabelText("Renderer")).toHaveTextContent("portrait");
    expect(screen.getByLabelText("Renderer profile")).toHaveTextContent("portrait");
  });

  it("reports static fallback readiness without attempting WebGL", async () => {
    const onReady = vi.fn();
    render(<RendererHarness enabled={false} onReady={onReady} />);
    expect(screen.getByLabelText("Renderer")).toHaveTextContent("portrait");
    await waitFor(() => expect(onReady).toHaveBeenCalledWith("portrait", 0));
  });

  it("keeps a fatal renderer failure terminal even if a late model load reports ready", () => {
    const onReady = vi.fn();
    render(<RendererHarness enabled onReady={onReady} />);

    fireEvent.click(screen.getByRole("button", { name: "Lite ready" }));
    fireEvent.click(screen.getByRole("button", { name: "Renderer failed" }));
    fireEvent.click(screen.getByRole("button", { name: "Model ready" }));

    expect(screen.getByLabelText("Renderer")).toHaveTextContent("portrait");
    expect(screen.getByLabelText("Renderer profile")).toHaveTextContent("portrait");
    expect(onReady).toHaveBeenCalledOnce();
  });
});
