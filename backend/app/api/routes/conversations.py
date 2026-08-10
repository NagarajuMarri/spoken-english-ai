from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.db.session import get_db
from backend.app.domain.scenarios import SCENARIOS, SCENARIOS_BY_ID
from backend.app.schemas.conversations import (
    ConversationCreate,
    ConversationRead,
    LearnerMessageCreate,
    MessageResult,
    ScenarioRead,
)
from backend.app.services.conversations import ConversationService
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.core.errors import AppError
from backend.app.unicode_safety import (
    UnicodeSafetyError,
    normalize_input_text,
    normalize_output_text,
)

router = APIRouter(prefix="/api/v1", tags=["conversation"])


def _safe_conversation_output(value: str, *, learner_text: bool = False) -> str:
    try:
        if learner_text:
            return normalize_input_text(value)
        return normalize_output_text(value, allow_telugu=True)
    except UnicodeSafetyError as exc:
        raise AppError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "conversation_output_invalid",
            "This conversation contains text that cannot be displayed safely.",
            retryable=False,
        ) from exc


def _safe_message_payload(message) -> dict:
    return {
        "id": message.id,
        "turn_number": message.turn_number,
        "learner_text": _safe_conversation_output(
            message.learner_text,
            learner_text=True,
        ),
        "tutor_response": _safe_conversation_output(message.tutor_response),
        "correction_summary": (
            _safe_conversation_output(message.correction_summary)
            if message.correction_summary is not None
            else None
        ),
        "created_at": message.created_at,
    }


@router.get("/scenarios", response_model=list[ScenarioRead])
def list_scenarios():
    return SCENARIOS


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    ensure_owner(data.learner_id, principal)
    RuntimeEntitlementService(
        session,
        request.app.state.commercial_service.config,
    ).enforce_conversation(data.learner_id)
    conversation, opening = ConversationService(session).create(
        data.learner_id, data.scenario_id, data.lesson_id
    )
    return {
        **conversation.__dict__,
        "opening_prompt": opening.result_json["api_result"]["spoken_text"],
        "opening_turn_id": opening.id,
        "messages": [],
    }


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResult)
def add_message(
    conversation_id: str,
    data: LearnerMessageCreate,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    service = ConversationService(session)
    ensure_owner(service.get(conversation_id).learner_id, principal)
    message = service.add_message(
        conversation_id, data.text, data.include_telugu_explanation
    )
    return {
        "tutor_response": message.tutor_response,
        "turn_number": message.turn_number,
        "transcript_entry": message,
        "correction_summary": message.correction_summary,
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    service = ConversationService(session)
    conversation = service.get(conversation_id)
    ensure_owner(conversation.learner_id, principal)
    opening = service.opening(conversation_id)
    opening_prompt = SCENARIOS_BY_ID[conversation.scenario_id].opening_prompt
    if opening is not None:
        opening_prompt = str(
            opening.result_json.get("api_result", {}).get("spoken_text")
            or opening_prompt
        )
    opening_prompt = _safe_conversation_output(opening_prompt)
    return {
        **conversation.__dict__,
        "opening_prompt": opening_prompt,
        "opening_turn_id": opening.id if opening is not None else None,
        "messages": [_safe_message_payload(message) for message in conversation.messages],
    }
