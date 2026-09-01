from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StageDefinition:
    id: str
    agent: str
    mode: str
    approval: str
    worker_agent: str | None = None


@dataclass(frozen=True)
class AgentContract:
    agent_id: str
    responsibility: list[str]
    readable_inputs: list[str]
    writable_outputs: list[str]
    allowed_tools: list[str]
    required_outputs: list[str]
    human_review: str


@dataclass
class AgentResult:
    agent_id: str
    run_id: str
    status: RunStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

