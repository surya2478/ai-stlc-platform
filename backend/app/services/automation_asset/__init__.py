"""UI-020/021/023 Automation Asset Workspace services.

Structured the way UI-018 proved out: `evidence.py` is the only module that
queries, `autonomy.py` is pure functions over frozen dataclasses, and
`decisions.py` writes. That separation is what keeps the policy unit-testable
without a database and what bounds the cost of an evaluation pass.
"""
from app.services.automation_asset import autonomy, decisions, evidence  # noqa: F401

__all__ = ["autonomy", "decisions", "evidence"]
