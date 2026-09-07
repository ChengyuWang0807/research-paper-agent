"""LangGraph entry point for the Research-Paper-Agent.

The graph deliberately covers the first demonstrable slice of the product:
research kickoff, a human scope gate, and literature-processing initialization.
The existing Orchestrator remains responsible for business artifacts and DSH
sessions; LangGraph only owns graph state, interruption and resume semantics.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

# LangGraph's dev server loads this file directly from ``langgraph.json``.
# Make the ``src`` layout importable in that mode as well as normal package
# imports after ``pip install -e .``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_paper_agent.workflow import ResearchWorkflow


class ResearchState(TypedDict, total=False):
    task_id: str
    topic: str
    paper_paths: list[str]
    project_root: str
    runner: str
    task_brief: dict[str, Any]
    approval: dict[str, Any]
    current_stage: str
    status: str
    artifact_refs: dict[str, dict[str, str]]
    handoff_refs: dict[str, str]
    dsh_session_refs: dict[str, str]
    error: str


def _project_root(state: ResearchState) -> Path:
    configured = state.get("project_root") or os.getenv("RPA_PROJECT_ROOT")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workflow(state: ResearchState) -> ResearchWorkflow:
    return ResearchWorkflow(
        project_root=_project_root(state),
        runner=state.get("runner") or os.getenv("RPA_RUNNER", "mock"),
    )


def _session_refs(workflow: ResearchWorkflow, task_id: str) -> dict[str, str]:
    return {
        f"{item.get('stage_id')}:{item.get('agent_id')}:{index}": item["session_id"]
        for index, item in enumerate(workflow.sessions(task_id))
        if item.get("session_id")
    }


def research_start(state: ResearchState) -> ResearchState:
    """Create the task and produce the versioned task brief artifact."""
    workflow = _workflow(state)
    task_id = state["task_id"]
    topic = state["topic"]
    paper_paths = state.get("paper_paths", [])
    try:
        workflow.status(task_id)
    except KeyError:
        workflow.create(task_id, topic, paper_paths)

    payload = {
        "task_id": task_id,
        "topic": topic,
        "paper_paths": paper_paths,
        "project_root": str(_project_root(state)),
    }
    execution = workflow.orchestrator.run_stage(task_id, "01_research_start", payload)
    result = execution["result"]
    if result["status"] != "SUCCEEDED":
        return {"status": "FAILED", "current_stage": "01_research_start", "error": str(result.get("issues", []))}
    task_brief = result.get("outputs", {}).get("task_brief.json", {})
    artifact_refs = dict(state.get("artifact_refs", {}))
    if execution.get("artifact"):
        artifact_refs["01_research_start"] = execution["artifact"]
    handoff_refs = dict(state.get("handoff_refs", {}))
    if execution.get("handoff"):
        handoff_refs["01_research_start_to_02_literature"] = execution["handoff"]
    return {
        "task_brief": task_brief,
        "artifact_refs": artifact_refs,
        "handoff_refs": handoff_refs,
        "dsh_session_refs": _session_refs(workflow, task_id),
        "current_stage": "01_research_start",
        "status": "AWAITING_REVIEW",
    }


def review_scope(state: ResearchState) -> ResearchState:
    """Pause for human scope approval and resume on the same graph thread."""
    decision = interrupt(
        {
            "type": "research_scope_review",
            "message": "请确认研究任务草稿后继续",
            "task_id": state.get("task_id"),
            "task_brief": state.get("task_brief", {}),
            "expected_resume": {"approved": True, "comment": "..."},
        }
    )
    if isinstance(decision, bool):
        approved = decision
        comment = ""
    elif isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
        comment = str(decision.get("comment", ""))
    else:
        approved = str(decision).lower() in {"approve", "approved", "yes", "true"}
        comment = str(decision)
    if not approved:
        return {"status": "REJECTED", "approval": {"approved": False, "comment": comment}}
    return {
        "status": "APPROVED",
        "approval": {"approved": True, "comment": comment},
    }


def literature_init(state: ResearchState) -> ResearchState:
    """Initialize 02 using the approved task brief and its handoff reference."""
    if state.get("status") == "REJECTED":
        return {"current_stage": "01_research_start", "status": "REJECTED"}
    workflow = _workflow(state)
    task_id = state["task_id"]
    payload = {
        "task_id": task_id,
        "topic": state["topic"],
        "paper_paths": state.get("paper_paths", []),
        "prior_task_brief": state.get("task_brief", {}),
        "previous_artifact": state.get("artifact_refs", {}).get("01_research_start"),
        "project_root": str(_project_root(state)),
    }
    execution = workflow.orchestrator.run_stage(task_id, "02_literature", payload)
    result = execution["result"]
    if result["status"] != "SUCCEEDED":
        return {"status": "FAILED", "current_stage": "02_literature", "error": str(result.get("issues", []))}
    artifact_refs = dict(state.get("artifact_refs", {}))
    if execution.get("artifact"):
        artifact_refs["02_literature"] = execution["artifact"]
    handoff_refs = dict(state.get("handoff_refs", {}))
    if execution.get("handoff"):
        handoff_refs["02_literature_to_03_synthesis"] = execution["handoff"]
    return {
        "artifact_refs": artifact_refs,
        "handoff_refs": handoff_refs,
        "dsh_session_refs": _session_refs(workflow, task_id),
        "current_stage": "02_literature",
        "status": "LITERATURE_READY",
    }


def build_graph(checkpointer: Any | None = None):
    """Build the graph, optionally with a local checkpointer for SDK tests."""
    builder = StateGraph(ResearchState)
    builder.add_node("research_start", research_start)
    builder.add_node("review_scope", review_scope)
    builder.add_node("literature_init", literature_init)
    builder.add_edge(START, "research_start")
    builder.add_edge("research_start", "review_scope")
    builder.add_edge("review_scope", "literature_init")
    builder.add_edge("literature_init", END)
    return builder.compile(checkpointer=checkpointer)


# LangGraph API/Studio imports this symbol from langgraph.json. The server
# supplies persistence; local tests can call build_graph(MemorySaver()).
graph = build_graph()
