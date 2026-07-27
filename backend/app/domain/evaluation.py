from dataclasses import dataclass
import re


@dataclass(frozen=True)
class EvaluationResult:
    grammar_score: int
    vocabulary_score: int
    fluency_score: int
    task_completion_score: int
    confidence_score: int
    overall_score: int
    strengths: list[str]
    priority_improvements: list[str]
    corrected_examples: list[str]


def evaluate(messages) -> EvaluationResult:
    texts = [message.learner_text.strip() for message in messages]
    words = [word.lower() for text in texts for word in re.findall(r"[A-Za-z']+", text)]
    corrections = [message.correction_summary for message in messages if message.correction_summary]
    turns = len(texts)
    grammar = max(0, min(100, 85 - 12 * len(corrections) + min(turns, 3) * 3))
    vocabulary = max(0, min(100, 45 + len(set(words)) * 3))
    avg_words = len(words) / turns if turns else 0
    fluency = max(0, min(100, int(40 + min(avg_words, 15) * 4)))
    task = max(0, min(100, 30 + turns * 25))
    confidence = max(0, min(100, 45 + turns * 15))
    overall = round((grammar + vocabulary + fluency + task + confidence) / 5)
    strengths = ["You completed the conversation turns."] if turns else []
    if len(set(words)) >= 8:
        strengths.append("You used a useful range of words.")
    improvements = ["Practise the corrected sentence once more."] if corrections else ["Add more detail to each answer."]
    return EvaluationResult(grammar, vocabulary, fluency, task, confidence, overall, strengths, improvements, corrections[:2])
