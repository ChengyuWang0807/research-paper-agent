from __future__ import annotations

from pathlib import Path
from typing import Any

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
        return self.store.create_task(task_id, topic, [str(Path(path).resolve()) for path in paper_paths])

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
        for index in range(task["stage_index"], len(self.stages)):
            stage = self.stages[index]
            payload = {"task_id": task_id, "topic": task["topic"], "paper_paths": task["paper_paths"], "previous_artifact": previous_artifact}
            result = self._run_stage(task_id, stage, payload)
            if result.status is RunStatus.FAILED:
                self.store.update_task(task_id, status=TaskStatus.FAILED.value, stage_index=index)
                return self.store.get_task(task_id)
            previous_artifact = self.artifacts.commit(task_id, stage.id, result.run_id, result.to_dict())
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
        run_id, workspace = self.workspaces.create(task_id, stage_id, agent_id, payload)
        self.store.start_run(run_id, task_id, stage_id, agent_id, str(workspace))
        self.store.add_event(task_id, "agent.started", {"run_id": run_id, "agent_id": agent_id})
        try:
            result = self.runner.run(contract, prompt, workspace, payload, run_id)
        except Exception as error:
            self.store.finish_run(run_id, RunStatus.FAILED.value)
            self.store.add_event(task_id, "agent.failed", {"run_id": run_id, "error": str(error)})
            raise
        self.store.finish_run(run_id, result.status.value)
        self.store.add_event(task_id, "agent.finished", result.to_dict())
        return result
