from pathlib import Path

from research_paper_agent.indexing.fts5 import FTS5Index
from research_paper_agent.evaluation.retrieval_eval import evaluate_retriever
from research_paper_agent.retrieval.hybrid import HybridRetriever
from research_paper_agent.retrieval.integration import KnowledgeIntegrator
from research_paper_agent.retrieval.reranker import CallableReranker
from research_paper_agent.retrieval.rrf import reciprocal_rank_fusion


class FakeSemanticRetriever:
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results

    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        del query
        return self.results[:limit]


def seed_index(path: Path) -> FTS5Index:
    index = FTS5Index(path)
    index.upsert_paper("paper-a", "A", "a.pdf", {"publication_year": 2026, "country": "CN"}, "hash-a")
    index.upsert_paper("paper-b", "B", "b.pdf", {"publication_year": 2025, "country": "US"}, "hash-b")
    index.add_chunks(
        "paper-a",
        [{"chunk_id": "a-1", "content_type": "text", "page": 1, "section": "method", "content": "context isolation and handoff", "source_text": "context isolation and handoff"}],
    )
    index.add_chunks(
        "paper-b",
        [{"chunk_id": "b-1", "content_type": "table", "page": 2, "section": "results", "content": "accuracy comparison", "source_text": "accuracy comparison"}],
    )
    return index


def test_rrf_keeps_source_ranks_and_deduplicates() -> None:
    result = reciprocal_rank_fusion({"bm25": [{"chunk_id": "a"}, {"chunk_id": "b"}], "semantic": [{"chunk_id": "b"}, {"chunk_id": "a"}]}, limit=2)
    assert [item["chunk_id"] for item in result] == ["a", "b"]
    assert result[0]["retrieval_sources"] == ["bm25", "semantic"]
    assert result[0]["retrieval_ranks"] == {"bm25": 1, "semantic": 2}


def test_hybrid_retrieval_supports_metadata_and_type_filters(tmp_path: Path) -> None:
    index = seed_index(tmp_path / "literature.db")
    retriever = HybridRetriever(index, FakeSemanticRetriever([{"chunk_id": "a-1", "paper_id": "paper-a", "content_type": "text", "content": "context isolation", "paper_metadata": {"publication_year": 2026}}]))
    result = retriever.search("context", metadata_filter={"publication_year": 2026}, content_type="text")
    assert result.evidence_set[0]["chunk_id"] == "a-1"
    assert result.trace["fusion"] == "rrf"
    assert result.trace["reranker_enabled"] is False


def test_reranker_is_optional_and_can_be_injected(tmp_path: Path) -> None:
    index = seed_index(tmp_path / "literature.db")
    reranker = CallableReranker(lambda query, content: 1.0 if query in content else 0.0)
    result = HybridRetriever(index, reranker=reranker).search("context", limit=2)
    assert result.trace["reranker_enabled"] is True
    assert result.evidence_set[0]["reranker_score"] == 1.0


def test_retrieval_evaluation_reports_recall_mrr_and_ndcg() -> None:
    def search(query: str) -> list[dict[str, str]]:
        del query
        return [{"chunk_id": "wrong"}, {"chunk_id": "right"}]

    report = evaluate_retriever(search, [{"query": "q", "relevant_ids": ["right"]}], ks=(1, 3))
    assert report["metrics"]["recall_at_1"] == 0.0
    assert report["metrics"]["recall_at_3"] == 1.0
    assert report["metrics"]["mrr"] == 0.5
    assert 0.0 < report["metrics"]["ndcg_at_3"] < 1.0


def test_knowledge_integrator_builds_subquestion_evidence_and_feedback(tmp_path: Path) -> None:
    index = seed_index(tmp_path / "literature.db")
    result = KnowledgeIntegrator(index.database_path).integrate(
        "context isolation",
        ["context isolation and handoff", "accuracy comparison"],
        evidence_limit=2,
    )
    assert len(result.query_plan) == 2
    assert result.coverage["covered_subquestion_count"] == 2
    assert result.coverage["sufficient"] is True
    assert result.feedback_actions == []
    assert result.evidence_set[0]["evidence_id"] == "a-1"
