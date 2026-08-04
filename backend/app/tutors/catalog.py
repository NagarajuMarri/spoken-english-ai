"""Configuration-driven Indian-English tutor catalogue."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TutorProfile:
    tutor_id: str
    display_name: str
    gender: str
    avatar_profile: str
    voice_profile: str
    accent: str
    teaching_style: str
    animation_profile: str
    prompt_profile: str
    vocabulary_profile: str
    enabled: bool = True

    def public_dict(self) -> dict[str, str | bool]:
        return asdict(self)


TUTORS = (
    TutorProfile(
        "ananya", "Ananya", "female", "/tutors/ananya.jpg",
        "indian-english-female-warm", "Indian English",
        "patient, encouraging, and correction-aware",
        "natural-listening-thinking-speaking-v1", "supportive-daily-speaking-v1",
        "practical-indian-english-v1",
    ),
    TutorProfile(
        "arjun", "Arjun", "male", "/tutors/arjun.jpg",
        "indian-english-male-confident", "Indian English",
        "friendly, structured, and confidence-building",
        "natural-listening-thinking-speaking-v1", "structured-daily-speaking-v1",
        "practical-indian-english-v1",
    ),
)


def get_tutor(tutor_id: str) -> TutorProfile:
    for tutor in TUTORS:
        if tutor.tutor_id == tutor_id and tutor.enabled:
            return tutor
    raise KeyError(tutor_id)
