import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { SubscriptionView } from "../models";
import { SubscriptionScreen } from "../screens/LaunchScreens";

const subscription = (overrides:Partial<SubscriptionView>={}):SubscriptionView => ({
  plan_id:"FREE",plan_name:"Free",status:"FREE",trial_remaining_days:0,payment_mode:"test" as const,
  started_at:null,current_period_end:null,
  entitlements:{daily_conversations:5,voice_minutes:5,progress_history:true,conversation_history:false},
  active_features:["AI tutor conversations","40 structured English lessons","Progress and practice history"],
  available_plans:[
    {code:"FREE",name:"Free",price_inr:0,billing_period:"No charge",features:["5 AI tutor conversations each day"]},
    {code:"PREMIUM_MONTHLY",name:"Premium Monthly",price_inr:299,billing_period:"per month",features:["120 voice minutes each day"]},
    {code:"PREMIUM_YEARLY",name:"Premium Yearly",price_inr:2999,billing_period:"per year",features:["Everything in Premium Monthly"]},
  ],
  can_start_trial:true,can_preview_upgrade:true,
  payment_notice:"Closed-beta payment preview only. No real subscription or charge will be created.",
  fair_use:"Limits are enforced by the server.",...overrides,
});

afterEach(() => vi.restoreAllMocks());

describe("launch subscription presentation", () => {
  it("describes test upgrade as a preview without claiming a persisted subscription", async () => {
    vi.spyOn(api, "subscription").mockResolvedValue(subscription());
    vi.spyOn(api, "requestUpgrade").mockResolvedValue({
      status: "UPGRADE_PREVIEW",
      payment_mode: "test",
      real_charge: false,
    });

    render(<SubscriptionScreen />);
    await screen.findByRole("heading", { name: "Free", level: 2 });
    await userEvent.click(screen.getByRole("button", { name: "Preview Premium Monthly" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Premium preview opened in test mode. No subscription or charge was created.",
    );
    expect(screen.queryByText(/upgrade recorded/i)).not.toBeInTheDocument();
  });

  it("keeps a failed upgrade preview recoverable", async () => {
    vi.spyOn(api, "subscription").mockResolvedValue(subscription());
    vi.spyOn(api, "requestUpgrade").mockRejectedValue(new Error("Upgrade preview is temporarily unavailable."));

    render(<SubscriptionScreen />);
    await screen.findByRole("heading", { name: "Free", level: 2 });
    await userEvent.click(screen.getByRole("button", { name: "Preview Premium Monthly" }));

    expect(screen.getByRole("status")).toHaveTextContent("premium preview is temporarily unavailable");
    expect(screen.getByRole("button", { name: "Preview Premium Monthly" })).toBeEnabled();
  });

  it("shows active subscriber status, dates, and prevents a second trial", async()=>{
    vi.spyOn(api,"subscription").mockResolvedValue(subscription({
      plan_id:"PREMIUM_MONTHLY",plan_name:"Premium Monthly",status:"ACTIVE",can_start_trial:false,
      started_at:"2026-08-01T00:00:00Z",current_period_end:"2026-09-01T00:00:00Z",
      entitlements:{daily_conversations:200,voice_minutes:120,progress_history:true,conversation_history:true},
    }));
    render(<SubscriptionScreen/>);
    expect(await screen.findByRole("heading",{name:"Premium Monthly",level:2})).toBeVisible();
    expect(screen.getByText("ACTIVE")).toBeVisible();
    expect(screen.queryByRole("button",{name:/Start 7-day/})).not.toBeInTheDocument();
    expect(screen.getByText("200 conversations")).toBeVisible();
  });

  it("renders a safe recoverable load failure",async()=>{
    vi.spyOn(api,"subscription").mockRejectedValue(new Error("raw provider detail"));
    render(<SubscriptionScreen/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    expect(screen.queryByText("raw provider detail")).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Retry subscription details"})).toBeEnabled();
  });
});
