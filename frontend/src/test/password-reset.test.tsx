import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiError, api } from "../api/client";
import { AuthProvider } from "../auth/AuthProvider";
import { RouterProvider } from "../routes/router";

function renderApp(path:string){history.replaceState({},"",path);return render(<RouterProvider><AuthProvider><App/></AuthProvider></RouterProvider>)}

describe("password recovery",()=>{
  it("requests a neutral emailed verification code",async()=>{
    vi.spyOn(api,"requestPasswordReset").mockResolvedValue({message:"If an account exists for this email, we've sent a verification code."});
    renderApp("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email"),"learner@example.com");
    await userEvent.click(screen.getByRole("button",{name:"Send verification code"}));
    expect(location.pathname).toBe("/reset-password");
    expect(sessionStorage.getItem("speakmate.reset.email")).toBe("learner@example.com");
  });

  it("validates and confirms a six-digit code",async()=>{
    sessionStorage.setItem("speakmate.reset.email","learner@example.com");
    const validate=vi.spyOn(api,"validatePasswordReset").mockResolvedValue({valid:true});
    const confirm=vi.spyOn(api,"confirmPasswordReset").mockResolvedValue({message:"Your password has been updated. Sign in with your new password."});
    renderApp("/reset-password");
    await userEvent.type(screen.getByLabelText("Six-digit verification code"),"123456");
    await userEvent.type(screen.getByLabelText("New password"),"NewStrongPassword456!");
    await userEvent.click(screen.getByRole("button",{name:"Update password"}));
    await waitFor(()=>expect(validate).toHaveBeenCalledWith("learner@example.com","123456"));
    expect(confirm).toHaveBeenCalledWith("learner@example.com","123456","NewStrongPassword456!");
    expect(await screen.findByRole("status")).toHaveTextContent("has been updated");
  });

  it("shows code errors without exposing the password",async()=>{
    vi.spyOn(api,"validatePasswordReset").mockRejectedValue(new ApiError(400,"This password reset code is invalid or expired."));
    renderApp("/reset-password");
    await userEvent.type(screen.getByLabelText("Email"),"learner@example.com");
    await userEvent.type(screen.getByLabelText("Six-digit verification code"),"000000");
    await userEvent.type(screen.getByLabelText("New password"),"SecretPassword123!");
    await userEvent.click(screen.getByRole("button",{name:"Update password"}));
    expect(await screen.findByRole("status")).toHaveTextContent("invalid or expired");
    expect(screen.getByRole("status")).not.toHaveTextContent("SecretPassword123!");
  });

  it("does not let the service worker cache password-reset navigations",async()=>{
    const runtime=globalThis as typeof globalThis&{process:{cwd:()=>string}};
    const source=await readFile(resolve(runtime.process.cwd(),"public/service-worker.js"),"utf8");
    const handlers=new Map<string,(event:{request:{method:string;mode:string;url:string};respondWith:(response:Promise<unknown>)=>void})=>void>();
    new Function("self","caches",source)({addEventListener:(name:string,handler:(typeof handlers extends Map<string,infer T>?T:never))=>handlers.set(name,handler)},{});
    const respondWith=vi.fn(); handlers.get("fetch")?.({request:{method:"GET",mode:"navigate",url:"https://app.example.com/reset-password"},respondWith});
    expect(respondWith).not.toHaveBeenCalled();
  });
});
