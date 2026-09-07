from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Any


def evaluate_retriever(
    search: Callable[[str], Any],
    queries: Iterable[dict[str, Any]],
    *,
    ks: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Evaluate Recall@K, MRR and nDCG from a small hand-labelled query set.

    Each query contains ``query`` and ``relevant_ids``. ``search`` may return a
    RetrievalHit or a plain list of result dictionaries.
    """
    query_list = list(queries)
    rows: list[dict[str, Any]] = []
    for item in query_list:
        result = search(str(item["query"]))
        ranked = result.evidence_set if hasattr(result, "evidence_set") else result
        ranked_ids = [str(hit.get("chunk_id") or hit.get("evidence_id") or hit.get("id")) for hit in ranked]
        relevant = {str(value) for value in item.get("relevant_ids", [])}
        first = next((rank for rank, hit_id in enumerate(ranked_ids, start=1) if hit_id in relevant), None)
        rows.append({"query": item["query"], "relevant_ids": relevant, "relevant_count": len(relevant), "first_relevant_rank": first, "ranked_ids": ranked_ids})

    count = len(rows)
    metrics: dict[str, float] = {}
    for k in ks:
        recall_values = []
        for row in rows:
            retrieved = sum(hit_id in row["relevant_ids"] for hit_id in row["ranked_ids"][:k])
            recall_values.append(retrieved / len(row["relevant_ids"]) if row["relevant_ids"] else 0.0)
        metrics[f"recall_at_{k}"] = sum(recall_values) / count if count else 0.0
        ndcg_values = []
        for row in rows:
            dcg = sum(1.0 / math.log2(rank + 1) for rank, hit_id in enumerate(row["ranked_ids"][:k], start=1) if hit_id in row["relevant_ids"])
            ideal_count = min(len(row["relevant_ids"]), k)
            ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
            ndcg_values.append(dcg / ideal if ideal else 0.0)
        metrics[f"ndcg_at_{k}"] = sum(ndcg_values) / count if count else 0.0
    metrics["mrr"] = sum(1.0 / row["first_relevant_rank"] for row in rows if row["first_relevant_rank"]) / count if count else 0.0
    public_rows = [dict(row, relevant_ids=sorted(row["relevant_ids"])) for row in rows]
    return {"query_count": count, "metrics": metrics, "rows": public_rows}
