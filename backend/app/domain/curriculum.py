from dataclasses import dataclass
from datetime import date

from backend.app.domain.enums import LearningGoal, ProficiencyLevel


@dataclass(frozen=True)
class CurriculumLesson:
    id: str
    title: str
    proficiency_level: ProficiencyLevel
    scenario_id: str
    learning_objectives: tuple[str, ...]
    target_vocabulary: tuple[str, ...]
    grammar_focus: tuple[str, ...]
    estimated_duration_minutes: int
    completion_criteria: str


def _lesson(level, suffix, title, scenario, vocabulary, grammar):
    return CurriculumLesson(
        id=f"{level.value.lower().replace('_', '-')}-{suffix}",
        title=title,
        proficiency_level=level,
        scenario_id=scenario,
        learning_objectives=(f"Complete a {title.lower()} exchange", "Respond without translation prompts"),
        target_vocabulary=tuple(vocabulary),
        grammar_focus=tuple(grammar),
        estimated_duration_minutes=10,
        completion_criteria="Complete at least two learner turns and finish the lesson session.",
    )


LESSONS = (
    _lesson(ProficiencyLevel.STARTER, "introductions", "Simple Introductions", "daily-conversation", ["hello", "name", "live"], ["be", "subject pronouns"]),
    _lesson(ProficiencyLevel.STARTER, "shopping", "Buying One Item", "shopping", ["want", "price", "please"], ["this/that", "simple questions"]),
    _lesson(ProficiencyLevel.BEGINNER, "routine", "My Daily Routine", "daily-conversation", ["usually", "morning", "evening"], ["simple present", "time expressions"]),
    _lesson(ProficiencyLevel.BEGINNER, "travel", "Asking for Directions", "travel", ["left", "right", "near"], ["where questions", "imperatives"]),
    _lesson(ProficiencyLevel.ELEMENTARY, "work-update", "Giving a Work Update", "workplace-english", ["progress", "deadline", "complete"], ["past simple", "future forms"]),
    _lesson(ProficiencyLevel.ELEMENTARY, "doctor", "Describing Symptoms", "doctor-visit", ["pain", "since", "better"], ["present perfect basics", "duration"]),
    _lesson(ProficiencyLevel.PRE_INTERMEDIATE, "interview", "Interview Experience", "job-interview", ["responsibility", "achievement", "challenge"], ["past narrative", "linking words"]),
    _lesson(ProficiencyLevel.PRE_INTERMEDIATE, "telephone", "Clarifying by Phone", "telephone-conversation", ["confirm", "repeat", "available"], ["indirect questions", "modals"]),
    _lesson(ProficiencyLevel.INTERMEDIATE, "workplace", "Proposing an Improvement", "workplace-english", ["proposal", "impact", "trade-off"], ["conditionals", "discourse markers"]),
    _lesson(ProficiencyLevel.INTERMEDIATE, "free-talk", "Defending an Opinion", "free-talk", ["perspective", "evidence", "however"], ["complex clauses", "hedging"]),
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
