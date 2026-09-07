"""The readable application-level workflow facade.

This module is intentionally small: the stage order is visible here, while
Orchestrator owns persistence, isolation, fan-out and recovery mechanics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core.agent_runner import MockAgentRunner
from .core.dsh_runner import DeepSeekHarnessRunner
from .core.orchestrator import Orchestrator


STAGE_OVERVIEW = (
    ("01_research_start", "01 研究启动", "定义主题、问题、范围", "人工确认"),
    ("02_literature", "02 文献处理", "并发解析论文、建库、生成证据卡片", "解析失败时"),
    ("03_synthesis", "03 知识整合", "按子问题召回、RRF、生成 evidence_set", "结构化反馈"),
    ("04_experiment", "04 实验闭环", "按需设计、执行和分析实验", "尚未接入"),
    ("05_writing", "05 写作交付", "生成论文结构、草稿和引用映射", "无"),
    ("06_reliability", "06 系统可靠性", "状态、Handoff、Artifact、Trace 全程支撑", "全程"),
    ("05_audit", "05 审计", "检查引用、证据和交付质量", "人工确认"),
)


class ResearchWorkflow:
    """One obvious entry point for driving the Research-Paper-Agent."""

    def __init__(self, project_root: Path | None = None, runner: str = "mock") -> None:
        root = (project_root or Path.cwd()).resolve()
        if runner not in {"mock", "dsh"}:
            raise ValueError("runner must be 'mock' or 'dsh'")
        agent_runner = MockAgentRunner() if runner == "mock" else DeepSeekHarnessRunner()
        self.root = root
        self.runner_name = runner
        self.orchestrator = Orchestrator(root, agent_runner)

    @staticmethod
    def overview() -> list[dict[str, str]]:
        return [
            {"stage_id": stage_id, "name": name, "responsibility": responsibility, "review": review}
            for stage_id, name, responsibility, review in STAGE_OVERVIEW
        ]

    def create(self, task_id: str, topic: str, paper_paths: list[str] | None = None) -> dict[str, Any]:
        return self.orchestrator.create_task(task_id, topic, paper_paths or [])

    def run(self, task_id: str) -> dict[str, Any]:
        return self.orchestrator.run(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        return self.orchestrator.status(task_id)

    def inspect(self, task_id: str) -> dict[str, Any]:
        """Return the task, stage runs, sessions and handoff paths in one view."""
        return self.orchestrator.inspect(task_id)

    def sessions(self, task_id: str) -> list[dict[str, Any]]:
        return self.orchestrator.sessions(task_id)

    def artifacts(self, task_id: str) -> list[dict[str, Any]]:
        return self.orchestrator.list_artifacts(task_id)

    def replay(self, task_id: str, run_id: str) -> dict[str, Any]:
        return self.orchestrator.replay(task_id, run_id)

    def stage_runs(self, task_id: str, stage_id: str) -> list[dict[str, Any]]:
        return [item for item in self.orchestrator.store.list_stage_runs(task_id) if item["stage_id"] == stage_id]

    def approve(self, task_id: str, comment: str = "") -> dict[str, Any]:
        return self.orchestrator.review(task_id, approved=True, comment=comment)

    def reject(self, task_id: str, comment: str) -> dict[str, Any]:
        return self.orchestrator.review(task_id, approved=False, comment=comment)
