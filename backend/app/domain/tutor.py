from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TutorTurn:
    response: str
    correction: str | None = None


def respond(text: str, include_telugu_explanation: bool = False) -> TutorTurn:
    normalized = " ".join(text.split())
    correction: str | None = None
    response = "Thanks for sharing. Could you tell me a little more?"

    if re.search(r"\bI am go to (?:the )?office yesterday\b", normalized, re.IGNORECASE):
        correction = 'You can say: “I went to the office yesterday.”'
        response = "I see. What did you do at the office?"
    elif re.search(r"\bI (?:go|goed) .+ yesterday\b", normalized, re.IGNORECASE):
        correction = "For a finished action yesterday, use the past-tense form of the verb."
        response = "Good effort. What happened after that?"
    elif normalized.endswith("?"):
        response = "That is a good question. What answer do you expect?"

    if correction and include_telugu_explanation:
        correction += " తెలుగు: నిన్న పూర్తైన పనికి past tense వాడాలి."
    return TutorTurn(response=response, correction=correction)
