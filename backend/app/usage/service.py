from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select

from backend.app.core.errors import AppError
from backend.app.models import AIUsageRecord
from backend.app.usage.limits import UsageLimits
from fastapi import status


class UsageService:
    def __init__(self, session, limits=UsageLimits()):
        self.session, self.limits = session, limits

    def _day_start(self):
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def enforce(self, learner_id, user_id, voice_session_id=None):
        since = self._day_start()
        learner_count = self.session.scalar(select(func.sum(AIUsageRecord.request_count)).where(
            AIUsageRecord.learner_id == learner_id, AIUsageRecord.occurred_at >= since
        )) or 0
        account_count = self.session.scalar(select(func.sum(AIUsageRecord.request_count)).where(
            AIUsageRecord.user_id == user_id, AIUsageRecord.occurred_at >= since
        )) or 0
        session_count = 0
        if voice_session_id:
            session_count = self.session.scalar(select(func.sum(AIUsageRecord.request_count)).where(
                AIUsageRecord.voice_session_id == voice_session_id
            )) or 0
        if (
            learner_count >= self.limits.learner_requests_per_day
            or account_count >= self.limits.account_requests_per_day
            or session_count >= self.limits.voice_session_requests
        ):
            raise AppError(status.HTTP_429_TOO_MANY_REQUESTS, "ai_usage_limit_reached", "AI usage limit reached.")

    def record(self, *, learner_id, user_id, provider_kind, voice_session_id=None,
               input_units=0, output_units=0, request_count=1, retries=0,
               failed=False, degraded=False, commit=True,
               ai_turn_attempt_id=None, outcome="SUCCESS"):
        record = AIUsageRecord(
            ai_turn_attempt_id=ai_turn_attempt_id,
            learner_id=learner_id, user_id=user_id, voice_session_id=voice_session_id,
            provider_kind=provider_kind, request_count=request_count,
            input_units=input_units, output_units=output_units, retries=retries,
            failed=failed, degraded=degraded, outcome=outcome,
        )
        self.session.add(record)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return record

    def record_failure_attempt(
        self,
        *,
        ai_turn_attempt_id,
        learner_id,
        user_id,
        provider_requests,
        input_units=0,
        output_units=0,
        commit=True,
    ):
        record = self.session.scalar(select(AIUsageRecord).where(
            AIUsageRecord.ai_turn_attempt_id == ai_turn_attempt_id,
            AIUsageRecord.outcome == "FAILURE",
        ))
        if record is None:
            record = AIUsageRecord(
                ai_turn_attempt_id=ai_turn_attempt_id,
                learner_id=learner_id,
                user_id=user_id,
                provider_kind="llm",
                outcome="FAILURE",
                request_count=provider_requests,
                retries=max(0, provider_requests - 1),
                input_units=input_units,
                output_units=output_units,
                failed=True,
            )
            self.session.add(record)
        else:
            record.request_count += provider_requests
            record.retries += max(0, provider_requests - 1)
            record.input_units += input_units
            record.output_units += output_units
            record.failed = True
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return record

    def summary(self, learner_id):
        rows = list(self.session.scalars(select(AIUsageRecord).where(AIUsageRecord.learner_id == learner_id)))
        return {
            "request_count": sum(row.request_count for row in rows),
            "input_units": sum(row.input_units for row in rows),
            "output_units": sum(row.output_units for row in rows),
            "failures": sum(1 for row in rows if row.failed),
            "degraded_responses": sum(1 for row in rows if row.degraded),
        }
