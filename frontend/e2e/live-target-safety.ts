import type { APIRequestContext } from "@playwright/test";

const LOCAL_ENVIRONMENTS = new Set(["development", "test"]);
const DISPOSABLE_ENVIRONMENTS = new Set(["development", "test", "staging"]);
const OVERRIDE_VALUE = "I_ACCEPT_DISPOSABLE_TEST_DATA";

function isLoopback(value: string) {
  const hostname = new URL(value).hostname.toLowerCase();
  return hostname === "localhost" || hostname === "::1" || hostname.startsWith("127.");
}

export async function assertSafeLiveTarget(request: APIRequestContext) {
  const frontend = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173";
  const backend = process.env.VITE_API_PROXY_TARGET;
  const hasRemoteTarget = !isLoopback(frontend) || Boolean(backend && !isLoopback(backend));
  const override = process.env.SPEAKMATE_ALLOW_DISPOSABLE_E2E_TARGET === OVERRIDE_VALUE;

  const response = await request.get("/health/version");
  if (!response.ok()) {
    throw new Error(`Live acceptance target did not expose /health/version (${response.status()}).`);
  }
  const version = await response.json() as { environment?: string };
  const environment = version.environment?.toLowerCase() ?? "unknown";
  if (environment === "production") {
    throw new Error("Mutating Playwright acceptance is forbidden against production.");
  }
  if (!DISPOSABLE_ENVIRONMENTS.has(environment)) {
    throw new Error(`Live acceptance target environment '${environment}' is not disposable.`);
  }
  if ((hasRemoteTarget || !LOCAL_ENVIRONMENTS.has(environment)) && !override) {
    throw new Error(
      `Non-local live acceptance requires SPEAKMATE_ALLOW_DISPOSABLE_E2E_TARGET=${OVERRIDE_VALUE}.`,
    );
  }
}

export function assertSameOrigin(target: string, currentPageUrl: string) {
  const targetUrl = new URL(target);
  const currentUrl = new URL(currentPageUrl);
  if (targetUrl.origin !== currentUrl.origin) {
    throw new Error("Password-reset delivery pointed outside the verified acceptance target.");
  }
}
