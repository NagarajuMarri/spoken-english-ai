export type TutorRenderTier = "FULL_3D" | "LIGHTWEIGHT_3D" | "STATIC_FALLBACK";

interface NavigatorCapabilities {
  hardwareConcurrency?: number;
  connection?: { saveData?: boolean };
}

/** Provider-neutral capability policy; actual context creation remains fail-closed in the renderer. */
export function selectTutorRenderTier(
  tutorId: string,
  capabilities: NavigatorCapabilities = typeof navigator === "undefined" ? {} : navigator,
  webglAvailable = typeof WebGLRenderingContext !== "undefined"
    || typeof WebGL2RenderingContext !== "undefined",
): TutorRenderTier {
  if (tutorId !== "ananya" || !webglAvailable) return "STATIC_FALLBACK";
  if (
    capabilities.connection?.saveData
    || (Number(capabilities.hardwareConcurrency) > 0 && Number(capabilities.hardwareConcurrency) <= 2)
  ) return "LIGHTWEIGHT_3D";
  return "FULL_3D";
}
