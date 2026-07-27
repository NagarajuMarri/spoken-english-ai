from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    opening_prompt: str


SCENARIOS = (
    Scenario("daily-conversation", "Daily Conversation", "Hello! How has your day been so far?"),
    Scenario("workplace-english", "Workplace English", "Tell me about what you are working on today."),
    Scenario("job-interview", "Job Interview", "Please tell me a little about yourself."),
    Scenario("travel", "Travel", "Where would you like to travel, and why?"),
    Scenario("shopping", "Shopping", "What would you like to buy today?"),
    Scenario("doctor-visit", "Doctor Visit", "How would you describe how you are feeling?"),
    Scenario("telephone-conversation", "Telephone Conversation", "Hello, how may I help you today?"),
    Scenario("free-talk", "Free Talk", "What would you enjoy talking about?"),
)

SCENARIOS_BY_ID = {scenario.id: scenario for scenario in SCENARIOS}
