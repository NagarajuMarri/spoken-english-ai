from __future__ import annotations

import json
import secrets
from urllib import error, request as urllib_request

from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.providers.stt.contracts import SpeechToTextResult


class OpenAITranscriptionTimeout(TimeoutError):
    def __init__(self, provider_requests: int):
        super().__init__("OpenAI transcription timed out.")
        self.provider_requests = provider_requests


class OpenAITranscriptionFailure(RuntimeError):
    def __init__(self, provider_requests: int):
        super().__init__("OpenAI transcription request failed.")
        self.provider_requests = provider_requests


class OpenAITranscriptionRejected(ValueError):
    def __init__(self, message: str, provider_requests: int):
        super().__init__(message)
        self.provider_requests = provider_requests


class OpenAITranscriptionHTTPClient:
    """Small, dependency-free adapter for OpenAI's multipart transcription API."""

    endpoint = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, api_key: str, opener=urllib_request.urlopen):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.opener = opener

    @staticmethod
    def _multipart(*, model: str, audio: bytes, filename: str, content_type: str, language: str) -> tuple[bytes, str]:
        boundary = f"----speakmate-{secrets.token_hex(16)}"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n{language}\r\n".encode(),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
            ).encode(),
            audio,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        return b"".join(parts), boundary

    def transcribe(self, **values):
        body, boundary = self._multipart(
            model=values["model"], audio=values["audio_bytes"], filename=values["filename"],
            content_type=values["content_type"], language=values["language"],
        )
        outgoing = urllib_request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        for attempt in range(values["max_retries"] + 1):
            try:
                with self.opener(outgoing, timeout=values["timeout"]) as response:
                    return json.loads(response.read()), attempt + 1
            except TimeoutError:
                if attempt == values["max_retries"]:
                    raise OpenAITranscriptionTimeout(attempt + 1) from None
            except error.HTTPError as exc:
                raise OpenAITranscriptionFailure(attempt + 1) from exc
            except (error.URLError, json.JSONDecodeError, KeyError, TypeError) as exc:
                if attempt == values["max_retries"]:
                    raise OpenAITranscriptionFailure(attempt + 1) from exc
        raise OpenAITranscriptionFailure(values["max_retries"] + 1)


class OpenAICompatibleSTTProvider:
    def __init__(self, client, *, model: str, timeout_seconds=30, max_retries=2):
        if not model or not 0 <= max_retries <= 3:
            raise ValueError("Unsafe STT configuration.")
        self.client, self.model = client, model
        self.timeout_seconds, self.max_retries = timeout_seconds, max_retries

    def transcribe(self, request):
        if not request.audio_bytes:
            raise ProviderUnavailable("Speech audio is unavailable.")
        provider_requests = 1
        try:
            response = self.client.transcribe(
                model=self.model,
                audio_bytes=request.audio_bytes,
                filename=request.filename,
                content_type=request.content_type,
                language=request.language_hint,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
            if isinstance(response, tuple):
                value, provider_requests = response
            else:
                value, provider_requests = response, 1
            transcript = str(value.get("text", "")).strip()
            if not transcript:
                raise OpenAITranscriptionRejected(
                    "No speech was detected.",
                    provider_requests,
                )
            return SpeechToTextResult(
                transcript=transcript,
                detected_language=str(value.get("language") or request.language_hint),
                confidence=None,
                provider_job_id=str(value.get("id") or "openai-transcription")[:100],
                duration_seconds=float(value.get("duration") or request.maximum_duration_seconds),
                usage_units=float(value.get("duration") or request.maximum_duration_seconds),
                provider_requests=provider_requests,
                processing_status="SUCCEEDED",
            )
        except OpenAITranscriptionTimeout as exc:
            raise ProviderTimeout(
                "Speech provider timed out.",
                provider_requests=exc.provider_requests,
            ) from exc
        except OpenAITranscriptionRejected:
            raise
        except OpenAITranscriptionFailure as exc:
            raise ProviderUnavailable(
                "Speech provider unavailable.",
                provider_requests=exc.provider_requests,
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(
                "Speech provider unavailable.",
                provider_requests=provider_requests,
            ) from exc
