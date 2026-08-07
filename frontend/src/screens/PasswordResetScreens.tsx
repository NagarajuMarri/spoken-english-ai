import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import { useRouter } from "../routes/router";

export function RequestPasswordResetScreen() {
  const { navigate } = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    const email = String(new FormData(event.currentTarget).get("email"));
    try { setMessage((await api.requestPasswordReset(email)).message); }
    catch { setMessage("We could not process the request. Please wait and try again."); }
    finally { setBusy(false); }
  }
  return <main className="auth"><section><p className="eyebrow">Account recovery</p><h1>Reset your<br/><em>password.</em></h1><p>We will send a short-lived, single-use reset link.</p></section><form className="card" onSubmit={submit}><h2>Forgot password</h2><label>Email<input name="email" type="email" required autoComplete="email"/></label><button disabled={busy}>{busy?"Please wait…":"Send reset instructions"}</button><button type="button" className="link" onClick={()=>navigate("/login")}>Back to login</button><p role="status" aria-live="polite" className="message">{message}</p></form></main>;
}

export function UpdatePasswordScreen() {
  const { navigate } = useRouter();
  const token = new URLSearchParams(location.search).get("token") ?? "";
  const [state, setState] = useState<"checking"|"valid"|"invalid"|"complete">("checking");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    if (!token) { setState("invalid"); setMessage("This password reset link is invalid."); return; }
    api.validatePasswordReset(token).then(() => { if (active) setState("valid"); }).catch((error) => {
      if (active) { setState("invalid"); setMessage(error instanceof ApiError ? error.message : "This password reset link is invalid."); }
    });
    return () => { active = false; };
  }, [token]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    const password = String(new FormData(event.currentTarget).get("password"));
    try { setMessage((await api.confirmPasswordReset(token, password)).message); setState("complete"); }
    catch (error) { setMessage(error instanceof ApiError ? error.message : "We could not update your password."); }
    finally { setBusy(false); }
  }
  if (state === "checking") return <main className="loading" aria-live="polite">Checking your password reset link…</main>;
  return <main className="auth"><section><p className="eyebrow">Account recovery</p><h1>Choose a new<br/><em>password.</em></h1><p>Your existing signed-in sessions will be revoked.</p></section><section className="card"><h2>Update password</h2>{state === "valid"&&<form onSubmit={submit}><label>New password<input name="password" type="password" minLength={12} maxLength={72} required autoComplete="new-password"/></label><button disabled={busy}>{busy?"Please wait…":"Update password"}</button></form>}<p role={state === "invalid"?"alert":"status"} aria-live="polite" className="message">{message}</p>{(state === "invalid"||state === "complete")&&<button type="button" onClick={()=>navigate("/login",true)}>Back to login</button>}</section></main>;
}
