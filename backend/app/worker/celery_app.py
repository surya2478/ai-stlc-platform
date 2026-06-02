"""
Celery application — background task queue for agent runs and long operations.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "stlc_workers",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.worker.tasks.agent_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)
