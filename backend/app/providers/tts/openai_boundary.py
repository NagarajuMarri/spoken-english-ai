from __future__ import annotations

import json
from time import perf_counter
from urllib import error, request as urllib_request

from backend.app.ai.exceptions import (
    ProviderConnectionError,
    ProviderMalformedResponse,
    ProviderRateLimited,
    ProviderServiceError,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.providers.tts.contracts import TextToSpeechResult


def _looks_like_mp3(value: bytes) -> bool:
    return len(value) >= 32 and (value.startswith(b"ID3") or (value[0] == 0xFF and value[1] & 0xE0 == 0xE0))


class OpenAISpeechHTTPClient:
    """Dependency-free OpenAI speech client that returns binary audio only."""

    endpoint = "https://api.openai.com/v1/audio/speech"

    def __init__(self, api_key: str, opener=urllib_request.urlopen):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.opener = opener

    def synthesize(self, **values) -> tuple[bytes, str]:
        body = json.dumps({
            "model": values["model"],
            "input": values["text"],
            "voice": values["voice"],
            "instructions": values["instructions"],
            "response_format": values["response_format"],
            "speed": values["speed"],
        }).encode()
        outgoing = urllib_request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with self.opener(outgoing, timeout=values["timeout"]) as response:
                return response.read(), response.headers.get_content_type()
        except TimeoutError as exc:
            raise ProviderTimeout("Speech synthesis timed out.") from exc
        except error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimited("Speech synthesis was rate limited.") from exc
            if 500 <= exc.code <= 599:
                raise ProviderServiceError("Speech synthesis service failed.") from exc
            raise ProviderUnavailable("Speech synthesis request was rejected.") from exc
        except error.URLError as exc:
            raise ProviderConnectionError("Speech synthesis could not connect.") from exc
        except Exception as exc:
            raise ProviderUnavailable("Speech synthesis failed.") from exc


class OpenAICompatibleTTSProvider:
    def __init__(self, client, *, model: str, timeout_seconds=30, max_retries=0, response_format="mp3"):
        if not model or max_retries != 0 or response_format != "mp3":
            raise ValueError("Unsafe TTS configuration.")
        self.client, self.model = client, model
        self.timeout_seconds, self.max_retries = timeout_seconds, max_retries
        self.response_format = response_format

    def synthesize(self, request):
        started = perf_counter()
        audio, provider_content_type = self.client.synthesize(
            model=self.model,
            text=request.text,
            voice=request.voice_reference,
            instructions=request.instructions,
            response_format=self.response_format,
            speed=request.speaking_rate,
            timeout=self.timeout_seconds,
        )
        if not _looks_like_mp3(audio):
            raise ProviderMalformedResponse("Speech provider returned invalid audio.")
        if provider_content_type not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
            raise ProviderMalformedResponse("Speech provider returned an unexpected content type.")
        digest = __import__("hashlib").sha256(audio).hexdigest()[:16]
        return TextToSpeechResult(
            audio_bytes=audio,
            audio_asset_reference=f"ephemeral/openai/{digest}.mp3",
            content_type="audio/mpeg",
            duration_seconds=max(0.1, len(request.text.split()) / 2.5),
            provider_job_id=f"openai-speech:{digest}",
            usage_units=len(request.text),
            provider_requests=1,
            model_reference=self.model,
            voice_reference=request.voice_reference,
            generation_latency_ms=(perf_counter() - started) * 1000,
            generation_status="SUCCEEDED",
        )
