import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { SettingsScreen } from "../screens/ExperienceScreens";
import { ananya, dashboard } from "./fixtures";

describe("settings subscription summary", () => {
  it("shows the current dashboard plan and status", () => {
    render(
      <AuthProvider>
        <SettingsScreen
          data={{
            ...dashboard,
            subscription_tier: "PREMIUM_MONTHLY",
            subscription_status: "TRIAL",
          }}
          tutor={ananya}
          onChange={() => undefined}
        />
      </AuthProvider>,
    );

    expect(screen.getByText(/PREMIUM MONTHLY · TRIAL/)).toBeVisible();
    expect(screen.queryByText(/provider integration ready/i)).not.toBeInTheDocument();
  });
});
