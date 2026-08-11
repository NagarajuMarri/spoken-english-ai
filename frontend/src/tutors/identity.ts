import type { Tutor } from "../models";

export const CANONICAL_ANANYA_PORTRAIT = "/tutors/ananya.jpg";

export function tutorPortrait(tutor: Tutor): string {
  return tutor.tutor_id === "ananya" ? CANONICAL_ANANYA_PORTRAIT : tutor.avatar_profile;
}
