from __future__ import annotations

import json
import uuid
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManifestStore:
    """Small durable registry that maps a research run to its DSH session.

    DSH owns the append-only conversation log. This file owns the application
    mapping between task/stage/agent and that DSH session, so the workflow can
    resume after a CLI process exits without importing DSH's internal storage.
    """

    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.resolve()
        self._lock = Lock()

    def initialize_task(self, task_id: str, topic: str, paper_paths: list[str]) -> Path:
        with self._lock:
            task_root = self.runs_root / task_id
            (task_root / "dsh" / "home").mkdir(parents=True, exist_ok=True)
            (task_root / "dsh" / "sessions").mkdir(parents=True, exist_ok=True)
            (task_root / "handoffs").mkdir(parents=True, exist_ok=True)
            manifest = task_root / "task.json"
            if not manifest.exists():
                self._write(manifest, {
                    "task_id": task_id,
                    "topic": topic,
                    "paper_paths": paper_paths,
                    "workspace": str(task_root),
                    "created_at": utc_now(),
                })
            registry = task_root / "session_manifest.json"
            if not registry.exists():
                self._write(registry, {"version": 1, "task_id": task_id, "sessions": []})
            return task_root

    def acquire(
        self,
        task_id: str,
        stage_id: str,
        agent_id: str,
        *,
        session_mode: str,
        parent_session_id: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            registry_path = self.runs_root / task_id / "session_manifest.json"
            registry = self._read(registry_path, {"version": 1, "task_id": task_id, "sessions": []})
            key = scope or f"{stage_id}:{agent_id}"
            if session_mode == "continuable":
                for item in registry["sessions"]:
                    if item.get("scope") == key and item.get("status") != "CLOSED":
                        return item
            record = {
                "session_id": f"rpa-{uuid.uuid4().hex[:16]}",
                "task_id": task_id,
                "stage_id": stage_id,
                "agent_id": agent_id,
                "scope": key,
                "session_mode": session_mode,
                "parent_session_id": parent_session_id,
                "dsh_home": str((self.runs_root / task_id / "dsh" / "home").resolve()),
                "status": "OPEN",
                "created_at": utc_now(),
                "last_run_id": None,
                "last_finished_at": None,
            }
            registry["sessions"].append(record)
            self._write(registry_path, registry)
            return record

    def update(self, task_id: str, session_id: str, **changes: Any) -> None:
        with self._lock:
            path = self.runs_root / task_id / "session_manifest.json"
            registry = self._read(path, {"version": 1, "task_id": task_id, "sessions": []})
            for item in registry["sessions"]:
                if item.get("session_id") == session_id:
                    item.update(changes)
                    item["last_finished_at"] = utc_now()
                    break
            self._write(path, registry)

    @staticmethod
    def _read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
