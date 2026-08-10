from dataclasses import dataclass
from datetime import date

from backend.app.domain.enums import LearningGoal, ProficiencyLevel


@dataclass(frozen=True)
class CurriculumLesson:
    id: str
    title: str
    category: str
    proficiency_level: ProficiencyLevel
    scenario_id: str
    learning_objectives: tuple[str, ...]
    target_vocabulary: tuple[str, ...]
    grammar_focus: tuple[str, ...]
    estimated_duration_minutes: int
    completion_criteria: str
    instruction_prompt: str
    practice_prompt: str
    roleplay_prompt: str


def _lesson(level, category, suffix, title, scenario, vocabulary, grammar, practice, roleplay):
    return CurriculumLesson(
        id=f"{level.value.lower().replace('_', '-')}-{suffix}",
        title=title,
        category=category,
        proficiency_level=level,
        scenario_id=scenario,
        learning_objectives=(f"Complete a {title.lower()} exchange", "Respond without translation prompts"),
        target_vocabulary=tuple(vocabulary),
        grammar_focus=tuple(grammar),
        estimated_duration_minutes=10,
        completion_criteria="Complete at least two learner turns and finish the lesson session.",
        instruction_prompt=(
            f"Welcome to {title}. Today we will practise {', '.join(vocabulary[:2])}. "
            f"{practice}"
        ),
        practice_prompt=practice,
        roleplay_prompt=roleplay,
    )


_LESSON_SPECS = (
    ("introductions", "introductions", "Simple Introductions", "daily-conversation", ["hello", "name", "live"], ["be", "subject pronouns"], "Tell me your name and where you live.", "Meet a new neighbour and introduce yourself."),
    ("introductions", "family", "Talking About Family", "daily-conversation", ["family", "sister", "brother"], ["have/has", "possessives"], "Tell me about one person in your family.", "Introduce a family member to a friend."),
    ("introductions", "hometown", "My Hometown", "daily-conversation", ["hometown", "near", "famous"], ["be", "there is"], "Describe your hometown in two short sentences.", "Help a visitor learn about your town."),
    ("introductions", "likes", "Likes and Interests", "free-talk", ["like", "enjoy", "favourite"], ["simple present", "gerunds"], "Tell me one activity you enjoy.", "Find a shared interest with a new friend."),
    ("introductions", "small-talk", "Friendly Small Talk", "free-talk", ["weather", "weekend", "today"], ["present simple", "question forms"], "Ask me one friendly small-talk question.", "Start a short conversation while waiting in a queue."),
    ("daily-life", "routine", "My Daily Routine", "daily-conversation", ["usually", "morning", "evening"], ["simple present", "time expressions"], "Describe what you usually do in the morning.", "Compare morning routines with a friend."),
    ("daily-life", "time", "Telling the Time", "daily-conversation", ["o'clock", "half past", "quarter"], ["time expressions", "at"], "Tell me when you start work or study.", "Arrange a meeting time with a friend."),
    ("daily-life", "home", "Activities at Home", "daily-conversation", ["cook", "clean", "relax"], ["simple present", "frequency adverbs"], "Tell me what you do after coming home.", "Plan household tasks with a family member."),
    ("daily-life", "weekend", "Weekend Plans", "daily-conversation", ["plan", "visit", "rest"], ["going to", "future time"], "Tell me one plan for this weekend.", "Invite a friend to join your weekend plan."),
    ("daily-life", "yesterday", "What I Did Yesterday", "daily-conversation", ["went", "finished", "watched"], ["past simple", "sequence words"], "Tell me two things you did yesterday.", "Share yesterday's highlights with a friend."),
    ("shopping", "shopping", "Buying One Item", "shopping", ["want", "price", "please"], ["this/that", "simple questions"], "Ask the price of an item you want.", "Buy a notebook from me at a shop."),
    ("shopping", "sizes", "Choosing a Size", "shopping", ["size", "fit", "larger"], ["comparatives", "could I"], "Ask for a different clothing size.", "Try on a shirt and ask the shop assistant for help."),
    ("shopping", "market", "At the Market", "shopping", ["fresh", "kilo", "cost"], ["how much", "countable nouns"], "Buy one kilo of fruit from me.", "Compare two prices at a market stall."),
    ("shopping", "returns", "Returning an Item", "shopping", ["return", "receipt", "exchange"], ["past simple", "would like"], "Explain why you want to return an item.", "Request an exchange politely."),
    ("shopping", "online-order", "Checking an Online Order", "telephone-conversation", ["order", "delivery", "tracking"], ["present perfect", "polite questions"], "Ask when your order will arrive.", "Call customer support about a delayed order."),
    ("travel", "directions", "Asking for Directions", "travel", ["left", "right", "near"], ["where questions", "imperatives"], "Ask how to reach the nearest bus stop.", "Follow directions to a railway station."),
    ("travel", "transport", "Using Public Transport", "travel", ["ticket", "platform", "fare"], ["which/when questions", "prepositions"], "Ask which bus goes to the city centre.", "Buy a train ticket from the counter."),
    ("travel", "hotel", "Checking Into a Hotel", "travel", ["booking", "room", "passport"], ["have got", "polite requests"], "Tell the receptionist about your booking.", "Check into a hotel and ask about breakfast."),
    ("travel", "airport", "At the Airport", "travel", ["boarding", "gate", "luggage"], ["present continuous", "where questions"], "Ask where your boarding gate is.", "Check in your luggage with airline staff."),
    ("travel", "trip-plan", "Planning a Short Trip", "travel", ["visit", "stay", "return"], ["going to", "future forms"], "Describe a simple two-day trip plan.", "Choose a destination with a friend."),
    ("work", "work-update", "Giving a Work Update", "workplace-english", ["progress", "deadline", "complete"], ["present continuous", "future forms"], "Give a two-sentence update about your work.", "Update your manager in a short meeting."),
    ("work", "schedule", "Discussing a Schedule", "workplace-english", ["available", "meeting", "reschedule"], ["can/could", "time prepositions"], "Say when you are available for a meeting.", "Reschedule a meeting with a colleague."),
    ("work", "help", "Asking a Colleague for Help", "workplace-english", ["help", "explain", "problem"], ["could you", "because"], "Ask politely for help with a task.", "Explain a small work problem to a colleague."),
    ("work", "phone-update", "A Short Work Call", "telephone-conversation", ["calling", "update", "confirm"], ["present continuous", "polite openings"], "Introduce yourself and state why you are calling.", "Give a project update over the phone."),
    ("work", "interview", "Basic Job Interview", "job-interview", ["experience", "skills", "responsible"], ["past simple", "present simple"], "Tell me about one useful skill you have.", "Answer two questions in a job interview."),
    ("health", "doctor", "Describing Symptoms", "doctor-visit", ["pain", "since", "better"], ["present perfect basics", "duration"], "Describe one symptom and when it started.", "Talk to a doctor about how you feel."),
    ("health", "appointment", "Making an Appointment", "telephone-conversation", ["appointment", "available", "morning"], ["would like", "time questions"], "Ask for a doctor's appointment.", "Choose an available appointment time by phone."),
    ("health", "pharmacy", "At the Pharmacy", "doctor-visit", ["medicine", "cold", "dose"], ["have got", "how often"], "Tell the pharmacist about a simple cold.", "Ask how often to take a medicine."),
    ("health", "healthy-habits", "Healthy Habits", "daily-conversation", ["exercise", "sleep", "water"], ["should", "frequency adverbs"], "Describe one healthy habit you follow.", "Suggest a healthy habit to a friend."),
    ("health", "feeling-better", "Checking How Someone Feels", "daily-conversation", ["better", "rest", "recover"], ["feel + adjective", "past simple"], "Ask me if I am feeling better.", "Check on a friend who was unwell."),
    ("telephone", "telephone", "Starting a Phone Call", "telephone-conversation", ["speaking", "calling", "available"], ["phone openings", "may I"], "Introduce yourself on a phone call.", "Call a friend and ask if they can talk."),
    ("telephone", "message", "Leaving a Message", "telephone-conversation", ["message", "call back", "number"], ["can/could", "reported requests"], "Leave a short message for someone.", "Ask a receptionist to pass on your message."),
    ("telephone", "clarify", "Asking for Clarification", "telephone-conversation", ["repeat", "slowly", "confirm"], ["could you", "indirect questions"], "Ask the caller to repeat something slowly.", "Confirm a phone number and appointment time."),
    ("telephone", "support", "Calling Customer Support", "telephone-conversation", ["issue", "account", "resolve"], ["present simple", "polite requests"], "State your problem clearly in one sentence.", "Call support about an account issue."),
    ("telephone", "emergency-call", "Making an Urgent Call", "telephone-conversation", ["urgent", "location", "help"], ["imperatives", "there is"], "State what help is needed and your location.", "Make a clear urgent call without extra detail."),
    ("social", "invitation", "Inviting a Friend", "free-talk", ["join", "free", "together"], ["would you like", "future time"], "Invite me to a simple activity.", "Plan tea or coffee with a friend."),
    ("social", "accept-decline", "Accepting or Declining", "free-talk", ["sounds good", "sorry", "another time"], ["can/can't", "because"], "Accept or decline an invitation politely.", "Respond to two different invitations."),
    ("social", "opinions", "Sharing a Simple Opinion", "free-talk", ["think", "prefer", "because"], ["opinion phrases", "comparatives"], "Say which of two activities you prefer and why.", "Choose a film with a friend."),
    ("social", "apology", "A Simple Apology", "free-talk", ["sorry", "late", "understand"], ["past simple", "because"], "Apologize for being late and give a reason.", "Respond kindly to a friend's apology."),
    ("social", "goodbye", "Ending a Conversation", "free-talk", ["nice", "again", "take care"], ["conversation closings", "future forms"], "End our conversation naturally.", "Say goodbye after meeting someone new."),
)


LESSONS = tuple(
    _lesson(
        ProficiencyLevel.STARTER if index % 5 < 2 else ProficiencyLevel.BEGINNER,
        category, suffix, title, scenario, vocabulary, grammar, practice, roleplay,
    )
    for index, (category, suffix, title, scenario, vocabulary, grammar, practice, roleplay)
    in enumerate(_LESSON_SPECS)
)
LESSONS_BY_ID = {lesson.id: lesson for lesson in LESSONS}
GOAL_SCENARIOS = {
    LearningGoal.DAILY_CONVERSATION: {"daily-conversation", "shopping", "telephone-conversation"},
    LearningGoal.JOB_INTERVIEW: {"job-interview", "workplace-english"},
    LearningGoal.WORKPLACE: {"workplace-english", "telephone-conversation"},
    LearningGoal.TRAVEL: {"travel", "shopping"},
    LearningGoal.GENERAL_FLUENCY: {lesson.scenario_id for lesson in LESSONS},
}


def select_daily_lesson(level, goal, completed_ids, recent_ids, current_date: date):
    level_lessons = [lesson for lesson in LESSONS if lesson.proficiency_level == level]
    goal_matches = [lesson for lesson in level_lessons if lesson.scenario_id in GOAL_SCENARIOS[goal]]
    pool = goal_matches or level_lessons
    incomplete = [lesson for lesson in pool if lesson.id not in completed_ids]
    pool = incomplete or pool
    not_recent = [lesson for lesson in pool if lesson.id not in recent_ids]
    pool = not_recent or pool
    return sorted(pool, key=lambda item: item.id)[current_date.toordinal() % len(pool)]
