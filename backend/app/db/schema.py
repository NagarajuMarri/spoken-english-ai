"""Database schema identifiers shared by runtime readiness and version evidence."""

ALEMBIC_HEAD_REVISION = "0019_realtime_turns"


def ensure_no_duplicate_subscriptions(connection) -> None:
    from sqlalchemy import text

    duplicate = connection.execute(text(
        "SELECT learner_id, COUNT(*) AS subscription_count "
        "FROM commercial_subscriptions GROUP BY learner_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce one subscription lifecycle per learner: duplicate commercial subscriptions require operator review."
        )
