import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.db.session import get_db
from backend.app.services.conversations import ConversationService

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])
logger = logging.getLogger("spoken_english.realtime")


@router.get("/capability")
def realtime_capability(request: Request, _: Principal = Depends(current_principal)):
    settings = request.app.state.settings
    return {"enabled": bool(settings.realtime_voice_enabled and settings.openai_api_key)}


def _instructions(language_mode: str, lesson_id: str | None) -> str:
    telugu = language_mode != "ENGLISH"
    language = (
        "Keep the learning sentence in English. Give brief, natural Telugu help when useful; "
        "never output Kannada, Cyrillic, Chinese, Arabic, or Urdu script."
        if telugu else
        "Teach in concise, friendly Indian English."
    )
    lesson = f" Current structured lesson id: {lesson_id}. Do not skip its stages." if lesson_id else ""
    return (
        "You are Ananya, SpeakMate's warm Indian spoken-English tutor. Keep ordinary replies to one or two "
        "short sentences. Do not overcorrect valid English. For an obvious error, give one concise correction "
        "and invite one retry. Never create duplicate answers. " + language + lesson
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
