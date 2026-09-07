import sys
import types
from pathlib import Path

from research_paper_agent.core.dsh_runner import DeepSeekHarnessRunner, DshSettings
from research_paper_agent.core.models import AgentContract, RunStatus


def test_dsh_runner_uses_workspace_and_reads_structured_outputs(tmp_path: Path, monkeypatch) -> None:
    class FakeResult:
        session_id = "session-test"
        finish_reason = "completed"
        events = [{"type": "turn/end"}]
        notifications = []
        session_root = "session-root"
        final_response = "done"

    class FakeHarness:
        received = None

        def __init__(self, **kwargs):
            FakeHarness.received = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, _prompt):
            (Path(FakeHarness.received["cwd"]) / "output" / "result.json").write_text("{}", encoding="utf-8")
            return FakeResult()

    fake_module = types.SimpleNamespace(DeepSeekHarness=FakeHarness)
    monkeypatch.setitem(sys.modules, "deepseek_harness", fake_module)
    workspace = tmp_path / "workspace"
    for name in ("input", "scratch", "output", "logs"):
        (workspace / name).mkdir(parents=True)
    contract = AgentContract("fake", ["test"], ["payload"], ["result.json"], [], ["result.json"], "never")

    result = DeepSeekHarnessRunner(DshSettings(model="test-model")).run(contract, "role", workspace, {"x": 1}, "run-1")

    assert result.status is RunStatus.SUCCEEDED
    assert FakeHarness.received["cwd"] == str(workspace.resolve())
    assert FakeHarness.received["env"]["DSH_CWD"] == str(workspace.resolve())
    assert FakeHarness.received["env"]["DSH_SESSION_ROOT"] == str((workspace / "dsh_session").resolve())
    assert FakeHarness.received["dsh_home"] == str((workspace / "dsh_home").resolve())
    assert (workspace / "logs" / "dsh_result.json").exists()


def test_dsh_settings_support_generic_provider_environment(monkeypatch) -> None:
    monkeypatch.setenv("RPA_DSH_PROVIDER", "qwen-vllm")
    monkeypatch.setenv("RPA_DSH_MODEL", "qwen36-35b-a3b")
    monkeypatch.setenv("RPA_DSH_API_KEY_ENV", "RPA_VLLM_API_KEY")
    monkeypatch.setenv("RPA_DSH_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("RPA_DSH_CORDIS", "config/dsh/qwen-vllm.cordis.yml")

    settings = DshSettings.from_environment()

    assert settings.provider == "qwen-vllm"
    assert settings.model == "qwen36-35b-a3b"
    assert settings.api_key_env == "RPA_VLLM_API_KEY"
    assert settings.base_url == "https://gateway.example/v1"
    assert settings.cordis == "config/dsh/qwen-vllm.cordis.yml"
