import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.db.session import get_db
from backend.app.integrations.llm import RuleBasedLLMProvider
from backend.app.models import ConversationMessage, RealtimeTurn
from backend.app.repositories.conversations import ConversationRepository, TurnSequenceConflict
from backend.app.services.conversations import ConversationService
from backend.app.unicode_safety import UnicodeSafetyError, normalize_input_text, normalize_output_text

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])
logger = logging.getLogger("spoken_english.realtime")


class RealtimeEventCreate(BaseModel):
    event_type: str = Field(pattern="^(learner_transcript|tutor_transcript|tutor_interrupted)$")
    learner_item_id: str = Field(min_length=1, max_length=100)
    response_id: str | None = Field(default=None, max_length=100)
    transcript: str | None = Field(default=None, max_length=10_000)


def _analyse_realtime_turn(session_factory, turn_id: str) -> None:
    """Runs after the event response; it never creates a provider voice response."""
    with session_factory() as db:
        turn = db.get(RealtimeTurn, turn_id)
        if turn is None or turn.analysis_status == "COMPLETED":
            return
        try:
            result = RuleBasedLLMProvider().generate_tutor_response(turn.learner_transcript, False)
            turn.correction_summary = result.correction
            turn.analysis_status = "COMPLETED"
            if turn.conversation_message_id:
                message = db.get(ConversationMessage, turn.conversation_message_id)
                if message is not None:
                    message.correction_summary = turn.correction_summary
            db.commit()
            if turn.tutor_status == "COMPLETED":
                _mirror_completed_turn(db, turn)
        except Exception:
            db.rollback()
            logger.exception("realtime_turn_analysis_failed turn_id=%s", turn_id)


def _mirror_completed_turn(db: Session, turn: RealtimeTurn) -> None:
    if turn.conversation_message_id or turn.tutor_status != "COMPLETED" or not turn.tutor_transcript:
        return
    try:
        message = ConversationRepository(db).add_message(
            turn.conversation_id,
            turn.learner_transcript,
            turn.tutor_transcript,
            turn.correction_summary,
            commit=False,
        )
        turn.conversation_message_id = message.id
        db.commit()
    except TurnSequenceConflict:
        db.rollback()
        raise AppError(status.HTTP_409_CONFLICT, "turn_sequence_conflict", "The live turn could not be finalized yet.", retryable=True)


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def persist_realtime_event(
    data: RealtimeEventCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    conversation_id: str = Query(min_length=1, max_length=100),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    conversation = ConversationService(db).get(conversation_id)
    ensure_owner(conversation.learner_id, principal)
    turn = db.scalar(select(RealtimeTurn).where(
        RealtimeTurn.conversation_id == conversation_id,
        RealtimeTurn.learner_item_id == data.learner_item_id,
    ))
    if data.event_type == "learner_transcript":
        try:
            transcript = normalize_input_text((data.transcript or "").strip())
        except UnicodeSafetyError as exc:
            raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_realtime_transcript", "The live transcript could not be validated.") from exc
        if not transcript:
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_realtime_transcript", "The live transcript is empty.")
        if turn is None:
            turn = RealtimeTurn(conversation_id=conversation_id, learner_item_id=data.learner_item_id, learner_transcript=transcript)
            db.add(turn)
            db.commit()
            db.refresh(turn)
        elif turn.learner_transcript != transcript:
            raise AppError(status.HTTP_409_CONFLICT, "realtime_event_conflict", "This live turn was already persisted with different content.")
        if turn.analysis_status == "PENDING":
            background_tasks.add_task(_analyse_realtime_turn, request.app.state.session_factory, turn.id)
    else:
        if turn is None:
            raise AppError(status.HTTP_409_CONFLICT, "realtime_learner_turn_missing", "The learner transcript has not arrived yet.", retryable=True)
        if data.event_type == "tutor_interrupted":
            turn.tutor_status = "INTERRUPTED"
            if data.response_id:
                turn.tutor_response_id = data.response_id
            db.commit()
        else:
            try:
                transcript = normalize_output_text((data.transcript or "").strip(), allow_telugu=True)
            except UnicodeSafetyError as exc:
                raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_realtime_transcript", "The tutor transcript could not be validated.") from exc
            if not transcript or not data.response_id:
                raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "incomplete_realtime_event", "The tutor event is incomplete.")
            if turn.tutor_status == "INTERRUPTED" and turn.tutor_response_id == data.response_id:
                return {"accepted": True, "turn_id": turn.id, "analysis_status": turn.analysis_status}
            if turn.tutor_response_id and turn.tutor_response_id != data.response_id:
                raise AppError(status.HTTP_409_CONFLICT, "realtime_event_conflict", "This live turn already has a tutor response.")
            turn.tutor_response_id = data.response_id
            turn.tutor_transcript = transcript
            turn.tutor_status = "COMPLETED"
            db.commit()
            _mirror_completed_turn(db, turn)
    return {"accepted": True, "turn_id": turn.id, "analysis_status": turn.analysis_status}


@router.get("/turns/{learner_item_id}")
def get_realtime_turn(
    learner_item_id: str,
    conversation_id: str = Query(min_length=1, max_length=100),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    conversation = ConversationService(db).get(conversation_id)
    ensure_owner(conversation.learner_id, principal)
    turn = db.scalar(select(RealtimeTurn).where(
        RealtimeTurn.conversation_id == conversation_id,
        RealtimeTurn.learner_item_id == learner_item_id,
    ))
    if turn is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "realtime_turn_not_found", "The live turn is still being processed.", retryable=True)
    return {
        "turn_id": turn.id,
        "analysis_status": turn.analysis_status,
        "correction_summary": turn.correction_summary,
        "tutor_status": turn.tutor_status,
    }


@router.get("/capability")
def realtime_capability(request: Request, _: Principal = Depends(current_principal)):
    settings = request.app.state.settings
    return {"enabled": bool(settings.realtime_voice_enabled and settings.openai_api_key), "maximum_session_seconds": settings.realtime_max_session_seconds, "idle_session_seconds": settings.realtime_idle_session_seconds}


def _instructions(language_mode: str, lesson_id: str | None) -> str:
    telugu = language_mode != "ENGLISH"
    language = (
        "Keep the learning sentence in English. Give brief, natural Telugu help only when the learner uses Telugu or asks for it, and write "
        "that help in Telugu script rather than Latin transliteration; "
        "never output Kannada, Cyrillic, Chinese, Arabic, or Urdu script."
        if telugu else
        "Teach in concise, friendly Indian English."
    )
    lesson = f" Current structured lesson id: {lesson_id}. Do not skip its stages." if lesson_id else ""
    return (
        "You are Ananya, SpeakMate's warm Indian spoken-English tutor. Keep ordinary replies to one or two "
        "short sentences. Do not overcorrect valid English. For an obvious error, give one concise correction "
        "and invite one retry. Accept 'My day is good.' and 'I am Nagaraj.' as valid; do not replace them with stylistic alternatives. "
        "Treat the learner's latest factual statement as authoritative, including a changed hometown. When the learner asks how to say "
        "something in English, immediately give the exact natural English translation, then at most one short Telugu explanation; never use a "
        "placeholder such as 'let us turn that into English'. Never create duplicate answers. " + language + lesson
    )


def _multipart(sdp: bytes, session: dict) -> tuple[bytes, str]:
    boundary = f"speakmate-{secrets.token_hex(16)}"
    body = bytearray()
    for name, value, content_type in (
        ("sdp", sdp, "application/sdp"),
        ("session", json.dumps(session, separators=(",", ":")).encode(), "application/json"),
    ):
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n".encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(value)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


@router.post("/calls", response_class=Response)
async def create_realtime_call(
    request: Request,
    conversation_id: str = Query(min_length=1, max_length=100),
    language_mode: str = Query(default="ENGLISH", pattern="^(ENGLISH|ENGLISH_TELUGU|TELUGU_DOMINANT)$"),
    lesson_id: str | None = Query(default=None, max_length=100),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    conversation = ConversationService(db).get(conversation_id)
    ensure_owner(conversation.learner_id, principal)
    settings = request.app.state.settings
    if not settings.realtime_voice_enabled or not settings.openai_api_key:
        raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "realtime_unavailable", "Live voice is temporarily unavailable. Use text mode or retry.", retryable=True)
    sdp = await request.body()
    if not sdp or len(sdp) > settings.realtime_sdp_max_bytes or b"v=" not in sdp[:100]:
        raise AppError(status.HTTP_400_BAD_REQUEST, "realtime_invalid_offer", "The live voice connection could not be started.", retryable=False)
    session = {
        "type": "realtime",
        "model": settings.openai_realtime_model,
        "instructions": _instructions(language_mode, lesson_id),
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transcription": {"model": settings.openai_stt_model},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": settings.realtime_vad_threshold,
                    "prefix_padding_ms": settings.realtime_vad_prefix_padding_ms,
                    "silence_duration_ms": settings.realtime_vad_silence_ms,
                    "create_response": True,
                    "interrupt_response": True,
                }
            },
            "output": {"voice": settings.openai_realtime_voice},
        },
    }
    body, boundary = _multipart(sdp, session)
    safety_identifier = hashlib.sha256(f"{settings.jwt_issuer}:{principal.user.id}".encode()).hexdigest()
    upstream = urllib.request.Request(
        "https://api.openai.com/v1/realtime/calls",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "OpenAI-Safety-Identifier": safety_identifier,
        },
    )
    try:
        with urllib.request.urlopen(upstream, timeout=settings.openai_realtime_connect_timeout_seconds) as result:
            answer = result.read(settings.realtime_sdp_max_bytes)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        logger.warning("realtime_connection_failed request_id=%s upstream_status=%s", getattr(request.state, "request_id", "unknown"), getattr(exc, "code", "connection"))
        raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "realtime_unavailable", "Live voice is temporarily unavailable. Use text mode or retry.", retryable=True) from exc
    if not answer or b"v=" not in answer[:100]:
        raise AppError(status.HTTP_502_BAD_GATEWAY, "realtime_invalid_answer", "Live voice is temporarily unavailable. Use text mode or retry.", retryable=True)
    return Response(content=answer, media_type="application/sdp", headers={"Cache-Control": "no-store"})
