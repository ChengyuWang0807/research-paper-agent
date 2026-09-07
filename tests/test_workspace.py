from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from research_paper_agent.core.workspace import WorkspaceManager


def test_each_run_gets_an_isolated_workspace(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "runs")
    first_id, first = manager.create("task", "stage", "worker", {"paper": "a"})
    second_id, second = manager.create("task", "stage", "worker", {"paper": "b"})
    assert first_id != second_id
    assert first != second
    assert (first / "input" / "payload.json").exists()
    assert (second / "output").is_dir()


def test_task_session_manifest_keeps_parallel_worker_sessions(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "runs")
    manager.initialize_task("task", "topic", [])

    def create_worker(index: int) -> None:
        manager.create(
            "task",
            "02_literature",
            "paper_worker",
            {"paper_path": f"paper-{index}.pdf"},
            session_mode="one_shot",
            session_scope=f"02_literature:paper_worker:paper-{index}.pdf",
            include_session=True,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(create_worker, range(8)))

    manifest = json.loads(
        (tmp_path / "runs" / "task" / "session_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["sessions"]) == 8
