from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .agent_runner import AgentRunner
from .artifact_store import ArtifactStore
from .contracts import load_agent_contract, load_workflow
from .handoff import HandoffStore
from .models import AgentResult, RunStatus, StageDefinition, TaskStatus
from .scheduler import Scheduler
from .state_store import StateStore
from .workspace import WorkspaceManager


class Orchestrator:
    def __init__(self, project_root: Path, runner: AgentRunner) -> None:
        self.root = project_root
        self.runner = runner
        self.stages, max_workers = load_workflow(self.root / "config" / "workflow.yaml")
        self.store = StateStore(self.root / "data" / "app.db")
        self.workspaces = WorkspaceManager(self.root / "runs")
        self.artifacts = ArtifactStore(self.root / "artifacts")
        self.handoffs = HandoffStore(self.root / "runs")
        self.scheduler = Scheduler(max_workers=max_workers)

    def create_task(self, task_id: str, topic: str, paper_paths: list[str]) -> dict[str, Any]:
        normalized = [str(Path(path).resolve()) for path in paper_paths]
        result = self.store.create_task(task_id, topic, normalized)
        self.workspaces.initialize_task(task_id, topic, normalized)
        return result

    def status(self, task_id: str) -> dict[str, Any]:
        return self.store.get_task(task_id)

    def review(self, task_id: str, approved: bool, comment: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        self.store.decide_approval(task_id, approved, comment)
        if approved:
            self.store.update_task(task_id, status=TaskStatus.READY.value, stage_index=task["stage_index"] + 1)
        else:
            self.store.update_task(task_id, status=TaskStatus.FAILED.value)
        return self.store.get_task(task_id)

    def run(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task["status"] == TaskStatus.AWAITING_REVIEW.value or task["status"] in (TaskStatus.FAILED.value, TaskStatus.COMPLETED.value):
            return task
        self.store.update_task(task_id, status=TaskStatus.RUNNING.value)
        previous_handoff = (
            self.handoffs.latest_for(task_id, self.stages[task["stage_index"]].id)
            if task["stage_index"] < len(self.stages)
            else None
        )
        previous_artifact: dict[str, str] | None = (
            previous_handoff["artifact"] if previous_handoff else None
        )
        previous_output = self._load_artifact(previous_artifact)
        prior_task_brief = self._latest_task_brief(task_id)
        for index in range(task["stage_index"], len(self.stages)):
            stage = self.stages[index]
            payload = {
                "task_id": task_id,
                "topic": task["topic"],
                "paper_paths": task["paper_paths"],
                "previous_artifact": previous_artifact,
                "previous_output": previous_output,
                "prior_task_brief": prior_task_brief,
                "project_root": str(self.root.resolve()),
            }
            if stage.id == "03_synthesis":
                payload["retrieval_package"] = self._build_retrieval_package(task["topic"], prior_task_brief)
            result = self._run_stage(task_id, stage, payload)
            if result.status is RunStatus.FAILED:
                self.store.update_task(task_id, status=TaskStatus.FAILED.value, stage_index=index)
                return self.store.get_task(task_id)
            previous_artifact = self.artifacts.commit(task_id, stage.id, result.run_id, result.to_dict())
            previous_output = result.to_dict()
            if stage.id == "01_research_start":
                prior_task_brief = result.outputs.get("task_brief.json")
            self.store.add_event(task_id, "artifact.committed", previous_artifact)
            if index + 1 < len(self.stages):
                self.handoffs.write(task_id, stage.id, self.stages[index + 1].id, previous_artifact, {"topic": task["topic"], "source_stage": stage.id})
            if stage.approval == "always":
                self.store.create_approval(task_id, stage.id)
                self.store.update_task(task_id, status=TaskStatus.AWAITING_REVIEW.value, stage_index=index)
                return self.store.get_task(task_id)
            self.store.update_task(task_id, status=TaskStatus.RUNNING.value, stage_index=index + 1)
        self.store.update_task(task_id, status=TaskStatus.COMPLETED.value, stage_index=len(self.stages))
        return self.store.get_task(task_id)

    def run_stage(self, task_id: str, stage_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute exactly one stage and persist its artifact and handoff.

        LangGraph owns the graph-level control flow and approvals, while this
        method keeps the existing artifact, workspace, session and handoff
        semantics in one place.  It is deliberately independent from
        :meth:`run`, which continues to support the original CLI workflow.
        """
        task = self.store.get_task(task_id)
        stage = next((item for item in self.stages if item.id == stage_id), None)
        if stage is None:
            raise KeyError(f"stage not found: {stage_id}")
        result = self._run_stage(task_id, stage, payload)
        if result.status is RunStatus.FAILED:
            self.store.update_task(task_id, status=TaskStatus.FAILED.value)
            return {"result": result.to_dict(), "artifact": None, "handoff": None}

        artifact = self.artifacts.commit(task_id, stage.id, result.run_id, result.to_dict())
        self.store.add_event(task_id, "artifact.committed", artifact)
        index = self.stages.index(stage)
        handoff_path: Path | None = None
        if index + 1 < len(self.stages):
            next_stage = self.stages[index + 1]
            handoff_path = self.handoffs.write(
                task_id,
                stage.id,
                next_stage.id,
                artifact,
                {"topic": task["topic"], "source_stage": stage.id},
            )
        self.store.update_task(task_id, status=TaskStatus.READY.value, stage_index=index + 1)
        return {
            "result": result.to_dict(),
            "artifact": artifact,
            "handoff": str(handoff_path.resolve()) if handoff_path else None,
        }

    @staticmethod
    def _load_artifact(artifact: dict[str, str] | None) -> dict[str, Any] | None:
        if not artifact or not artifact.get("uri"):
            return None
        parsed = urlparse(artifact["uri"])
        if parsed.scheme != "file":
            return None
        path = Path(unquote(parsed.path.lstrip("/")))
        if parsed.netloc:
            path = Path(f"//{parsed.netloc}{unquote(parsed.path)}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _latest_task_brief(self, task_id: str) -> dict[str, Any] | None:
        paths = sorted((self.artifacts.root / "tasks" / task_id / "01_research_start").glob("*.json"), key=lambda path: path.stat().st_mtime_ns)
        if not paths:
            return None
        value = self._load_artifact({"uri": paths[-1].resolve().as_uri()}) or {}
        outputs = value.get("outputs", value) if isinstance(value, dict) else {}
        brief = outputs.get("task_brief.json") if isinstance(outputs, dict) else None
        return brief if isinstance(brief, dict) else None

    def _build_retrieval_package(self, topic: str, task_brief: dict[str, Any] | None) -> dict[str, Any]:
        """Precompute retrieval so Mock and DSH runners receive identical evidence."""
        from ..retrieval.integration import KnowledgeIntegrator

        questions = task_brief.get("research_questions", []) if isinstance(task_brief, dict) else []
        index_path = self.root / "data" / "literature" / "literature.db"
        if not index_path.exists():
            return {"status": "unavailable", "reason": "literature index does not exist", "query_plan": []}
        return KnowledgeIntegrator(index_path).integrate(topic, questions).to_dict()

    def _run_stage(self, task_id: str, stage: StageDefinition, payload: dict[str, Any]) -> AgentResult:
        if stage.mode == "paper_fanout":
            worker_results = self.scheduler.map(lambda path: self._execute_agent(task_id, stage.id, stage.worker_agent or "paper_worker", {**payload, "paper_path": path}), payload["paper_paths"])
            failed = [item for item in worker_results if item.status is RunStatus.FAILED]
            if failed:
                return failed[0]
            payload = {**payload, "worker_results": [item.outputs for item in worker_results]}
        return self._execute_agent(task_id, stage.id, stage.agent, payload)

    def _execute_agent(self, task_id: str, stage_id: str, agent_id: str, payload: dict[str, Any]) -> AgentResult:
        agent_dir = self.root / "src" / "research_paper_agent" / "agents" / agent_id
        contract = load_agent_contract(agent_dir)
        prompt = (agent_dir / "system_prompt.md").read_text(encoding="utf-8")
        session_mode = self._session_mode(stage_id, agent_id)
        session_scope = f"{stage_id}:{agent_id}"
        if agent_id == "paper_worker":
            session_scope = f"{session_scope}:{payload.get('paper_path', '')}"
        run_id, workspace, session = self.workspaces.create(
            task_id,
            stage_id,
            agent_id,
            payload,
            session_mode=session_mode,
            session_scope=session_scope,
            include_session=True,
        )
        self.store.start_run(
            run_id,
            task_id,
            stage_id,
            agent_id,
            str(workspace),
            session_id=session["session_id"],
            session_mode=session["session_mode"],
            parent_session_id=session.get("parent_session_id"),
            dsh_home=session.get("dsh_home"),
        )
        self.store.add_event(task_id, "agent.started", {"run_id": run_id, "agent_id": agent_id})
        try:
            runtime_payload = {
                **payload,
                "_runtime": {
                    "session_id": session["session_id"],
                    "session_mode": session["session_mode"],
                    "parent_session_id": session.get("parent_session_id"),
                    "dsh_home": session["dsh_home"],
                },
            }
            result = self.runner.run(contract, prompt, workspace, runtime_payload, run_id)
        except Exception as error:
            self.store.finish_run(run_id, RunStatus.FAILED.value)
            self.workspaces.sessions.update(task_id, session["session_id"], status="FAILED", last_run_id=run_id)
            self.store.add_event(task_id, "agent.failed", {"run_id": run_id, "error": str(error)})
            raise
        self.store.finish_run(run_id, result.status.value)
        self.workspaces.sessions.update(
            task_id,
            session["session_id"],
            status="OPEN" if session["session_mode"] == "continuable" else "CLOSED",
            last_run_id=run_id,
        )
        self._update_run_manifest(workspace, result.status.value, result)
        self.store.add_event(task_id, "agent.finished", result.to_dict())
        return result

    @staticmethod
    def _session_mode(stage_id: str, agent_id: str) -> str:
        if agent_id == "paper_worker" or stage_id in {"02_literature", "05_audit"}:
            return "one_shot"
        return "continuable"

    @staticmethod
    def _update_run_manifest(workspace: Path, status: str, result: AgentResult) -> None:
        path = workspace / "run_manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        value.update({"status": status, "result": result.to_dict()})
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def inspect(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        task_root = self.root / "runs" / task_id
        return {
            "task": task,
            "stage_runs": self.store.list_stage_runs(task_id),
            "task_workspace": str(task_root.resolve()),
            "task_manifest": str((task_root / "task.json").resolve()),
            "session_manifest": str((task_root / "session_manifest.json").resolve()),
            "handoffs": sorted(str(path.resolve()) for path in (task_root / "handoffs").glob("*.json")),
            "sessions": self.sessions(task_id),
            "artifacts": self.list_artifacts(task_id),
        }

    def sessions(self, task_id: str) -> list[dict[str, Any]]:
        path = self.root / "runs" / task_id / "session_manifest.json"
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return value.get("sessions", []) if isinstance(value, dict) else []

    def list_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        root = self.artifacts.root / "tasks" / task_id
        if not root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*.json"), key=lambda item: item.stat().st_mtime_ns):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = None
            items.append({
                "stage_id": path.parent.name,
                "run_id": path.stem,
                "path": str(path.resolve()),
                "valid_json": value is not None,
                "keys": sorted(value.keys()) if isinstance(value, dict) else [],
            })
        return items

    def replay(self, task_id: str, run_id: str) -> dict[str, Any]:
        runs_root = self.root / "runs" / task_id
        matches = list(runs_root.rglob(run_id))
        if not matches:
            raise KeyError(f"run not found: {run_id}")
        workspace = matches[0]
        def read_json(path: Path) -> Any:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return {
            "task_id": task_id,
            "run_id": run_id,
            "workspace": str(workspace.resolve()),
            "run_manifest": read_json(workspace / "run_manifest.json"),
            "input": read_json(workspace / "input" / "payload.json"),
            "outputs": {
                path.name: read_json(path)
                for path in sorted((workspace / "output").glob("*.json"))
            },
            "logs": {
                path.name: read_json(path)
                for path in sorted((workspace / "logs").glob("*.json"))
            },
        }
