from backend.app.ai.models import AIConversationResponse, LearningSignals, UsageInfo


class DeterministicAIProvider:
    name = "deterministic"
    supported_scenarios = {
        "greeting", "self-introduction", "family", "school", "workplace",
        "shopping", "travel", "daily-routine", "daily-conversation",
    }

    def generate(self, request):
        scenario = request.scenario if request.scenario in self.supported_scenarios else "daily-conversation"
        cleaned = request.current_learner_message.strip()
        corrected = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
        if corrected and corrected[-1] not in ".!?":
            corrected += "."
        vocabulary = {
            "travel": ["itinerary", "destination"],
            "shopping": ["affordable", "receipt"],
            "workplace": ["collaborate", "deadline"],
            "school": ["assignment", "curious"],
        }.get(scenario, ["confident", "practice"])
        return AIConversationResponse(
            tutor_message=f"Thanks for sharing. {corrected}",
            corrected_learner_sentence=corrected,
            correction_explanation="Start with a capital letter and finish the sentence clearly.",
            grammar_feedback=["sentence boundaries"],
            vocabulary_suggestions=vocabulary,
            conversation_question=f"What would you like to say next about {scenario.replace('-', ' ')}?",
            encouragement="Good effort—keep going.",
            detected_level=request.learner_level,
            recommended_next_difficulty=request.learner_level,
            learning_signals=LearningSignals(
                grammar_focus=["sentence boundaries"],
                vocabulary=vocabulary,
                confidence=60,
                fluency=55,
            ),
            provider_metadata_reference="deterministic:v1",
            usage=UsageInfo(input_units=len(cleaned.split()), output_units=35),
        )
