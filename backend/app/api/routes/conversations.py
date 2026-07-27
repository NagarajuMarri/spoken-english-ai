from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

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

router = APIRouter(prefix="/api/v1", tags=["conversation"])


@router.get("/scenarios", response_model=list[ScenarioRead])
def list_scenarios():
    return SCENARIOS


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(data: ConversationCreate, session: Session = Depends(get_db)):
    conversation = ConversationService(session).create(data.learner_id, data.scenario_id)
    return {
        **conversation.__dict__,
        "opening_prompt": SCENARIOS_BY_ID[conversation.scenario_id].opening_prompt,
        "messages": [],
    }


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResult)
def add_message(
    conversation_id: str,
    data: LearnerMessageCreate,
    session: Session = Depends(get_db),
):
    message = ConversationService(session).add_message(
        conversation_id, data.text, data.include_telugu_explanation
    )
    return {
        "tutor_response": message.tutor_response,
        "turn_number": message.turn_number,
        "transcript_entry": message,
        "correction_summary": message.correction_summary,
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: str, session: Session = Depends(get_db)):
    conversation = ConversationService(session).get(conversation_id)
    return {
        **conversation.__dict__,
        "opening_prompt": SCENARIOS_BY_ID[conversation.scenario_id].opening_prompt,
        "messages": conversation.messages,
    }
