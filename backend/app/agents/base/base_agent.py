"""
Abstract base class for all STLC AI agents.
Every agent (Phase 2+) extends this class to get:
  - Consistent logging to agent_logs table
  - LLM provider injection
  - Pydantic output validation
  - Standard run lifecycle (pending → running → completed/failed)
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.llm.provider import LLMProvider, get_llm

logger = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    """Standard result envelope for a concrete agent's public `run()` method.

    Every concrete agent used to define its own identically-shaped result
    class (`RequirementAgentResult`, `ExecutionAgentResult`, ... 11 copies).
    This is the single shared replacement — same fields, same semantics.
    Distinct from `AgentResult` below, which wraps the `_run()` template
    method's timeout/logging lifecycle instead.
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    logs: list[dict] = field(default_factory=list)
    error: str | None = None


class AgentResult(BaseModel):
    """Standard result envelope returned by every agent."""
    agent_name: str
    agent_run_id: int | None = None
    status: str  # completed | failed
    output: dict[str, Any]
    error: str | None = None
    duration_seconds: float = 0.0


class BaseAgent(ABC):
    """
    All STLC agents inherit from here.

    Usage:
        class RequirementIntakeAgent(BaseAgent):
            name = "requirement_intake"

            async def _run(self, input_data: dict) -> dict:
                # call self.llm.achat(...) etc.
                return {...}
    """

    name: str = "base_agent"

    def __init__(
        self,
        llm: LLMProvider | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ):
        self.llm: LLMProvider = llm or get_llm(
            provider=llm_provider, model=llm_model
        )
        self._logs: list[dict] = []

    def log(self, level: str, step: str, message: str, data: dict | None = None):
        entry = {"level": level, "step": step, "message": message, "data": data}
        self._logs.append(entry)
        getattr(logger, level, logger.info)(
            "[%s] %s — %s", self.name, step, message
        )

    @abstractmethod
    async def _run(self, input_data: dict) -> dict:
        """Core logic — implemented by each concrete agent."""
        ...

    async def run(self, input_data: dict, agent_run_id: int | None = None, timeout: float | None = 120.0) -> AgentResult:
        """Execute the agent and return a structured result."""
        self._logs.clear()
        start = time.monotonic()
        self.log("info", "start", f"Agent '{self.name}' started")
        try:
            if timeout is not None:
                output = await asyncio.wait_for(self._run(input_data), timeout=timeout)
            else:
                output = await self._run(input_data)
            duration = time.monotonic() - start
            self.log("info", "complete", f"Agent '{self.name}' completed in {duration:.1f}s")
            return AgentResult(
                agent_name=self.name,
                agent_run_id=agent_run_id,
                status="completed",
                output=output,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            error_msg = f"Agent execution timed out after {timeout} seconds." if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) else str(exc)
            self.log("error", "error", error_msg)
            logger.exception("Agent '%s' failed", self.name)
            return AgentResult(
                agent_name=self.name,
                agent_run_id=agent_run_id,
                status="failed",
                output={},
                error=error_msg,
                duration_seconds=duration,
            )

    @property
    def collected_logs(self) -> list[dict]:
        return list(self._logs)
