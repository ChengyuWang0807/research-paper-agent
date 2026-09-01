from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from .models import AgentContract, AgentResult, RunStatus


class AgentRunner(Protocol):
    def run(self, contract: AgentContract, system_prompt: str, workspace: Path, payload: dict[str, Any], run_id: str) -> AgentResult: ...


class MockAgentRunner:
    """Deterministic harness used to validate orchestration before model integration."""

    def run(self, contract: AgentContract, system_prompt: str, workspace: Path, payload: dict[str, Any], run_id: str) -> AgentResult:
        del system_prompt
        outputs = self._build_outputs(contract.agent_id, payload)
        for filename in contract.required_outputs:
            value = outputs.get(filename)
            if value is None:
                return AgentResult(contract.agent_id, run_id, RunStatus.FAILED, issues=[{"type": "missing_output", "filename": filename}])
            (workspace / "output" / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return AgentResult(contract.agent_id, run_id, RunStatus.SUCCEEDED, outputs)

    def _build_outputs(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if agent_id == "research_starter":
            return {"task_brief.json": {"topic": payload["topic"], "research_questions": [f"{payload['topic']} 的核心方法、证据和局限是什么？"], "scope": {"paper_count": len(payload.get("paper_paths", []))}, "status": "awaiting_human_confirmation"}}
        if agent_id == "paper_worker":
            paper_path = payload["paper_path"]
            paper_id = hashlib.sha256(paper_path.encode("utf-8")).hexdigest()[:12]
            return {"paper_card.json": {"paper_id": paper_id, "source_path": paper_path, "title": Path(paper_path).stem, "processing_status": "mock_parsed"}, "evidence_cards.json": [], "parse_report.json": {"paper_id": paper_id, "quality": 1.0, "note": "Mock Harness does not parse PDF contents."}}
        if agent_id == "literature_supervisor":
            workers = payload.get("worker_results", [])
            return {"literature_package.json": {"paper_count": len(workers), "papers": [item["paper_card.json"] for item in workers], "evidence_card_count": sum(len(item["evidence_cards.json"]) for item in workers)}}
        if agent_id == "knowledge_synthesizer":
            return {"knowledge_pack.json": {"topic": payload["topic"], "themes": [], "claims": [], "gaps": [], "source_artifact": payload.get("previous_artifact")}}
        if agent_id == "paper_writer":
            return {"writing_package.json": {"title": payload["topic"], "outline": ["引言", "相关工作", "讨论", "结论"], "draft": "Mock Harness draft. Connect a real harness for evidence-grounded writing.", "claim_evidence_map": []}}
        if agent_id == "citation_auditor":
            return {"audit_report.json": {"passed": True, "citation_issues": [], "note": "Mock Harness audit only validates workflow wiring."}}
        raise ValueError(f"unsupported mock agent: {agent_id}")

