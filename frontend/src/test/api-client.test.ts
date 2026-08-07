import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, configureSession } from "../api/client";
import { account, tokens } from "./fixtures";

const response = (status:number, body:unknown) => new Response(
  body === undefined ? null : JSON.stringify(body),
  {status, headers:{"Content-Type":"application/json"}},
);

describe("central API session lifecycle", () => {
  const update = vi.fn(), clear = vi.fn();
  beforeEach(() => {
    update.mockClear(); clear.mockClear();
    configureSession({get:()=>tokens, update, clear});
  });
  it("rotates an expired access token and retries", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(response(401,{})).mockResolvedValueOnce(response(200,next)).mockResolvedValueOnce(response(200,account)));
    await expect(api.me()).resolves.toEqual(account);
    expect(update).toHaveBeenCalledWith(next);
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("clears state when refresh is rejected", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(response(401,{})).mockResolvedValueOnce(response(401,{})));
    await expect(api.me()).rejects.toThrow("session");
    expect(clear).toHaveBeenCalled();
  });
  it("keeps credentials out of request headers", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(200,tokens)));
    await api.login("review@example.invalid","StrongPassword123!");
    const init=vi.mocked(fetch).mock.calls[0][1];
    expect(JSON.stringify(init?.headers)).not.toContain("StrongPassword123!");
  });
  it("clears the local session after a successful password reset", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(200,{message:"Password updated."})));
    await api.confirmPasswordReset("single-use-token-value-with-safe-length-123", "NewStrongPassword456!");
    expect(clear).toHaveBeenCalledOnce();
  });
});
