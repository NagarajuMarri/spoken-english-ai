import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiError, api } from "../api/client";
import { AuthProvider } from "../auth/AuthProvider";
import { RouterProvider } from "../routes/router";

type RegisteredServiceWorkerHandler = (event: {
  request: { method: string; mode: string; url: string };
  respondWith: (response: Promise<unknown>) => void;
}) => void;

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
    const validate=vi.spyOn(api, "validatePasswordReset").mockResolvedValue({valid:true});
    vi.spyOn(api, "confirmPasswordReset").mockResolvedValue({message:"Your password has been updated. Sign in with your new password."});
    const token="valid-single-use-token-value-123456789";
    renderApp(`/reset-password#token=${token}`);
    expect(location.hash).toBe("");
    expect(location.search).toBe("");
    expect(await screen.findByLabelText("New password")).toBeVisible();
    expect(validate).toHaveBeenCalledWith(token);
    await userEvent.type(screen.getByLabelText("New password"), "NewStrongPassword456!");
    await userEvent.click(screen.getByRole("button", {name:"Update password"}));
    expect(await screen.findByRole("status")).toHaveTextContent("has been updated");
    await userEvent.click(screen.getByRole("button", {name:"Back to login"}));
    expect(location.pathname).toBe("/login");
  });

  it("does not expose the password form for an invalid or used token", async () => {
    vi.spyOn(api, "validatePasswordReset").mockRejectedValue(new ApiError(400,"This password reset link has already been used."));
    renderApp("/reset-password#token=used-single-use-token-value-1234567890");
    expect(await screen.findByRole("alert")).toHaveTextContent("already been used");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("removes a legacy query token without submitting it", async () => {
    const validate=vi.spyOn(api, "validatePasswordReset");
    renderApp("/reset-password?campaign=acceptance&token=legacy-query-secret");
    expect(location.search).toBe("?campaign=acceptance");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid");
    expect(validate).not.toHaveBeenCalled();
  });

  it("shows password-policy errors without exposing the submitted password", async () => {
    vi.spyOn(api, "validatePasswordReset").mockResolvedValue({valid:true});
    vi.spyOn(api, "confirmPasswordReset").mockRejectedValue(new ApiError(422,"Password does not meet requirements."));
    renderApp("/reset-password#token=valid-single-use-token-value-123456789");
    await userEvent.type(await screen.findByLabelText("New password"), "ShortEnough12");
    await userEvent.click(screen.getByRole("button", {name:"Update password"}));
    await waitFor(()=>expect(screen.getByRole("status")).toHaveTextContent("does not meet requirements"));
    expect(screen.getByRole("status")).not.toHaveTextContent("ShortEnough12");
  });

  it("does not let the service worker cache password-reset navigations", async () => {
    const runtime=globalThis as typeof globalThis&{process:{cwd:()=>string}};
    const source=await readFile(resolve(runtime.process.cwd(),"public/service-worker.js"),"utf8");
    const handlers=new Map<string,RegisteredServiceWorkerHandler>();
    const scope={addEventListener:(name:string,handler:RegisteredServiceWorkerHandler)=>handlers.set(name,handler)};
    const evaluate=new Function("self","caches",source);
    evaluate(scope,{});

    const respondWith=vi.fn();
    const fetchHandler=handlers.get("fetch");
    expect(fetchHandler).toBeDefined();
    fetchHandler?.({
      request:{method:"GET",mode:"navigate",url:"https://app.example.com/reset-password?token=sentinel"},
      respondWith,
    });
    expect(respondWith).not.toHaveBeenCalled();
  });
});
