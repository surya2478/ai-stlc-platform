"""
Celery tasks for dispatching AI agent runs asynchronously.
Phase 1: stubs only — agents are implemented in Phase 2+.
"""
import logging

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="agent_tasks.run_agent", max_retries=2)
def run_agent(self, agent_run_id: int, agent_name: str, input_data: dict):
    """
    Generic agent dispatch task.
    Will be fleshed out in Phase 2 once LangGraph agents are implemented.
    """
    logger.info("Agent task started: agent=%s run_id=%s", agent_name, agent_run_id)
    # TODO Phase 2: import and invoke the appropriate LangGraph agent
    return {"agent_run_id": agent_run_id, "status": "stub_completed"}
