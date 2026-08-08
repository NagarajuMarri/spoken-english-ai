import { render } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { initialTutorPresentation } from "../avatar/machine";
import { Avatar } from "../components/Avatar";
import { ananya } from "./fixtures";

describe("accessibility", () => {
  it("has no critical avatar violations", async () => {
    const { container } = render(<main><h1>Tutor status</h1><Avatar tutor={ananya} presentation={initialTutorPresentation} /></main>);
    const result = await axe.run(container);
    expect(result.violations.filter((item) => item.impact === "critical" || item.impact === "serious")).toEqual([]);
  });

  it("exposes reduced-motion state while keeping the mouth static", () => {
    const speaking = { ...initialTutorPresentation, state: "SPEAKING" as const, mouth: "WIDE" as const };
    const { getByLabelText } = render(<Avatar tutor={ananya} presentation={speaking} reducedMotion />);
    const avatar = getByLabelText(/status: speaking/);
    expect(avatar).toHaveClass("reduced-motion");
    expect(avatar).toHaveAttribute("data-mouth", "REST");
  });
});
