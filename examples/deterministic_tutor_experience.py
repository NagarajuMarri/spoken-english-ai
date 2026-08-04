"""Offline demonstration of the configuration-driven Milestone 8 tutors."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.tutors import TUTORS


def main() -> None:
    for tutor in TUTORS:
        print(
            f"{tutor.display_name}: {tutor.accent}; {tutor.voice_profile}; "
            f"animations={tutor.animation_profile}; enabled={str(tutor.enabled).lower()}"
        )


if __name__ == "__main__":
    main()
