import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { RouterProvider } from "./routes/router";
import "./styles.css";

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/service-worker.js");
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode><RouterProvider><AuthProvider><App /></AuthProvider></RouterProvider></StrictMode>,
);
