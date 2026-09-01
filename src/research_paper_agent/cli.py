from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core.agent_runner import MockAgentRunner
from .core.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research-Paper-Agent MVP workflow")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="create a task")
    init_parser.add_argument("--task-id", required=True)
    init_parser.add_argument("--topic", required=True)
    init_parser.add_argument("--paper", action="append", default=[])
    for name in ("run", "status"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--task-id", required=True)
    approve_parser = subparsers.add_parser("approve", help="approve the pending gate")
    approve_parser.add_argument("--task-id", required=True)
    approve_parser.add_argument("--comment", default="")
    reject_parser = subparsers.add_parser("reject", help="reject the pending gate")
    reject_parser.add_argument("--task-id", required=True)
    reject_parser.add_argument("--comment", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    orchestrator = Orchestrator(project_root=args.root.resolve(), runner=MockAgentRunner())
    if args.command == "init":
        task = orchestrator.create_task(args.task_id, args.topic, args.paper)
    elif args.command == "run":
        task = orchestrator.run(args.task_id)
    elif args.command == "approve":
        task = orchestrator.review(args.task_id, approved=True, comment=args.comment)
    elif args.command == "reject":
        task = orchestrator.review(args.task_id, approved=False, comment=args.comment)
    else:
        task = orchestrator.status(args.task_id)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0

