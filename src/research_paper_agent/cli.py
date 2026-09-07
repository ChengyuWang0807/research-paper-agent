from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .workflow import ResearchWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research-Paper-Agent MVP workflow")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    parser.add_argument("--runner", choices=("mock", "dsh"), default="mock")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="create a task")
    init_parser.add_argument("--task-id", required=True)
    init_parser.add_argument("--topic", required=True)
    init_parser.add_argument("--paper", action="append", default=[])
    for name in ("run", "status", "inspect", "sessions", "artifacts"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--task-id", required=True)
    approve_parser = subparsers.add_parser("approve", help="approve the pending gate")
    approve_parser.add_argument("--task-id", required=True)
    approve_parser.add_argument("--comment", default="")
    reject_parser = subparsers.add_parser("reject", help="reject the pending gate")
    reject_parser.add_argument("--task-id", required=True)
    reject_parser.add_argument("--comment", required=True)
    subparsers.add_parser("overview", help="show the high-level workflow map")
    demo_parser = subparsers.add_parser("demo", help="create a task and run it to the next human gate")
    demo_parser.add_argument("--task-id", required=True)
    demo_parser.add_argument("--topic", required=True)
    demo_parser.add_argument("--paper", action="append", default=[])
    retrieve_parser = subparsers.add_parser("retrieve", help="query the local literature index")
    retrieve_parser.add_argument("--query", required=True)
    retrieve_parser.add_argument("--limit", type=int, default=8)
    retrieve_parser.add_argument("--content-type", choices=("text", "table", "figure", "formula"))
    retrieve_parser.add_argument("--year", type=int)
    replay_parser = subparsers.add_parser("replay", help="replay one Agent Run's inputs, outputs and logs")
    replay_parser.add_argument("--task-id", required=True)
    replay_parser.add_argument("--run-id", required=True)
    stage_parser = subparsers.add_parser("stage-runs", help="list runs for one workflow stage")
    stage_parser.add_argument("--task-id", required=True)
    stage_parser.add_argument("--stage", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.command == "overview":
        task = {"workflow": ResearchWorkflow.overview(), "runner_note": "04_experiment is a future conditional branch; 06_reliability is cross-cutting."}
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    workflow = ResearchWorkflow(project_root=args.root.resolve(), runner=args.runner)
    if args.command == "demo":
        workflow.create(args.task_id, args.topic, args.paper)
        task = workflow.run(args.task_id)
        task["next_step"] = _next_step(task)
    elif args.command == "init":
        task = workflow.create(args.task_id, args.topic, args.paper)
    elif args.command == "run":
        task = workflow.run(args.task_id)
    elif args.command == "approve":
        task = workflow.approve(args.task_id, comment=args.comment)
    elif args.command == "reject":
        task = workflow.reject(args.task_id, comment=args.comment)
    elif args.command == "retrieve":
        from .indexing.fts5 import FTS5Index
        from .retrieval.hybrid import HybridRetriever

        metadata_filter = {"publication_year": args.year} if args.year is not None else None
        result = HybridRetriever(FTS5Index(args.root.resolve() / "data" / "literature" / "literature.db")).search(
            args.query, limit=args.limit, content_type=args.content_type, metadata_filter=metadata_filter
        )
        task = result.to_dict()
    elif args.command == "inspect":
        task = workflow.inspect(args.task_id)
    elif args.command == "sessions":
        task = {"task_id": args.task_id, "sessions": workflow.sessions(args.task_id)}
    elif args.command == "artifacts":
        task = {"task_id": args.task_id, "artifacts": workflow.artifacts(args.task_id)}
    elif args.command == "replay":
        task = workflow.replay(args.task_id, args.run_id)
    elif args.command == "stage-runs":
        task = {"task_id": args.task_id, "stage_id": args.stage, "runs": workflow.stage_runs(args.task_id, args.stage)}
    else:
        task = workflow.status(args.task_id)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def _next_step(task: dict[str, object]) -> str:
    if task.get("status") == "AWAITING_REVIEW":
        approval = task.get("pending_approval") or {}
        stage_id = approval.get("stage_id", "unknown") if isinstance(approval, dict) else "unknown"
        return f"审核 {stage_id} 后运行: python workflow.py run --task-id {task.get('task_id')}"
    if task.get("status") == "COMPLETED":
        return "流程完成；查看 artifacts/tasks/<task-id>/ 和 runs/<task-id>/"
    if task.get("status") == "FAILED":
        return "查看 runs/<task-id>/<stage>/ 的 logs 和 output"
    return f"继续运行: python workflow.py run --task-id {task.get('task_id')}"
