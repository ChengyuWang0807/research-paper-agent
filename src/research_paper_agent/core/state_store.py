from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, topic TEXT NOT NULL, paper_paths TEXT NOT NULL,
                    status TEXT NOT NULL, stage_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stage_runs (
                    run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, stage_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL, status TEXT NOT NULL, workspace TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT,
                    session_id TEXT, session_mode TEXT, parent_session_id TEXT, dsh_home TEXT
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    stage_id TEXT NOT NULL, status TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )
            for column, definition in (
                ("session_id", "TEXT"),
                ("session_mode", "TEXT"),
                ("parent_session_id", "TEXT"),
                ("dsh_home", "TEXT"),
            ):
                try:
                    connection.execute(f"ALTER TABLE stage_runs ADD COLUMN {column} {definition}")
                except sqlite3.OperationalError:
                    pass

    def create_task(self, task_id: str, topic: str, paper_paths: list[str]) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, 'READY', 0, ?, ?)",
                (task_id, topic, json.dumps(paper_paths, ensure_ascii=False), now, now),
            )
        self.add_event(task_id, "task.created", {"topic": topic})
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        task = dict(row)
        task["paper_paths"] = json.loads(task["paper_paths"])
        task["pending_approval"] = self.pending_approval(task_id)
        return task

    def update_task(self, task_id: str, *, status: str, stage_index: int | None = None) -> None:
        with self._connect() as connection:
            if stage_index is None:
                connection.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?", (status, utc_now(), task_id))
            else:
                connection.execute("UPDATE tasks SET status = ?, stage_index = ?, updated_at = ? WHERE task_id = ?", (status, stage_index, utc_now(), task_id))

    def start_run(
        self,
        run_id: str,
        task_id: str,
        stage_id: str,
        agent_id: str,
        workspace: str,
        *,
        session_id: str | None = None,
        session_mode: str | None = None,
        parent_session_id: str | None = None,
        dsh_home: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO stage_runs(run_id, task_id, stage_id, agent_id, status, workspace, started_at, finished_at, session_id, session_mode, parent_session_id, dsh_home) VALUES (?, ?, ?, ?, 'RUNNING', ?, ?, NULL, ?, ?, ?, ?)",
                (run_id, task_id, stage_id, agent_id, workspace, utc_now(), session_id, session_mode, parent_session_id, dsh_home),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE stage_runs SET status = ?, finished_at = ? WHERE run_id = ?", (status, utc_now(), run_id))

    def create_approval(self, task_id: str, stage_id: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO approvals(task_id, stage_id, status, created_at) VALUES (?, ?, 'PENDING', ?)", (task_id, stage_id, utc_now()))

    def pending_approval(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE task_id = ? AND status = 'PENDING' ORDER BY approval_id DESC LIMIT 1", (task_id,)).fetchone()
        return dict(row) if row else None

    def decide_approval(self, task_id: str, approved: bool, comment: str) -> dict[str, Any]:
        approval = self.pending_approval(task_id)
        if approval is None:
            raise ValueError(f"task {task_id} has no pending approval")
        decision = "APPROVED" if approved else "REJECTED"
        with self._connect() as connection:
            connection.execute("UPDATE approvals SET status = ?, comment = ?, decided_at = ? WHERE approval_id = ?", (decision, comment, utc_now(), approval["approval_id"]))
        self.add_event(task_id, "approval.decided", {"stage_id": approval["stage_id"], "decision": decision})
        return approval

    def add_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO events(task_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)", (task_id, event_type, json.dumps(payload, ensure_ascii=False), utc_now()))

    def list_stage_runs(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM stage_runs WHERE task_id = ? ORDER BY started_at", (task_id,)
            ).fetchall()
        return [dict(row) for row in rows]
