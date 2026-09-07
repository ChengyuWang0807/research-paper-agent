from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class NoopReranker:
    """Default ranker: preserve RRF order and make the optional stage explicit."""

    enabled = False

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        del query
        return [dict(item, reranker_score=None, reranker_enabled=False) for item in candidates]


class CallableReranker:
    """Adapter for a local cross-encoder or a remote rerank API."""

    enabled = True

    def __init__(self, score: Callable[[str, str], float]) -> None:
        self.score = score

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for candidate in candidates:
            value = float(self.score(query, str(candidate.get("content", ""))))
            ranked.append((value, candidate))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("chunk_id", ""))))
        return [dict(item, reranker_score=score, reranker_enabled=True, final_rank=index) for index, (score, item) in enumerate(ranked, start=1)]
