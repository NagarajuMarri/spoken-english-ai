import { useEffect, useState } from "react";
import { api } from "./api/client";
import { useAuth } from "./auth/AuthProvider";
import { AppShell } from "./components/AppShell";
import type { Dashboard, TutorPreference } from "./models";
import { useRouter } from "./routes/router";
import { AuthScreen } from "./screens/AuthScreen";
import { ConversationScreen, DailyLessonScreen, DashboardScreen, SettingsScreen } from "./screens/ExperienceScreens";
import { FeedbackScreen, FounderScreen, ProgressDetailScreen, SubscriptionScreen } from "./screens/LaunchScreens";
import { PublicScreen } from "./screens/PublicScreens";
import { TutorPicker } from "./screens/TutorPicker";

const publicContent = new Set(["/", "/pricing", "/privacy", "/terms", "/refunds", "/support", "/faq"]);

export function App() {
  const { status, account } = useAuth();
  const { route, navigate, isPublic } = useRouter();
  const [pref, setPref] = useState<TutorPreference>();
  const [data, setData] = useState<Dashboard>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (status === "anonymous" && !isPublic) navigate("/login", true);
    if (status === "authenticated" && (route === "/login" || route === "/register")) navigate("/app/dashboard", true);
  }, [status, isPublic, route, navigate]);
  useEffect(() => {
    if (status !== "authenticated" || route === "/onboarding" || isPublic) return;
    Promise.all([api.preference(), api.dashboard()]).then(([p, d]) => { setPref(p); setData(d); }).catch(() => setError("Your learning space could not be loaded."));
  }, [status, route, isPublic]);
  if (publicContent.has(route)) return <PublicScreen route={route} />;
  if (status === "restoring") return <main className="loading" aria-live="polite">Restoring your secure session…</main>;
  if (route === "/login") return <AuthScreen mode="login" />;
  if (route === "/register") return <AuthScreen mode="register" />;
  if (status !== "authenticated" || !account) return null;
  if (route === "/onboarding") return <TutorPicker />;
  if (error) return <main role="alert" className="loading">{error} <button onClick={() => location.reload()}>Retry</button></main>;
  if (!pref || !data) return <main className="loading" aria-live="polite">Preparing your lesson…</main>;
  const screen = route === "/app/dashboard" ? <DashboardScreen data={data} tutor={pref.tutor} /> : route === "/app/daily-lesson" ? <DailyLessonScreen /> : route === "/app/conversation" ? <ConversationScreen account={account} tutor={pref.tutor} telugu={pref.telugu_explanations_enabled} /> : route === "/app/progress" ? <ProgressDetailScreen /> : route === "/app/feedback" ? <FeedbackScreen /> : route === "/app/subscription" ? <SubscriptionScreen /> : route === "/app/founder" ? <FounderScreen /> : <SettingsScreen tutor={pref.tutor} onChange={() => navigate("/onboarding")} />;
  return <AppShell>{screen}</AppShell>;
}
