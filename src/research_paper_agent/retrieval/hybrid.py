from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..indexing.fts5 import FTS5Index
from .reranker import NoopReranker, Reranker
from .rrf import reciprocal_rank_fusion


class SemanticRetriever(Protocol):
    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...


@dataclass
class RetrievalHit:
    query: str
    evidence_set: list[dict[str, Any]]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"query": self.query, "evidence_set": self.evidence_set, "trace": self.trace}


class HybridRetriever:
    def __init__(
        self,
        fts5: FTS5Index,
        semantic: SemanticRetriever | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.fts5 = fts5
        self.semantic = semantic
        self.reranker = reranker or NoopReranker()

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        candidate_limit: int = 30,
        content_type: str | None = None,
        paper_ids: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> RetrievalHit:
        lexical = self.fts5.search(query, candidate_limit, content_type, paper_ids, metadata_filter)
        semantic: list[dict[str, Any]] = []
        if self.semantic is not None:
            semantic = self.semantic.search(query, candidate_limit)
            semantic = [item for item in semantic if self._matches(item, content_type, paper_ids, metadata_filter)]
        fused = reciprocal_rank_fusion({"bm25": lexical, "semantic": semantic}, limit=candidate_limit)
        reranked = self.reranker.rerank(query, fused)[:limit]
        return RetrievalHit(
            query=query,
            evidence_set=reranked,
            trace={
                "retrievers": {"bm25": len(lexical), "semantic": len(semantic)},
                "candidate_count": len(fused),
                "returned_count": len(reranked),
                "fusion": "rrf",
                "reranker_enabled": bool(getattr(self.reranker, "enabled", False)),
            },
        )

    @staticmethod
    def _matches(item: dict[str, Any], content_type: str | None, paper_ids: list[str] | None, metadata_filter: dict[str, Any] | None) -> bool:
        if content_type and item.get("content_type") != content_type:
            return False
        if paper_ids and item.get("paper_id") not in paper_ids:
            return False
        metadata = item.get("paper_metadata", item.get("metadata", {}))
        return all(metadata.get(key) == value for key, value in (metadata_filter or {}).items())
