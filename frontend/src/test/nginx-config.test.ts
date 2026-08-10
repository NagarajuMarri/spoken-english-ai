import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

let source = "";
let productionCompose = "";
let dockerfile = "";
let serviceWorker = "";
let productionEnvironment = "";
let backendConfiguration = "";
let liveTargetSafety = "";
let liveAuthAcceptance = "";
let registrationAcceptance = "";
let passwordResetAcceptance = "";

beforeAll(async () => {
  const runtime = globalThis as typeof globalThis & { process: { cwd: () => string } };
  [
    source,
    productionCompose,
    dockerfile,
    serviceWorker,
    productionEnvironment,
    backendConfiguration,
    liveTargetSafety,
    liveAuthAcceptance,
    registrationAcceptance,
    passwordResetAcceptance,
  ] = await Promise.all([
    readFile(resolve(runtime.process.cwd(), "nginx.conf"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "..", "compose.production.yaml"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "Dockerfile"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "public", "service-worker.js"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "..", ".env.production.example"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "..", "backend", "app", "core", "config.py"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "e2e", "live-target-safety.ts"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "e2e", "live-auth.spec.ts"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "e2e", "registration-acceptance.spec.ts"), "utf8"),
    readFile(resolve(runtime.process.cwd(), "e2e", "password-reset-acceptance.spec.ts"), "utf8"),
  ]);
});

describe("production Nginx security boundary", () => {
  it("keeps security headers at server scope so cache locations inherit them", () => {
    const addHeaderLines = source.split(/\r?\n/).filter((line) => line.includes("add_header"));

    expect(addHeaderLines).toHaveLength(6);
    expect(addHeaderLines.every((line) => /^\s{2}add_header /.test(line))).toBe(true);
    expect(source).toContain("add_header X-Content-Type-Options nosniff always;");
    expect(source).toContain("add_header X-Frame-Options DENY always;");
    expect(source).toContain("add_header Referrer-Policy no-referrer always;");
    expect(source).toContain("frame-ancestors 'none'");
  });

  it("allows only the app capabilities needed for API, microphone, and tutor audio", () => {
    expect(source).toContain("default-src 'self'");
    expect(source).toContain("connect-src 'self'");
    expect(source).toContain("media-src 'self' blob:");
    expect(source).toContain("object-src 'none'");
    expect(source).toContain("script-src 'self' 'wasm-unsafe-eval'");
    expect(source).not.toContain("'unsafe-eval'");
    expect(source).toContain("style-src 'self'");
    expect(source).toContain("microphone=(self)");
    expect(source).toContain("camera=()");
    expect(source).toContain("payment=()");
  });

  it("trusts only the configured ingress and forwards its verified client address", () => {
    expect(source).toContain("set_real_ip_from ${TRUSTED_INGRESS_CIDR};");
    expect(source).toContain("real_ip_header X-Forwarded-For;");
    expect(source).toContain("real_ip_recursive on;");
    expect(source.match(/proxy_set_header X-Real-IP \$remote_addr;/g)).toHaveLength(3);
    expect(source.match(/proxy_set_header X-Forwarded-For \$remote_addr;/g)).toHaveLength(3);
    expect(source.match(/proxy_set_header X-Forwarded-Proto https;/g)).toHaveLength(3);
    expect(source).not.toContain("$proxy_add_x_forwarded_for");
    expect(dockerfile).toContain("NGINX_ENVSUBST_FILTER=TRUSTED_INGRESS_CIDR");
    expect(productionEnvironment).toContain("set this to the exact host-ingress peer");
    expect(productionEnvironment).toMatch(
      /^TRUSTED_INGRESS_CIDR=(?:(?:\d{1,3}\.){3}\d{1,3}\/32|[0-9a-fA-F:]+\/128)$/m,
    );
    expect(productionEnvironment).not.toMatch(/TRUSTED_INGRESS_CIDR=(?:0\.0\.0\.0\/0|::\/0)/);

    const backendService = productionCompose.split("  backend:", 2)[1]?.split("  worker:", 1)[0] ?? "";
    expect(backendService).toContain('"--proxy-headers", "--forwarded-allow-ips=*"');
    expect(backendService).not.toMatch(/^\s+ports:/m);
    expect(backendService).toContain("'X-Forwarded-Proto': 'https'");
  });

  it("does not access-log password-reset navigations", () => {
    expect(source).toMatch(/location = \/reset-password \{\s+access_log off;/);
    expect(source).toContain('~^/reset-password$ "no-store";');
    expect(serviceWorker).toContain('spoken-english-shell-v2');
    expect(serviceWorker).toContain("keys.filter((key) => key !== CACHE)");
    expect(serviceWorker).toContain("caches.delete(key)");
    expect(serviceWorker).toContain('url.pathname === "/reset-password"');
  });

  it("streams bounded transcription uploads without writable container storage", () => {
    expect(source).toMatch(/location ~ \^\/api\/v1\/conversations\/\[\^\/\]\+\/transcriptions\$ \{/);
    expect(source).toContain("client_max_body_size 10m;");
    expect(source).toContain("proxy_request_buffering off;");
    expect(source).toContain("proxy_http_version 1.1;");
    expect(backendConfiguration).toContain("upload_size_limit_bytes: int = 10_000_000");
    const frontendService = productionCompose.split("  frontend:", 2)[1] ?? "";
    expect(frontendService).toContain("TRUSTED_INGRESS_CIDR: ${TRUSTED_INGRESS_CIDR:?");
    expect(frontendService).toContain("read_only: true");
    expect(frontendService).toContain("tmpfs: [/tmp, /var/cache/nginx]");
    expect(frontendService).toContain('ports: ["127.0.0.1:8080:8080"]');
    expect(frontendService).not.toContain('ports: ["8080:8080"]');
  });

  it("blocks mutating live acceptance on production and requires an explicit remote override", () => {
    expect(liveTargetSafety).toContain('const OVERRIDE_VALUE = "I_ACCEPT_DISPOSABLE_TEST_DATA";');
    expect(liveTargetSafety).toContain('request.get("/health/version")');
    expect(liveTargetSafety).toContain('environment === "production"');
    expect(liveTargetSafety).toContain("Mutating Playwright acceptance is forbidden against production.");
    expect(liveTargetSafety).toContain("SPEAKMATE_ALLOW_DISPOSABLE_E2E_TARGET=${OVERRIDE_VALUE}");
    expect(liveTargetSafety).toContain("!isLoopback(frontend)");
    expect(liveTargetSafety).toContain("!isLoopback(backend)");

    expect(liveAuthAcceptance.match(/await assertSafeLiveTarget\(request\);/g)).toHaveLength(1);
    expect(registrationAcceptance.match(/await assertSafeLiveTarget\(request\);/g)).toHaveLength(2);
    expect(passwordResetAcceptance.match(/await assertSafeLiveTarget\(request\);/g)).toHaveLength(1);
    expect(passwordResetAcceptance).toContain("assertSameOrigin(delivery.reset_url, page.url());");
  });
});
