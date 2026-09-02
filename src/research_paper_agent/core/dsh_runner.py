from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AgentContract, AgentResult, RunStatus


@dataclass(frozen=True)
class DshSettings:
    provider: str = "deepseek-official"
    model: str = "deepseek-v4-flash"
    max_tokens: int | None = None
    request_timeout_seconds: float | None = 900.0
    cordis: str | None = None
    base_url: str | None = None

    @classmethod
    def from_environment(cls) -> "DshSettings":
        max_tokens = os.getenv("RPA_DSH_MAX_TOKENS")
        timeout = os.getenv("RPA_DSH_TIMEOUT_SECONDS", "900")
        return cls(
            provider=os.getenv("RPA_DSH_PROVIDER", "deepseek-official"),
            model=os.getenv("RPA_DSH_MODEL", "deepseek-v4-flash"),
            max_tokens=int(max_tokens) if max_tokens else None,
            request_timeout_seconds=float(timeout) if timeout else None,
            cordis=os.getenv("RPA_DSH_CORDIS") or None,
            base_url=os.getenv("DEEPSEEK_BASE_URL") or None,
        )


class DeepSeekHarnessRunner:
    """Run one contracted Agent Run in an isolated DeepSeek Harness session.

    The SDK is imported lazily so Mock mode and unit tests do not require the
    optional DSH runtime package or an API key.
    """

    def __init__(self, settings: DshSettings | None = None) -> None:
        self.settings = settings or DshSettings.from_environment()

    def run(
        self,
        contract: AgentContract,
        system_prompt: str,
        workspace: Path,
        payload: dict[str, Any],
        run_id: str,
    ) -> AgentResult:
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as error:
            return AgentResult(
                contract.agent_id,
                run_id,
                RunStatus.FAILED,
                issues=[
                    {
                        "type": "dependency_missing",
                        "package": "deepseek-harness-sdk",
                        "message": str(error),
                    }
                ],
            )

        session_root = workspace / "dsh_session"
        session_root.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(contract, payload)
        env = {"DSH_SYSTEM_PROMPT": system_prompt, "DSH_MODEL": self.settings.model}
        try:
            with DeepSeekHarness(
                provider=self.settings.provider,
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                cwd=str(workspace.resolve()),
                session_root=str(session_root.resolve()),
                cordis=self.settings.cordis,
                base_url=self.settings.base_url,
                env=env,
                request_timeout_seconds=self.settings.request_timeout_seconds,
            ) as harness:
                result = harness.run(prompt)
        except Exception as error:  # SDK errors are part of the run contract.
            self._write_json(workspace / "logs" / "dsh_result.json", {"error": str(error)})
            return AgentResult(
                contract.agent_id,
                run_id,
                RunStatus.FAILED,
                issues=[{"type": "dsh_runtime_error", "message": str(error)}],
            )

        self._write_json(
            workspace / "logs" / "dsh_result.json",
            {
                "session_id": getattr(result, "session_id", None),
                "finish_reason": getattr(result, "finish_reason", None),
                "events": self._jsonable(getattr(result, "events", [])),
                "notifications": self._jsonable(getattr(result, "notifications", [])),
                "session_root": getattr(result, "session_root", None),
            },
        )
        outputs, issues = self._read_outputs(contract, workspace)
        finish_reason = getattr(result, "finish_reason", None)
        if finish_reason == "error":
            issues.append({"type": "dsh_finish_error", "message": getattr(result, "final_response", "")})
        if issues:
            return AgentResult(contract.agent_id, run_id, RunStatus.FAILED, outputs, issues)
        return AgentResult(contract.agent_id, run_id, RunStatus.SUCCEEDED, outputs)

    @staticmethod
    def _build_prompt(contract: AgentContract, payload: dict[str, Any]) -> str:
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        required = ", ".join(contract.required_outputs)
        return (
            "Execute exactly one Research-Paper-Agent job in the current workspace.\n"
            f"Required output files: {required}.\n"
            "Read the input payload below. Write each required JSON file under output/. "
            "Do not write outside the current workspace and do not invent missing evidence.\n\n"
            f"INPUT PAYLOAD:\n{payload_text}"
        )

    @staticmethod
    def _read_outputs(contract: AgentContract, workspace: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        outputs: dict[str, Any] = {}
        issues: list[dict[str, Any]] = []
        output_dir = workspace / "output"
        for filename in contract.required_outputs:
            path = output_dir / filename
            if not path.is_file():
                issues.append({"type": "missing_output", "filename": filename})
                continue
            try:
                outputs[filename] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                issues.append({"type": "invalid_json", "filename": filename, "message": str(error)})
        return outputs, issues

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonable(item) for item in value]
        for method_name in ("model_dump", "to_dict"):
            method = getattr(value, method_name, None)
            if callable(method):
                return cls._jsonable(method())
        return str(value)

