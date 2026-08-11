def safe_prompt_context(request) -> dict:
    """Return only learning context; never credentials, network data, or full stored prompts."""
    return {
        "level": request.learner_level,
        "scenario": request.scenario,
        "topic": request.topic,
        "tutor_id": request.tutor_id,
        "tutor_prompt_profile": request.tutor_prompt_profile,
        "tutor_vocabulary_profile": request.tutor_vocabulary_profile,
        "history": [turn.model_dump() for turn in request.conversation_history[-3:]],
        "message": request.current_learner_message,
        "strengths": request.known_strengths,
        "weaknesses": request.known_weaknesses,
        "recent_corrections": request.recent_corrections,
        "response_limit": request.allowed_response_length,
        "safety_policy": request.safety_policy,
        "correlation_id": request.correlation_id,
    }
