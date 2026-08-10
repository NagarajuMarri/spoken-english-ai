const enabled = import.meta.env.VITE_ENABLE_ENGINEERING_DIAGNOSTICS === "true";

export function engineeringDiagnosticInfo(event: string, details: Record<string, unknown>) {
  if (enabled) console.info(event, details);
}

export function engineeringDiagnosticWarning(event: string, details: Record<string, unknown>) {
  if (enabled) console.warn(event, details);
}
