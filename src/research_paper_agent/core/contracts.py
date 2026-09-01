from __future__ import annotations

from pathlib import Path

import yaml

from .models import AgentContract, StageDefinition


class ContractError(ValueError):
    pass


def load_workflow(path: Path) -> tuple[list[StageDefinition], int]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    stages = [StageDefinition(**item) for item in data["stages"]]
    return stages, int(data.get("max_paper_workers", 3))


def load_agent_contract(agent_dir: Path) -> AgentContract:
    data = yaml.safe_load((agent_dir / "agent.yaml").read_text(encoding="utf-8"))
    required = {
        "agent_id",
        "responsibility",
        "readable_inputs",
        "writable_outputs",
        "allowed_tools",
        "required_outputs",
        "human_review",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise ContractError(f"{agent_dir.name} is missing fields: {', '.join(missing)}")
    return AgentContract(**{key: data[key] for key in required})

