from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..indexing.fts5 import FTS5Index
from .hybrid import HybridRetriever
from .query_plan import QueryPlan, build_query_plan


@dataclass
class KnowledgeIntegrationResult:
    topic: str
    query_plan: list[dict[str, Any]]
    subquestion_results: list[dict[str, Any]]
    evidence_set: list[dict[str, Any]]
    retrieval_trace: dict[str, Any]
    coverage: dict[str, Any]
    feedback_actions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "query_plan": self.query_plan,
            "subquestion_results": self.subquestion_results,
            "evidence_set": self.evidence_set,
            "retrieval_trace": self.retrieval_trace,
            "coverage": self.coverage,
            "feedback_actions": self.feedback_actions,
        }


class KnowledgeIntegrator:
    """Execute query plans deterministically and return a traceable evidence package."""

    def __init__(self, database_path: str | Path, semantic: Any | None = None, reranker: Any | None = None) -> None:
        self.retriever = HybridRetriever(FTS5Index(database_path), semantic=semantic, reranker=reranker)

    def integrate(
        self,
        topic: str,
        research_questions: Iterable[str] | None = None,
        *,
        metadata_filter: dict[str, Any] | None = None,
        candidate_limit: int = 30,
        evidence_limit: int = 8,
    ) -> KnowledgeIntegrationResult:
        plans = build_query_plan(topic, research_questions, metadata_filter=metadata_filter, candidate_limit=candidate_limit, evidence_limit=evidence_limit)
        subquestion_results: list[dict[str, Any]] = []
        unique: dict[str, dict[str, Any]] = {}
        traces: list[dict[str, Any]] = []
        for plan in plans:
            hit = self.retriever.search(plan.query, limit=plan.evidence_limit, candidate_limit=plan.candidate_limit, metadata_filter=plan.metadata_filter)
            evidence = [self._normalize_evidence(item, plan) for item in hit.evidence_set if self._valid_evidence(item)]
            for item in evidence:
                unique.setdefault(str(item["evidence_id"]), item)
            trace = dict(hit.trace, plan_id=plan.plan_id, query=plan.query)
            traces.append(trace)
            subquestion_results.append({"plan_id": plan.plan_id, "sub_question": plan.sub_question, "evidence_ids": [item["evidence_id"] for item in evidence], "trace": trace})
        coverage = self._coverage(plans, subquestion_results, unique)
        feedback = self._feedback(plans, coverage)
        return KnowledgeIntegrationResult(
            topic=topic,
            query_plan=[plan.to_dict() for plan in plans],
            subquestion_results=subquestion_results,
            evidence_set=list(unique.values()),
            retrieval_trace={"subqueries": traces, "plans": len(plans), "unique_evidence_count": len(unique), "fusion": "rrf"},
            coverage=coverage,
            feedback_actions=feedback,
        )

    @staticmethod
    def _normalize_evidence(item: dict[str, Any], plan: QueryPlan) -> dict[str, Any]:
        evidence = {
            "evidence_id": item.get("chunk_id"),
            "chunk_id": item.get("chunk_id"),
            "paper_id": item.get("paper_id"),
            "page": item.get("page"),
            "section": item.get("section", ""),
            "content_type": item.get("content_type", "text"),
            "content": item.get("content", ""),
            "source_text": item.get("source_text", ""),
            "metadata": item.get("paper_metadata", item.get("metadata", {})),
            "retrieval_sources": item.get("retrieval_sources", []),
            "retrieval_ranks": item.get("retrieval_ranks", {}),
            "lexical_score": item.get("lexical_score"),
            "semantic_score": item.get("semantic_score"),
            "rrf_score": item.get("rrf_score"),
            "reranker_score": item.get("reranker_score"),
            "reranker_enabled": item.get("reranker_enabled", False),
            "final_rank": item.get("final_rank"),
            "matched_plan_id": plan.plan_id,
        }
        return evidence

    @staticmethod
    def _valid_evidence(item: dict[str, Any]) -> bool:
        return bool(
            (item.get("evidence_id") or item.get("chunk_id"))
            and item.get("paper_id")
            and item.get("page") is not None
            and item.get("source_text")
        )

    @staticmethod
    def _coverage(plans: list[QueryPlan], results: list[dict[str, Any]], unique: dict[str, dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(item["paper_id"] for item in unique.values())
        covered = sum(bool(item["evidence_ids"]) for item in results)
        return {
            "subquestion_count": len(plans),
            "covered_subquestion_count": covered,
            "coverage_ratio": covered / len(plans) if plans else 0.0,
            "unique_evidence_count": len(unique),
            "paper_count": len(counts),
            "evidence_by_paper": dict(counts),
            "sufficient": bool(plans) and covered == len(plans) and bool(unique),
        }

    @staticmethod
    def _feedback(plans: list[QueryPlan], coverage: dict[str, Any]) -> list[dict[str, Any]]:
        if coverage["sufficient"]:
            return []
        actions: list[dict[str, Any]] = []
        if coverage["covered_subquestion_count"] < coverage["subquestion_count"]:
            actions.append({"action": "expand_query", "reason": "one or more subquestions returned no traceable evidence", "target": "03_synthesis"})
        if coverage["paper_count"] < 2 and len(plans) > 1:
            actions.append({"action": "check_cross_paper_coverage", "reason": "evidence comes from fewer than two papers", "target": "03_synthesis"})
        actions.append({"action": "manual_review", "reason": "evidence coverage is below the configured threshold", "target": "human"})
        return actions
