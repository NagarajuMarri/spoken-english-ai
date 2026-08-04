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
               input_units=0, output_units=0, failed=False, degraded=False):
        record = AIUsageRecord(
            learner_id=learner_id, user_id=user_id, voice_session_id=voice_session_id,
            provider_kind=provider_kind, input_units=input_units, output_units=output_units,
            failed=failed, degraded=degraded,
        )
        self.session.add(record)
        self.session.commit()
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
