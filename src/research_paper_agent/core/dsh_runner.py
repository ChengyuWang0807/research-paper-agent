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
    api_key_env: str = "DEEPSEEK_API_KEY"
    dsh_home: str | None = None

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
            base_url=os.getenv("RPA_DSH_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or None,
            api_key_env=os.getenv("RPA_DSH_API_KEY_ENV", "DEEPSEEK_API_KEY"),
            dsh_home=os.getenv("RPA_DSH_HOME") or None,
        )


class DeepSeekHarnessRunner:
    """Run one contracted Agent Run in an isolated DSH session.

    The SDK is imported lazily so Mock mode and unit tests do not require the
    optional DSH runtime package or an API key.  Despite the historical class
    name, the provider is selected by :class:`DshSettings` and can be a custom
    OpenAI-compatible endpoint such as Qwen served by vLLM.
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

        runtime = payload.get("_runtime", {}) if isinstance(payload, dict) else {}
        session_root = workspace / "dsh_session"
        session_root.mkdir(parents=True, exist_ok=True)
        configured_home = runtime.get("dsh_home") if isinstance(runtime, dict) else None
        dsh_home = Path(configured_home).expanduser().resolve() if configured_home else (
            Path(self.settings.dsh_home).expanduser().resolve() if self.settings.dsh_home else workspace / "dsh_home"
        )
        dsh_home.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(contract, system_prompt, payload)
        env = {
            "DSH_SYSTEM_PROMPT": system_prompt,
            "DSH_MODEL": self.settings.model,
            "DSH_CWD": str(workspace.resolve()),
            "DSH_SESSION_ROOT": str(session_root.resolve()),
            "DSH_HOME": str(dsh_home),
            "RPA_DSH_API_KEY_ENV": self.settings.api_key_env,
        }
        if self.settings.base_url:
            env["RPA_DSH_BASE_URL"] = self.settings.base_url
        if self.settings.cordis:
            env["DSH_CORDIS_CONFIG"] = str(Path(self.settings.cordis).expanduser().resolve())

        harness_kwargs = {
            "provider": self.settings.provider,
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "cwd": str(workspace.resolve()),
            "dsh_home": str(dsh_home),
            "env": env,
            "request_timeout_seconds": self.settings.request_timeout_seconds,
        }
        try:
            # `cordis` and `session_root` existed in an earlier SDK API. The
            # released 0.1.x SDK uses DSH_CORDIS_CONFIG/DSH_SESSION_ROOT and
            # dsh_home instead, so keep the kwargs compatible with both.
            try:
                from deepseek_harness import DeepSeekHarnessConfig

                supported = getattr(DeepSeekHarnessConfig, "__annotations__", {})
            except ImportError:
                supported = {}
            if "base_url" in supported and self.settings.base_url and not self.settings.cordis:
                harness_kwargs["base_url"] = self.settings.base_url
            if "session_root" in supported:
                harness_kwargs["session_root"] = str(session_root.resolve())
            if "cordis" in supported and self.settings.cordis:
                harness_kwargs["cordis"] = self.settings.cordis
            with DeepSeekHarness(**harness_kwargs) as harness:
                session_id = runtime.get("session_id") if isinstance(runtime, dict) else None
                try:
                    result = harness.run(prompt, session_id=session_id)
                except TypeError as error:
                    # Keep compatibility with older/fake SDKs whose run method
                    # accepts only the prompt while using session reuse when it
                    # is supported by the installed SDK.
                    if "session_id" not in str(error):
                        raise
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
    def _build_prompt(contract: AgentContract, system_prompt: str, payload: dict[str, Any]) -> str:
        model_payload = {key: value for key, value in payload.items() if key != "_runtime"}
        payload_text = json.dumps(model_payload, ensure_ascii=False, indent=2)
        required = ", ".join(contract.required_outputs)
        return (
            "You are executing exactly one contracted Research-Paper-Agent job.\n"
            "Follow the role instructions below as the highest-priority task instructions.\n"
            f"ROLE INSTRUCTIONS:\n{system_prompt}\n\n"
            f"REQUIRED OUTPUT FILES: {required}\n"
            "Only read the INPUT PAYLOAD in this turn and write the required JSON files under output/. "
            "Do not inspect or summarize DSH internals, prior runs, skills, logs, manifests, or files outside "
            "the current workspace. Do not write any extra report or prose file. Do not put runtime paths, "
            "session diagnostics, tool traces, or unsupported claims into the contracted JSON. "
            "If the payload lacks evidence, represent that as an empty list, null, or an explicit pending item; "
            "never invent facts. After writing the required files, stop.\n\n"
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
