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
        outputs = self._build_outputs(contract.agent_id, payload, workspace)
        for filename in contract.required_outputs:
            value = outputs.get(filename)
            if value is None:
                return AgentResult(contract.agent_id, run_id, RunStatus.FAILED, issues=[{"type": "missing_output", "filename": filename}])
            (workspace / "output" / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return AgentResult(contract.agent_id, run_id, RunStatus.SUCCEEDED, outputs)

    def _build_outputs(self, agent_id: str, payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
        if agent_id == "research_starter":
            return {"task_brief.json": {"topic": payload["topic"], "research_questions": [f"{payload['topic']} 的核心方法、证据和局限是什么？"], "scope": {"paper_count": len(payload.get("paper_paths", []))}, "status": "awaiting_human_confirmation"}}
        if agent_id == "paper_worker":
            paper_path = payload["paper_path"]
            if Path(paper_path).is_file() and Path(paper_path).suffix.lower() == ".pdf":
                from ..literature_processor import LiteratureProcessor

                processor = LiteratureProcessor(Path(payload.get("project_root", workspace)) / "data" / "literature")
                return processor.process(paper_path, workspace / "output")
            paper_id = hashlib.sha256(paper_path.encode("utf-8")).hexdigest()[:12]
            return {"paper_card.json": {"paper_id": paper_id, "source_path": paper_path, "title": Path(paper_path).stem, "processing_status": "mock_parsed"}, "evidence_cards.json": [], "parse_report.json": {"paper_id": paper_id, "quality": 1.0, "note": "Mock Harness does not parse PDF contents."}}
        if agent_id == "literature_supervisor":
            workers = payload.get("worker_results", [])
            return {"literature_package.json": {
                "paper_count": len(workers),
                "papers": [item["paper_card.json"] for item in workers],
                "evidence_card_count": sum(len(item["evidence_cards.json"]) for item in workers),
                "indexes": {"fts5": str((Path(payload.get("project_root", workspace)) / "data" / "literature" / "literature.db").resolve())},
                "coverage": {"workers_succeeded": len(workers), "workers_failed": 0},
            }}
        if agent_id == "knowledge_synthesizer":
            from ..retrieval.integration import KnowledgeIntegrator

            index_path = Path(payload.get("project_root", workspace)) / "data" / "literature" / "literature.db"
            previous = payload.get("previous_output") or {}
            outputs = previous.get("outputs", previous) if isinstance(previous, dict) else {}
            literature = outputs.get("literature_package.json", {}) if isinstance(outputs, dict) else {}
            research_questions = []
            prior = payload.get("prior_task_brief") or {}
            if isinstance(prior, dict):
                research_questions = prior.get("research_questions", [])
            if not research_questions and payload.get("topic"):
                research_questions = [f"{payload['topic']} 的核心方法、证据和局限是什么？"]
            package = payload.get("retrieval_package")
            if not isinstance(package, dict) or package.get("status") == "unavailable":
                result = KnowledgeIntegrator(index_path).integrate(
                    payload["topic"],
                    research_questions,
                    candidate_limit=30,
                    evidence_limit=8,
                )
                package = result.to_dict()
            package["source_artifact"] = payload.get("previous_artifact")
            package["literature_package"] = {
                "paper_count": literature.get("paper_count", 0),
                "indexes": literature.get("indexes", {}),
            }
            return {"knowledge_pack.json": package}
        if agent_id == "paper_writer":
            return {"writing_package.json": {"title": payload["topic"], "outline": ["引言", "相关工作", "讨论", "结论"], "draft": "Mock Harness draft. Connect a real harness for evidence-grounded writing.", "claim_evidence_map": []}}
        if agent_id == "citation_auditor":
            return {"audit_report.json": {"passed": True, "citation_issues": [], "note": "Mock Harness audit only validates workflow wiring."}}
        raise ValueError(f"unsupported mock agent: {agent_id}")
