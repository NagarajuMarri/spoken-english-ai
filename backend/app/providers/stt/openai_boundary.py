from __future__ import annotations

import json
import secrets
from urllib import error, request as urllib_request

from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.providers.stt.contracts import SpeechToTextResult


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
                    return json.loads(response.read())
            except TimeoutError:
                if attempt == values["max_retries"]:
                    raise
            except error.HTTPError as exc:
                raise RuntimeError("OpenAI transcription request failed.") from exc
            except (error.URLError, json.JSONDecodeError, KeyError, TypeError) as exc:
                if attempt == values["max_retries"]:
                    raise RuntimeError("OpenAI transcription request failed.") from exc
        raise RuntimeError("OpenAI transcription request failed.")


class OpenAICompatibleSTTProvider:
    def __init__(self, client, *, model: str, timeout_seconds=30, max_retries=2):
        if not model or not 0 <= max_retries <= 3:
            raise ValueError("Unsafe STT configuration.")
        self.client, self.model = client, model
        self.timeout_seconds, self.max_retries = timeout_seconds, max_retries

    def transcribe(self, request):
        if not request.audio_bytes:
            raise ProviderUnavailable("Speech audio is unavailable.")
        try:
            value = self.client.transcribe(
                model=self.model,
                audio_bytes=request.audio_bytes,
                filename=request.filename,
                content_type=request.content_type,
                language=request.language_hint,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
            transcript = str(value.get("text", "")).strip()
            if not transcript:
                raise ValueError("No speech was detected.")
            return SpeechToTextResult(
                transcript=transcript,
                detected_language=str(value.get("language") or request.language_hint),
                confidence=None,
                provider_job_id=str(value.get("id") or "openai-transcription")[:100],
                duration_seconds=float(value.get("duration") or request.duration_seconds),
                usage_units=request.duration_seconds,
                processing_status="SUCCEEDED",
            )
        except TimeoutError as exc:
            raise ProviderTimeout("Speech provider timed out.") from exc
        except ValueError:
            raise
        except Exception as exc:
            raise ProviderUnavailable("Speech provider unavailable.") from exc
