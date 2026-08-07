import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiError, api } from "../api/client";
import { AuthProvider } from "../auth/AuthProvider";
import { RouterProvider } from "../routes/router";

function renderApp(path: string) {
  history.replaceState({}, "", path);
  return render(<RouterProvider><AuthProvider><App /></AuthProvider></RouterProvider>);
}

describe("password recovery", () => {
  it("links login to a neutral reset request", async () => {
    vi.spyOn(api, "requestPasswordReset").mockResolvedValue({message:"If an account matches that email, password reset instructions have been sent."});
    renderApp("/login");
    await userEvent.click(screen.getByRole("button", {name:"Forgot password?"}));
    expect(location.pathname).toBe("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email"), "learner@example.com");
    await userEvent.click(screen.getByRole("button", {name:"Send reset instructions"}));
    expect(await screen.findByRole("status")).toHaveTextContent("If an account matches");
  });

  it("validates the token before showing the update form and returns to login", async () => {
    vi.spyOn(api, "validatePasswordReset").mockResolvedValue({valid:true});
    vi.spyOn(api, "confirmPasswordReset").mockResolvedValue({message:"Your password has been updated. Sign in with your new password."});
    renderApp("/reset-password?token=valid-single-use-token-value-123456789");
    expect(await screen.findByLabelText("New password")).toBeVisible();
    await userEvent.type(screen.getByLabelText("New password"), "NewStrongPassword456!");
    await userEvent.click(screen.getByRole("button", {name:"Update password"}));
    expect(await screen.findByRole("status")).toHaveTextContent("has been updated");
    await userEvent.click(screen.getByRole("button", {name:"Back to login"}));
    expect(location.pathname).toBe("/login");
  });

  it("does not expose the password form for an invalid or used token", async () => {
    vi.spyOn(api, "validatePasswordReset").mockRejectedValue(new ApiError(400,"This password reset link has already been used."));
    renderApp("/reset-password?token=used-single-use-token-value-1234567890");
    expect(await screen.findByRole("alert")).toHaveTextContent("already been used");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("shows password-policy errors without exposing the submitted password", async () => {
    vi.spyOn(api, "validatePasswordReset").mockResolvedValue({valid:true});
    vi.spyOn(api, "confirmPasswordReset").mockRejectedValue(new ApiError(422,"Password does not meet requirements."));
    renderApp("/reset-password?token=valid-single-use-token-value-123456789");
    await userEvent.type(await screen.findByLabelText("New password"), "ShortEnough12");
    await userEvent.click(screen.getByRole("button", {name:"Update password"}));
    await waitFor(()=>expect(screen.getByRole("status")).toHaveTextContent("does not meet requirements"));
    expect(screen.getByRole("status")).not.toHaveTextContent("ShortEnough12");
  });
});
