from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


class WorkspaceManager:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.resolve()

    def create(self, task_id: str, stage_id: str, agent_id: str, payload: dict[str, Any]) -> tuple[str, Path]:
        run_id = f"{agent_id}-{uuid.uuid4().hex[:10]}"
        workspace = (self.runs_root / task_id / stage_id / run_id).resolve()
        if self.runs_root not in workspace.parents:
            raise ValueError("workspace escaped the configured runs root")
        for name in ("input", "scratch", "output", "logs"):
            (workspace / name).mkdir(parents=True, exist_ok=False)
        self.write_json(workspace / "input" / "payload.json", payload)
        self.write_json(workspace / "run_manifest.json", {"run_id": run_id, "task_id": task_id, "stage_id": stage_id, "agent_id": agent_id})
        return run_id, workspace

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

