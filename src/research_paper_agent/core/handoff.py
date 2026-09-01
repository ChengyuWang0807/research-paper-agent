from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class HandoffStore:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root

    def write(self, task_id: str, source_stage: str, target_stage: str, artifact: dict[str, str], summary: dict[str, Any]) -> Path:
        handoff_dir = self.runs_root / task_id / "handoffs"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        version = len(list(handoff_dir.glob(f"{source_stage}_to_{target_stage}.v*.json"))) + 1
        path = handoff_dir / f"{source_stage}_to_{target_stage}.v{version}.json"
        path.write_text(json.dumps({"schema_version": "1.0", "task_id": task_id, "source_stage": source_stage, "target_stage": target_stage, "artifact": artifact, "next_stage_brief": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def latest_for(self, task_id: str, target_stage: str) -> dict[str, Any] | None:
        handoff_dir = self.runs_root / task_id / "handoffs"
        candidates = sorted(
            handoff_dir.glob(f"*_to_{target_stage}.v*.json"),
            key=lambda path: path.stat().st_mtime_ns,
        )
        if not candidates:
            return None
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
