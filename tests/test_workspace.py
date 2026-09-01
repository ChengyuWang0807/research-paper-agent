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

