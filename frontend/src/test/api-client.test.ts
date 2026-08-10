import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, configureSession } from "../api/client";
import { account, tokens } from "./fixtures";

const response = (status:number, body:unknown) => new Response(
  body === undefined ? null : JSON.stringify(body),
  {status, headers:{"Content-Type":"application/json"}},
);

describe("central API session lifecycle", () => {
  const update = vi.fn(), clear = vi.fn();
  let current:typeof tokens|null;
  beforeEach(() => {
    update.mockClear(); clear.mockClear();
    current=tokens;
    configureSession({
      get:()=>current,
      update:(value)=>{current=value;update(value)},
      clear:(expectedRefreshToken)=>{
        if(expectedRefreshToken&&current&&current.refresh_token!==expectedRefreshToken)return;
        current=null;clear();
      },
    });
  });
  it("rotates an expired access token and retries", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(response(401,{})).mockResolvedValueOnce(response(200,next)).mockResolvedValueOnce(response(200,account)));
    await expect(api.me()).resolves.toEqual(account);
    expect(update).toHaveBeenCalledWith(next);
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("shares one refresh across concurrent JSON and speech requests", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    let releaseRefresh:()=>void=()=>{};
    const refreshGate=new Promise<void>((resolve)=>{releaseRefresh=resolve});
    configureSession({
      get:()=>current,
      update:(value)=>{current=value;update(value)},
      clear,
    });
    const audio=new Uint8Array(64);audio[0]=0x49;audio[1]=0x44;audio[2]=0x33;
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
      const url=String(input);
      if(url.endsWith("/api/v1/auth/refresh")){
        await refreshGate;
        return response(200,next);
      }
      const authorization=new Headers(init?.headers).get("Authorization");
      if(authorization===`Bearer ${tokens.access_token}`)return response(401,{});
      if(url.endsWith("/speech"))return new Response(audio,{status:200,headers:{"Content-Type":"audio/mpeg"}});
      return response(200,account);
    }));

    const requests=Promise.all([api.me(),api.speech("conversation-1","turn-1")]);
    await vi.waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/api/v1/auth/refresh"))).toHaveLength(1));
    releaseRefresh();
    await expect(requests).resolves.toMatchObject([account,{blob:expect.any(Blob)}]);

    const calls=vi.mocked(fetch).mock.calls;
    expect(calls.filter(([url])=>String(url).endsWith("/api/v1/auth/refresh"))).toHaveLength(1);
    expect(calls).toHaveLength(5);
    expect(update).toHaveBeenCalledOnce();
    const retriedProtectedCalls=calls.filter(([url,init])=>
      !String(url).endsWith("/api/v1/auth/refresh")
      && new Headers(init?.headers).get("Authorization")===`Bearer ${next.access_token}`
    );
    expect(retriedProtectedCalls).toHaveLength(2);
  });
  it("clears state when refresh is rejected", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(response(401,{})).mockResolvedValueOnce(response(401,{})));
    await expect(api.me()).rejects.toThrow("session");
    expect(clear).toHaveBeenCalled();
  });
  it("never replays a stale request after an account switch", async () => {
    const rotated={...tokens,access_token:"rotated-a",refresh_token:"rotated-a-refresh"};
    const accountB={...tokens,access_token:"account-b-access",refresh_token:"account-b-refresh"};
    let releaseRefresh:()=>void=()=>{};
    const gate=new Promise<void>((resolve)=>{releaseRefresh=resolve});
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      if(String(input).endsWith("/api/v1/auth/refresh")){
        await gate;
        return response(200,rotated);
      }
      return response(401,{});
    }));

    const pending=api.conversation("learner-a");
    await vi.waitFor(()=>expect(vi.mocked(fetch).mock.calls).toHaveLength(2));
    current=accountB;
    releaseRefresh();
    await expect(pending).rejects.toMatchObject({status:401});
    expect(update).not.toHaveBeenCalled();
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).includes("/conversations"))).toHaveLength(1);
  });
  it("does not let a delayed refresh body overwrite a new login", async () => {
    const rotated={...tokens,access_token:"rotated-a",refresh_token:"rotated-a-refresh"};
    const accountB={...tokens,access_token:"account-b-access",refresh_token:"account-b-refresh"};
    let releaseBody:()=>void=()=>{},markBodyStarted:()=>void=()=>{};
    const bodyGate=new Promise<void>((resolve)=>{releaseBody=resolve});
    const bodyStarted=new Promise<void>((resolve)=>{markBodyStarted=resolve});
    const delayedRefresh={
      ok:true,
      status:200,
      json:async()=>{markBodyStarted();await bodyGate;return rotated},
    } as Response;
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>
      String(input).endsWith("/api/v1/auth/refresh")?delayedRefresh:response(401,{})
    ));

    const pending=api.conversation("learner-a");
    await bodyStarted;
    current=accountB;
    releaseBody();

    await expect(pending).rejects.toMatchObject({status:401});
    expect(current).toBe(accountB);
    expect(update).not.toHaveBeenCalled();
    expect(clear).not.toHaveBeenCalled();
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).includes("/conversations"))).toHaveLength(1);
  });
  it("does not clear a new login when an old refresh is rejected late", async () => {
    const accountB={...tokens,access_token:"account-b-access",refresh_token:"account-b-refresh"};
    let releaseRefresh:()=>void=()=>{};
    const gate=new Promise<void>((resolve)=>{releaseRefresh=resolve});
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      if(String(input).endsWith("/api/v1/auth/refresh")){
        await gate;
        return response(401,{});
      }
      return response(401,{});
    }));

    const pending=api.conversation("learner-a");
    await vi.waitFor(()=>expect(vi.mocked(fetch).mock.calls).toHaveLength(2));
    current=accountB;
    releaseRefresh();
    await expect(pending).rejects.toMatchObject({status:401});
    expect(current).toBe(accountB);
    expect(clear).not.toHaveBeenCalled();
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).includes("/conversations"))).toHaveLength(1);
  });
  it("does not restore a session after logout while an old refresh completes", async () => {
    const rotated={...tokens,access_token:"rotated-a",refresh_token:"rotated-a-refresh"};
    let releaseRefresh:()=>void=()=>{};
    const gate=new Promise<void>((resolve)=>{releaseRefresh=resolve});
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      if(String(input).endsWith("/api/v1/auth/refresh")){
        await gate;
        return response(200,rotated);
      }
      return response(401,{});
    }));

    const pending=api.conversation("learner-a");
    await vi.waitFor(()=>expect(vi.mocked(fetch).mock.calls).toHaveLength(2));
    current=null;
    releaseRefresh();
    await expect(pending).rejects.toMatchObject({status:401});
    expect(current).toBeNull();
    expect(update).not.toHaveBeenCalled();
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).includes("/conversations"))).toHaveLength(1);
  });
  it("waits for an existing refresh and logs out its rotated token without replaying the stale POST", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    let releaseRefresh:()=>void=()=>{};
    const gate=new Promise<void>((resolve)=>{releaseRefresh=resolve});
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      const url=String(input);
      if(url.endsWith("/api/v1/auth/refresh")){
        await gate;
        return response(200,next);
      }
      if(url.endsWith("/api/v1/auth/logout"))return response(204,undefined);
      return response(401,{});
    }));

    const stalePost=api.conversation("learner-a");
    await vi.waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/api/v1/auth/refresh"))).toHaveLength(1));
    const logout=api.logout(tokens.refresh_token);
    await Promise.resolve();
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/api/v1/auth/logout"))).toHaveLength(0);
    releaseRefresh();

    await expect(stalePost).rejects.toMatchObject({status:401});
    await expect(logout).resolves.toBeUndefined();
    const logoutCalls=vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/api/v1/auth/logout"));
    expect(logoutCalls).toHaveLength(1);
    expect(JSON.parse(String(logoutCalls[0][1]?.body))).toEqual({refresh_token:next.refresh_token});
    expect(new Headers(logoutCalls[0][1]?.headers).get("Authorization")).toBe(`Bearer ${next.access_token}`);
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).includes("/conversations"))).toHaveLength(1);
    expect(clear).toHaveBeenCalledOnce();
    expect(current).toBeNull();
  });
  it("logs out the rotated refresh token after an expired-access response", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      const url=String(input);
      if(url.endsWith("/api/v1/auth/refresh"))return response(200,next);
      const logoutCalls=vi.mocked(fetch).mock.calls.filter(([value])=>String(value).endsWith("/api/v1/auth/logout"));
      return logoutCalls.length===1?response(401,{}):response(204,undefined);
    }));

    await api.logout(tokens.refresh_token);
    const logoutCalls=vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/api/v1/auth/logout"));
    expect(logoutCalls).toHaveLength(2);
    expect(JSON.parse(String(logoutCalls[0][1]?.body))).toEqual({refresh_token:tokens.refresh_token});
    expect(JSON.parse(String(logoutCalls[1][1]?.body))).toEqual({refresh_token:next.refresh_token});
    expect(new Headers(logoutCalls[1][1]?.headers).get("Authorization")).toBe(`Bearer ${next.access_token}`);
    expect(update).toHaveBeenCalledWith(next);
    expect(clear).toHaveBeenCalledOnce();
    expect(current).toBeNull();
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
  it("clears the rotated local session after a successful password reset", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
      const url=String(input);
      if(url.endsWith("/api/v1/auth/refresh"))return response(200,next);
      const confirmations=vi.mocked(fetch).mock.calls.filter(([value])=>String(value).endsWith("/api/v1/auth/password-reset/confirm"));
      return confirmations.length===1?response(401,{}):response(200,{message:"Password updated."});
    }));

    await api.confirmPasswordReset("single-use-token-value-with-safe-length-123", "NewStrongPassword456!");

    expect(update).toHaveBeenCalledWith(next);
    expect(clear).toHaveBeenCalledOnce();
    expect(current).toBeNull();
  });
  it("does not clear a login created while an anonymous password reset was pending", async () => {
    const accountB={...tokens,access_token:"account-b-access",refresh_token:"account-b-refresh"};
    let releaseReset:()=>void=()=>{};
    const gate=new Promise<void>((resolve)=>{releaseReset=resolve});
    current=null;
    vi.stubGlobal("fetch",vi.fn(async()=>{
      await gate;
      return response(200,{message:"Password updated."});
    }));

    const pending=api.confirmPasswordReset("single-use-token-value-with-safe-length-123", "NewStrongPassword456!");
    current=accountB;
    releaseReset();

    await expect(pending).resolves.toEqual({message:"Password updated."});
    expect(current).toBe(accountB);
    expect(clear).not.toHaveBeenCalled();
  });
  it("retrieves authenticated binary tutor audio and safe evidence headers", async () => {
    const audio=new Uint8Array(64);audio[0]=0x49;audio[1]=0x44;audio[2]=0x33;
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(audio,{status:200,headers:{
      "Content-Type":"audio/mpeg","X-TTS-Provider":"openai","X-TTS-Model":"gpt-4o-mini-tts",
      "X-TTS-Voice":"marin","X-TTS-Cache":"MISS","X-TTS-Input-Characters":"42",
      "X-TTS-Provider-Requests":"1","X-TTS-Usage-Classification":"provider-token-usage-unavailable",
    }})));
    const speech=await api.speech("conversation-1","turn-1");
    expect(speech.blob.size).toBe(64);
    expect(speech).toMatchObject({provider:"openai",model:"gpt-4o-mini-tts",voice:"marin",cacheStatus:"MISS",inputCharacters:42,providerRequests:1});
    const[url,init]=vi.mocked(fetch).mock.calls[0];
    expect(url).toContain("/api/v1/conversations/conversation-1/ai-turns/turn-1/speech");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe(`Bearer ${tokens.access_token}`);
  });
  it("sends a stable transcription identity with the raw audio capture", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(200,{
      transcript:"Hello",detected_language:"en",confidence:0.99,duration_ms:250,size_bytes:5,
    })));
    const blob=new Blob(["audio"],{type:"audio/webm"});
    await api.transcribe("conversation-1",{blob,durationMs:250},"voice-capture-identity");
    const[url,init]=vi.mocked(fetch).mock.calls[0];
    const headers=new Headers(init?.headers);
    expect(url).toContain("/api/v1/conversations/conversation-1/transcriptions");
    expect(headers.get("Idempotency-Key")).toBe("voice-capture-identity");
    expect(headers.get("X-Voice-Processing-Consent")).toBe("accepted");
    expect(init?.body).toBe(blob);
  });
  it("keeps the same transcription identity and audio across an access-token refresh", async () => {
    const next={...tokens,access_token:"new-access",refresh_token:"new-refresh-token-value"};
    let current=tokens;
    configureSession({
      get:()=>current,
      update:(value)=>{current=value;update(value)},
      clear,
    });
    vi.stubGlobal("fetch",vi.fn()
      .mockResolvedValueOnce(response(401,{}))
      .mockResolvedValueOnce(response(200,next))
      .mockResolvedValueOnce(response(200,{
        transcript:"Hello",detected_language:"en",confidence:0.99,duration_ms:250,size_bytes:5,
      })));
    const blob=new Blob(["audio"],{type:"audio/webm"});

    await api.transcribe("conversation-1",{blob,durationMs:250},"voice-capture-refresh-identity");

    const transcriptionCalls=vi.mocked(fetch).mock.calls.filter(([url])=>
      String(url).includes("/conversations/conversation-1/transcriptions")
    );
    expect(transcriptionCalls).toHaveLength(2);
    for(const[,init]of transcriptionCalls){
      expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("voice-capture-refresh-identity");
      expect(init?.body).toBe(blob);
    }
    expect(new Headers(transcriptionCalls[0][1]?.headers).get("Authorization")).toBe(`Bearer ${tokens.access_token}`);
    expect(new Headers(transcriptionCalls[1][1]?.headers).get("Authorization")).toBe(`Bearer ${next.access_token}`);
  });
});
