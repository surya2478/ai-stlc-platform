"""P1-S7 UI-046 Suite Execution Command Center.

Modules:

* `readiness` — the five-way gate that must pass before any item is dispatched.
* `outcomes`  — pure classification into the eight deterministic outcomes, plus
  the evidence quorum rule.
* `events`    — the append-only, monotonically sequenced event stream the UI polls.
* `controls`  — pause/resume/stop/cancel with acknowledgement and optimistic
  concurrency.
* `orchestrator` — snapshot expansion and dispatch over the existing
  `automation_runner`.

The division is deliberate: `outcomes` is pure so every branch is testable
without an execution, and `readiness` is separate from `orchestrator` so a gate
verdict can be computed and shown before anyone commits to a run.
"""
from app.services.execution_command_center import outcomes, readiness  # noqa: F401
