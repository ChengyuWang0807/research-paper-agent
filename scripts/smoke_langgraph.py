"""Run the first LangGraph slice locally and demonstrate interrupt/resume."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command
except ImportError as error:  # pragma: no cover - friendly CLI guidance
    raise SystemExit("请先安装图编排依赖：pip install -e \".[graph]\"") from error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_paper_agent.graph_app import build_graph  # noqa: E402


def main() -> int:
    task_id = f"lg-smoke-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": task_id}}
    app = build_graph(MemorySaver())
    initial = {
        "task_id": task_id,
        "topic": "LangGraph + DSH 科研论文工作流接入验收",
        "paper_paths": [],
        "project_root": str(ROOT),
        "runner": "mock",
    }
    paused = app.invoke(initial, config=config)
    print("=== 审核中断 ===")
    print(json.dumps(paused.get("__interrupt__", []), ensure_ascii=False, indent=2, default=str))
    resumed = app.invoke(
        Command(resume={"approved": True, "comment": "smoke test approved"}),
        config=config,
    )
    print("=== 恢复后的状态 ===")
    print(json.dumps(resumed, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
