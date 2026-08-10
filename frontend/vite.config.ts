import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const apiProxyTarget = loadEnv(mode, ".", "").VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": apiProxyTarget,
        "/health": apiProxyTarget,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      testTimeout: 15_000,
      exclude: ["e2e/**", "node_modules/**"],
    },
  };
});
