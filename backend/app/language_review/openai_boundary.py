from __future__ import annotations

import json
import logging
import socket
from time import sleep
from typing import cast
from urllib import error, request as urllib_request

from pydantic import ValidationError

from backend.app.ai.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderMalformedResponse,
    ProviderOutputInvalid,
    ProviderTimeout,
)
from backend.app.ai.models import UsageInfo
from backend.app.language_review.models import LanguageReviewResult
from backend.app.providers.llm.openai_boundary import OpenAIResponsesHTTPClient


logger = logging.getLogger("spoken_english.language_review")


LANGUAGE_REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "final_text": {"type": "string", "minLength": 1, "maxLength": 2000},
        "final_correction_explanation": {"type": ["string", "null"], "maxLength": 1000},
        "final_conversation_question": {"type": "string", "minLength": 1, "maxLength": 500},
        "final_encouragement": {"type": "string", "minLength": 1, "maxLength": 300},
        "language_mode": {
            "type": "string",
            "enum": ["ENGLISH", "ENGLISH_TELUGU", "TELUGU_DOMINANT"],
        },
        "review_changed": {"type": "boolean"},
        "review_reason_code": {
            "type": "string",
            "enum": [
                "NOT_REQUIRED",
                "NATURALIZED_TELUGU",
                "IMPROVED_CODE_SWITCHING",
                "SIMPLIFIED_TEACHER_TONE",
            ],
        },
        "preserved_learning_terms": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string"},
        },
        "expression_hint": {
            "type": "string",
            "enum": ["NEUTRAL", "POSITIVE", "ENCOURAGING", "CORRECTIVE"],
        },
    },
    "required": [
        "final_text",
        "final_correction_explanation",
        "final_conversation_question",
        "final_encouragement",
        "language_mode",
        "review_changed",
        "review_reason_code",
        "preserved_learning_terms",
        "expression_hint",
    ],
}


class OpenAILanguageReviewHTTPClient:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, opener=urllib_request.urlopen, sleeper=sleep):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.opener = opener
        self.sleeper = sleeper

    @staticmethod
    def _instructions() -> str:
        return (
            "You are SpeakMate's native Telugu language-quality reviewer, not the content tutor. "
            "Rewrite only the four learner-facing presentation fields. Preserve factual meaning, the "
            "corrected learner sentence, grammar result, learning objective, safety meaning, evaluation, "
            "scores, named entities, numbers, and required learning terms exactly. Never add a new fact or "
            "correction. Use natural contemporary Telugu understood in Andhra Pradesh and Telangana: warm, "
            "conversational, simple, teacher-like, and not literary-heavy. Never translate English word for "
            "word. Avoid machine-translated order, unnecessary Sanskrit-heavy wording, and awkward English "
            "transliteration. In ENGLISH_TELUGU mode, keep the main learning instruction clear in English and "
            "use natural Telugu explanation where it helps. In TELUGU_DOMINANT mode, explain mainly in Telugu "
            "while retaining useful English learning terms such as grammar, tense, sentence, verb, noun, "
            "pronunciation, confidence, fluency, and practice. Do not mix languages randomly. Return only the "
            "requested structured fields and never expose reasoning. The application owns integrity digests; "
            "do not return or invent a digest or any field outside the schema."
        )

    @staticmethod
    def _input(review_request) -> str:
        safe = review_request.model_dump(
            mode="json", exclude={"correlation_id", "source_content_digest"}
        )
        return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))

    def review_structured(
        self,
        review_request,
        *,
        model: str,
        timeout: float,
        max_retries: int,
        reasoning_effort: str,
        max_output_tokens: int,
    ) -> LanguageReviewResult:
        payload = json.dumps({
            "model": model,
            "instructions": self._instructions(),
            "input": [{"role": "user", "content": self._input(review_request)}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "speakmate_native_telugu_review",
                    "strict": True,
                    "schema": LANGUAGE_REVIEW_SCHEMA,
                },
            },
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "store": False,
        }, ensure_ascii=False).encode()
        outgoing = urllib_request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        value = None
        provider_requests = 0
        helper = OpenAIResponsesHTTPClient(self.api_key, self.opener, self.sleeper)
        for attempt in range(max_retries + 1):
            provider_requests += 1
            try:
                with self.opener(outgoing, timeout=timeout) as response:
                    value = json.loads(response.read())
                break
            except (json.JSONDecodeError, TypeError) as exc:
                raise ProviderMalformedResponse(
                    "Language review response body was malformed.",
                    provider_requests=provider_requests,
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                failure: ProviderError = ProviderTimeout(
                    "Language review timed out.", provider_requests=provider_requests,
                )
                if attempt == max_retries:
                    raise failure from exc
                helper._wait_before_retry(failure, attempt)
            except error.HTTPError as exc:
                failure = helper._http_error(exc, provider_requests)
                if not failure.retryable or attempt == max_retries:
                    raise failure from exc
                helper._wait_before_retry(failure, attempt)
            except error.URLError as exc:
                reason = exc.reason
                failure = (
                    ProviderTimeout("Language review timed out.", provider_requests=provider_requests)
                    if isinstance(reason, (TimeoutError, socket.timeout))
                    else ProviderConnectionError(
                        "Language review connection failed.", provider_requests=provider_requests,
                    )
                )
                if attempt == max_retries:
                    raise failure from exc
                helper._wait_before_retry(failure, attempt)
        if not isinstance(value, dict):
            raise ProviderMalformedResponse(
                "Language review response body was malformed.", provider_requests=provider_requests,
            )
        helper._log_response_shape(value)
        content = helper._structured_content(value, provider_requests)
        returned_fields = set(content)
        expected_fields = set(cast(list[str], LANGUAGE_REVIEW_SCHEMA["required"]))
        missing_fields = sorted(expected_fields - returned_fields)
        unexpected_fields = sorted(returned_fields - expected_fields)
        if missing_fields or unexpected_fields:
            shape = helper._response_shape(value)
            path = (
                f"missing.{missing_fields[0]}" if missing_fields
                else f"unexpected.{unexpected_fields[0]}"
            )
            logger.warning(
                "language_review_schema_failure status=%s output_item_types=%s "
                "returned_fields=%s missing_fields=%s unexpected_fields=%s "
                "schema_path=%s classification=validation language_mode=%s",
                shape["status"], shape["output_item_types"],
                ",".join(sorted(returned_fields)) or "none",
                ",".join(missing_fields) or "none",
                ",".join(unexpected_fields) or "none",
                path, review_request.language_mode,
            )
            raise ProviderOutputInvalid(
                "Language review structured output fields were invalid.",
                provider_requests=provider_requests,
                schema_path=path[:200],
            )
        usage = value.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        content["source_content_digest"] = review_request.source_content_digest
        content["provider_metadata_reference"] = (
            f"language-review:{value.get('model') or model}:{value.get('id') or 'response'}"
        )[:100]
        content["usage"] = UsageInfo(
            input_units=int(usage.get("input_tokens") or 0),
            cached_input_units=int(input_details.get("cached_tokens") or 0),
            output_units=int(usage.get("output_tokens") or 0),
            provider_requests=provider_requests,
        ).model_dump()
        try:
            return LanguageReviewResult.model_validate(content)
        except ValidationError as exc:
            known_fields = set(LanguageReviewResult.model_fields)
            first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
            location = tuple(first.get("loc", ()))
            path = ".".join(
                str(part)
                if isinstance(part, int) or (isinstance(part, str) and part in known_fields)
                else "unexpected_field"
                for part in location
            ) or "root"
            shape = helper._response_shape(value)
            logger.warning(
                "language_review_schema_failure status=%s output_item_types=%s "
                "returned_fields=%s missing_fields=%s unexpected_fields=%s "
                "schema_path=%s classification=validation language_mode=%s",
                shape["status"],
                shape["output_item_types"],
                ",".join(sorted(returned_fields)) or "none",
                ",".join(missing_fields) or "none",
                ",".join(unexpected_fields) or "none",
                path[:200],
                review_request.language_mode,
            )
            raise ProviderOutputInvalid(
                "Language review structured output was invalid.",
                provider_requests=provider_requests,
                input_units=int(usage.get("input_tokens") or 0),
                output_units=int(usage.get("output_tokens") or 0),
                schema_path=path[:200],
            ) from exc


class OpenAILanguageReviewProvider:
    name = "openai-native-telugu-review"

    def __init__(
        self,
        client,
        *,
        model: str,
        timeout_seconds: float = 45,
        max_retries: int = 1,
        reasoning_effort: str = "minimal",
        max_output_tokens: int = 2048,
    ):
        if (
            not model
            or not 1 <= timeout_seconds <= 60
            or max_retries not in {0, 1}
            or reasoning_effort not in {"minimal", "low", "medium", "high"}
            or not 1024 <= max_output_tokens <= 8192
        ):
            raise ValueError("Unsafe language review provider configuration.")
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    def review(self, request):
        return self.client.review_structured(
            request,
            model=self.model,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
        )
