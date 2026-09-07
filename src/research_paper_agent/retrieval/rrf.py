from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def reciprocal_rank_fusion(
    ranked_lists: dict[str, Iterable[dict[str, Any]]],
    *,
    limit: int = 20,
    k: int = 60,
) -> list[dict[str, Any]]:
    """Fuse ranked results using ranks, keeping provenance from every retriever."""
    scores: dict[str, float] = defaultdict(float)
    records: dict[str, dict[str, Any]] = {}
    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    for source, results in ranked_lists.items():
        for rank, result in enumerate(results, start=1):
            item_id = str(result.get("chunk_id") or result.get("evidence_id") or result.get("id"))
            if item_id == "None":
                continue
            scores[item_id] += 1.0 / (k + rank)
            ranks[item_id][source] = rank
            records.setdefault(item_id, dict(result))
    fused: list[dict[str, Any]] = []
    for final_rank, item_id in enumerate(sorted(scores, key=lambda key: (-scores[key], key))[:limit], start=1):
        item = records[item_id]
        item.update(
            {
                "chunk_id": item_id,
                "rrf_score": scores[item_id],
                "retrieval_sources": sorted(ranks[item_id]),
                "retrieval_ranks": ranks[item_id],
                "final_rank": final_rank,
            }
        )
        fused.append(item)
    return fused
