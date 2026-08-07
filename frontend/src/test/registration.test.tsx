import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiError, api } from "../api/client";
import { AuthProvider } from "../auth/AuthProvider";
import { RouterProvider } from "../routes/router";
import { account, tokens } from "./fixtures";

function renderRegistration() {
  history.replaceState({}, "", "/register");
  return render(<RouterProvider><AuthProvider><App /></AuthProvider></RouterProvider>);
}

async function fillRegistration() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Name"), "New Learner");
  await user.type(screen.getByLabelText("Closed-beta invitation code (if provided)"), "BETA");
  await user.type(screen.getByLabelText("Email"), "new-learner@example.invalid");
  await user.type(screen.getByLabelText("Password"), "StrongPassword123!");
  await user.click(screen.getByRole("checkbox"));
  return user;
}

describe("closed-beta registration", () => {
  it("submits the invite and explicit legal consent", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue({ ...account, tokens });
    renderRegistration();
    const user = await fillRegistration();
    await user.click(screen.getByRole("button", { name: "Create learner account" }));
    await waitFor(() => expect(register).toHaveBeenCalledWith({
      display_name: "New Learner",
      email: "new-learner@example.invalid",
      password: "StrongPassword123!",
      invitation_code: "BETA",
      terms_privacy_accepted: true,
    }));
  });

  it("shows the registration error without exposing submitted secrets", async () => {
    vi.spyOn(api, "register").mockRejectedValue(new ApiError(
      403, "You are on the beta waiting list. We will contact you when access is available.",
    ));
    renderRegistration();
    const user = await fillRegistration();
    await user.click(screen.getByRole("button", { name: "Create learner account" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("beta waiting list");
    expect(alert).not.toHaveTextContent("StrongPassword123!");
    expect(alert).not.toHaveTextContent("BETA");
  });
});
