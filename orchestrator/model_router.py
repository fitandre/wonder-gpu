"""
Picks the cheapest model that's likely to succeed at a task, and escalates
only when the cheaper tier has demonstrably failed -- rather than guessing
up front which tasks "feel hard."
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Task:
    id: str
    phase: str
    title: str
    kind: str                  # "design_or_spike" | "implementation" | "verification" | "chore"
    touches_paths: list[str] = field(default_factory=list)
    failure_count: int = 0


class ModelRouter:
    def __init__(self, routing_cfg: dict, escalate_after_failures: int,
                 human_gate_paths: list[str]):
        self.routing_cfg = routing_cfg
        self.escalate_after_failures = escalate_after_failures
        self.human_gate_paths = human_gate_paths

    def model_for(self, task: Task) -> str:
        base = self.routing_cfg.get(task.kind, self.routing_cfg["default"])
        if task.failure_count >= self.escalate_after_failures and base != "gemini-1.5-pro":
            return "gemini-1.5-pro"  # escalate to Pro on failure
        return base

    def requires_human_gate(self, task: Task) -> bool:
        import fnmatch
        for pattern in self.human_gate_paths:
            for path in task.touches_paths:
                if fnmatch.fnmatch(path, pattern):
                    return True
        return False
