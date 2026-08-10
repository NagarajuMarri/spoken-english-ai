import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { AuthProvider, useAuth } from "../auth/AuthProvider";
import { sessionStore } from "../auth/session-store";
import { account, tokens } from "./fixtures";

function Harness() {
  const { status, login, logout, logoutAll } = useAuth();
  return <main>
    <p>Session: {status}</p>
    <button onClick={() => void logout()}>End current session</button>
    <button onClick={() => void logoutAll()}>End all sessions</button>
    <button onClick={() => void login("account-b@example.invalid", "StrongPassword123!")}>Switch account</button>
  </main>;
}

describe("authentication session races", () => {
  beforeEach(() => sessionStorage.clear());

  it.each([
    ["current-session logout", "End current session", "logout"],
    ["all-session logout", "End all sessions", "logoutAll"],
  ] as const)("does not let a late %s clear a newer login", async (_label, button, method) => {
    const accountBTokens={...tokens,access_token:"account-b-access",refresh_token:"account-b-refresh"};
    const accountB={...account,id:"user-b",learner_id:"learner-b",email:"account-b@example.invalid"};
    let releaseLogout:()=>void=()=>{};
    const logoutGate=new Promise<void>((resolve)=>{releaseLogout=resolve});
    const logoutSpy=method==="logout"
      ?vi.spyOn(api,"logout").mockReturnValue(logoutGate)
      :vi.spyOn(api,"logoutAll").mockReturnValue(logoutGate);
    vi.spyOn(api,"login").mockResolvedValue(accountBTokens);
    vi.spyOn(api,"me").mockResolvedValueOnce(account).mockResolvedValue(accountB);
    sessionStore.write(tokens);
    render(<AuthProvider><Harness/></AuthProvider>);
    await screen.findByText("Session: authenticated");

    await userEvent.click(screen.getByRole("button",{name:button}));
    await waitFor(()=>expect(logoutSpy).toHaveBeenCalledOnce());
    await userEvent.click(screen.getByRole("button",{name:"Switch account"}));
    await waitFor(()=>expect(sessionStore.read()).toEqual(accountBTokens));
    releaseLogout();

    await waitFor(()=>expect(screen.getByText("Session: authenticated")).toBeVisible());
    expect(sessionStore.read()).toEqual(accountBTokens);
  });
});
