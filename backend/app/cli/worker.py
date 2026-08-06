"""Explicit Redis worker entry point; importing the application never starts it."""

import signal
import time

from redis import Redis

from backend.app.core.config import get_settings
from backend.app.jobs import RedisJobQueue


def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("SPOKEN_ENGLISH_REDIS_URL is required for the worker")
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=5)
    queue = RedisJobQueue(client)
    shutting_down = False

    def stop(*_args) -> None:
        nonlocal shutting_down
        shutting_down = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not shutting_down:
        client.set(settings.worker_heartbeat_key, str(time.time()), ex=settings.worker_heartbeat_ttl_seconds)
        job = queue.take(timeout_seconds=5)
        if job is None:
            continue
        try:
            # Job kinds are deliberately allow-listed as handlers are added.
            if job.kind != "healthcheck":
                raise ValueError("Unsupported job kind")
            queue.complete(job)
        except Exception:
            queue.fail(job)
    client.delete(settings.worker_heartbeat_key)
    client.close()


if __name__ == "__main__":
    main()
