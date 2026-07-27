from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScenarioRead(BaseModel):
    id: str
    name: str
    opening_prompt: str


class ConversationCreate(BaseModel):
    learner_id: str
    scenario_id: str


class LearnerMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    include_telugu_explanation: bool = False


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    turn_number: int
    learner_text: str
    tutor_response: str
    correction_summary: str | None
    created_at: datetime


class MessageResult(BaseModel):
    tutor_response: str
    turn_number: int
    transcript_entry: MessageRead
    correction_summary: str | None


class ConversationRead(BaseModel):
    id: str
    learner_id: str
    scenario_id: str
    opening_prompt: str
    created_at: datetime
    messages: list[MessageRead]
