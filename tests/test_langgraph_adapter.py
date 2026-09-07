from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

langgraph = pytest.importorskip("langgraph")
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from research_paper_agent.graph_app import build_graph  # noqa: E402


def test_graph_shape_contains_first_slice() -> None:
    app = build_graph()
    names = set(app.get_graph().nodes)
    assert {"__start__", "research_start", "review_scope", "literature_init", "__end__"} <= names


def test_graph_interrupt_and_resume_persists_handoff(tmp_path: Path) -> None:
    source_root = Path(__file__).parents[1]
    shutil.copytree(source_root / "config", tmp_path / "config")
    agents_target = tmp_path / "src" / "research_paper_agent" / "agents"
    shutil.copytree(source_root / "src" / "research_paper_agent" / "agents", agents_target)
    app = build_graph(MemorySaver())
    task_id = "graph-test"
    config = {"configurable": {"thread_id": task_id}}
    paused = app.invoke(
        {
            "task_id": task_id,
            "topic": "测试 LangGraph 首阶段",
            "paper_paths": [],
            "project_root": str(tmp_path),
            "runner": "mock",
        },
        config=config,
    )
    assert paused["status"] == "AWAITING_REVIEW"
    interrupt_value = paused["__interrupt__"][0].value
    assert interrupt_value["type"] == "research_scope_review"
    assert interrupt_value["task_brief"]["topic"] == "测试 LangGraph 首阶段"

    completed = app.invoke(Command(resume={"approved": True, "comment": "ok"}), config=config)
    assert completed["status"] == "LITERATURE_READY"
    assert completed["current_stage"] == "02_literature"
    assert "01_research_start" in completed["artifact_refs"]
    assert "02_literature" in completed["artifact_refs"]
    handoff = Path(completed["handoff_refs"]["01_research_start_to_02_literature"])
    assert handoff.exists()
    assert json.loads(handoff.read_text(encoding="utf-8"))["target_stage"] == "02_literature"
