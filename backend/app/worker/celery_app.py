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
        "app.worker.tasks.agent_reaper_tasks",
        "app.worker.tasks.agent_tasks",
        "app.worker.tasks.automation_tasks",
        "app.worker.tasks.discovery_tasks",
        "app.worker.tasks.document_tasks",
        "app.worker.tasks.jira_tasks",
        "app.worker.tasks.rag_tasks",
        "app.worker.tasks.retention_tasks",
        "app.worker.tasks.suite_execution_tasks",
        "app.worker.tasks.test_automation_studio_tasks",
    ],
)

from celery.schedules import crontab

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
    beat_schedule={
        # Run all data retention tasks nightly at 02:00 UTC
        "nightly-data-retention": {
            "task": "retention_tasks.run_all_retention",
            "schedule": crontab(hour=2, minute=0),
        },
        # An agent run whose worker died stays "running" forever and spins the
        # UI on a task that no longer exists. Every 5 minutes bounds how long
        # that can be believed; the reaper's own rule (the agent's declared
        # timeout + grace) decides what is actually abandoned.
        "reap-abandoned-agent-runs": {
            "task": "agent_reaper_tasks.reap_abandoned_agent_runs",
            "schedule": crontab(minute="*/5"),
        },
    },
)
