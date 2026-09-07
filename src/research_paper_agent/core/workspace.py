from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .session_manifest import SessionManifestStore


class WorkspaceManager:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.resolve()
        self.sessions = SessionManifestStore(self.runs_root)

    def initialize_task(self, task_id: str, topic: str, paper_paths: list[str]) -> Path:
        return self.sessions.initialize_task(task_id, topic, paper_paths)

    def create(
        self,
        task_id: str,
        stage_id: str,
        agent_id: str,
        payload: dict[str, Any],
        *,
        session_mode: str = "one_shot",
        parent_session_id: str | None = None,
        session_scope: str | None = None,
        include_session: bool = False,
    ) -> tuple[str, Path] | tuple[str, Path, dict[str, Any]]:
        run_id = f"{agent_id}-{uuid.uuid4().hex[:10]}"
        workspace = Path(os.path.abspath(self.runs_root / task_id / stage_id / run_id))
        root_text = os.path.normcase(os.path.abspath(str(self.runs_root)))
        workspace_text = os.path.normcase(os.path.abspath(str(workspace)))
        try:
            inside = os.path.commonpath([root_text, workspace_text]) == root_text
        except ValueError:
            inside = False
        if not inside:
            raise ValueError("workspace escaped the configured runs root")
        for name in ("input", "scratch", "output", "logs", "session"):
            (workspace / name).mkdir(parents=True, exist_ok=False)
        session = self.sessions.acquire(
            task_id,
            stage_id,
            agent_id,
            session_mode=session_mode,
            parent_session_id=parent_session_id,
            scope=session_scope,
        )
        recorded_payload = {
            **payload,
            "_runtime": {
                "session_id": session["session_id"],
                "session_mode": session["session_mode"],
                "parent_session_id": session.get("parent_session_id"),
                "dsh_home": session["dsh_home"],
            },
        }
        self.write_json(workspace / "input" / "payload.json", recorded_payload)
        self.write_json(workspace / "run_manifest.json", {
            "run_id": run_id,
            "task_id": task_id,
            "stage_id": stage_id,
            "agent_id": agent_id,
            "session_id": session["session_id"],
            "session_mode": session["session_mode"],
            "parent_session_id": session.get("parent_session_id"),
            "dsh_home": session["dsh_home"],
            "status": "RUNNING",
            "created_at": session["created_at"],
        })
        if include_session:
            return run_id, workspace, session
        return run_id, workspace

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
