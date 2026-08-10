import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { SubscriptionScreen } from "../screens/LaunchScreens";

afterEach(() => vi.restoreAllMocks());

describe("launch subscription presentation", () => {
  it("describes test upgrade as a preview without claiming a persisted subscription", async () => {
    vi.spyOn(api, "subscription").mockResolvedValue({
      plan_id: "FREE",
      status: "FREE",
      trial_remaining_days: 0,
      payment_mode: "test",
      entitlements: { daily_conversations: 5, voice_minutes: 5 },
      fair_use: "Limits are enforced by the server.",
    });
    vi.spyOn(api, "requestUpgrade").mockResolvedValue({
      status: "UPGRADE_PREVIEW",
      payment_mode: "test",
      real_charge: false,
    });

    render(<SubscriptionScreen />);
    await screen.findByRole("heading", { name: "FREE" });
    await userEvent.click(screen.getByRole("button", { name: "Test upgrade" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Test-mode upgrade preview opened. No subscription or charge was created.",
    );
    expect(screen.queryByText(/upgrade recorded/i)).not.toBeInTheDocument();
  });

  it("keeps a failed upgrade preview recoverable", async () => {
    vi.spyOn(api, "subscription").mockResolvedValue({
      plan_id: "FREE",
      status: "FREE",
      trial_remaining_days: 0,
      payment_mode: "test",
      entitlements: { daily_conversations: 5, voice_minutes: 5 },
      fair_use: "Limits are enforced by the server.",
    });
    vi.spyOn(api, "requestUpgrade").mockRejectedValue(new Error("Upgrade preview is temporarily unavailable."));

    render(<SubscriptionScreen />);
    await screen.findByRole("heading", { name: "FREE" });
    await userEvent.click(screen.getByRole("button", { name: "Test upgrade" }));

    expect(screen.getByRole("status")).toHaveTextContent("Upgrade preview is temporarily unavailable.");
    expect(screen.getByRole("button", { name: "Test upgrade" })).toBeEnabled();
  });
});
