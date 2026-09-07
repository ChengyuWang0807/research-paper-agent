from pathlib import Path

from research_paper_agent.core.agent_runner import MockAgentRunner
from research_paper_agent.core.orchestrator import Orchestrator


def copy_project_config(source_root: Path, target_root: Path) -> None:
    import shutil

    shutil.copytree(source_root / "config", target_root / "config")
    shutil.copytree(source_root / "src", target_root / "src")


def test_workflow_pauses_at_both_human_gates(tmp_path: Path) -> None:
    source_root = Path(__file__).parents[1]
    copy_project_config(source_root, tmp_path)
    orchestrator = Orchestrator(tmp_path, MockAgentRunner())
    orchestrator.create_task("demo", "Agent Harness", ["paper-a.pdf", "paper-b.pdf"])
    first_gate = orchestrator.run("demo")
    assert first_gate["status"] == "AWAITING_REVIEW"
    assert first_gate["pending_approval"]["stage_id"] == "01_research_start"
    orchestrator.review("demo", True, "scope approved")
    resumed_orchestrator = Orchestrator(tmp_path, MockAgentRunner())
    second_gate = resumed_orchestrator.run("demo")
    assert second_gate["status"] == "AWAITING_REVIEW"
    assert second_gate["pending_approval"]["stage_id"] == "05_audit"
    resumed_orchestrator.review("demo", True, "delivery approved")
    completed = resumed_orchestrator.run("demo")
    assert completed["status"] == "COMPLETED"
    assert len(list((tmp_path / "runs" / "demo" / "02_literature").glob("paper_worker-*"))) == 2
    synthesis_inputs = list(
        (tmp_path / "runs" / "demo" / "03_synthesis").glob("*/input/payload.json")
    )
    assert synthesis_inputs
    assert '"previous_artifact": {' in synthesis_inputs[0].read_text(encoding="utf-8")

    inspected = resumed_orchestrator.inspect("demo")
    assert len(inspected["sessions"]) >= 5
    assert inspected["artifacts"]
    run_id = inspected["stage_runs"][0]["run_id"]
    replay = resumed_orchestrator.replay("demo", run_id)
    assert replay["run_manifest"]["run_id"] == run_id
    assert "task_brief.json" in replay["outputs"]
