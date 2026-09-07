from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class QueryPlan:
    """One independently executable retrieval request for a synthesis question."""

    plan_id: str
    sub_question: str
    query: str
    keywords: list[str] = field(default_factory=list)
    content_types: list[str] = field(default_factory=lambda: ["text", "table", "figure", "formula"])
    metadata_filter: dict[str, Any] = field(default_factory=dict)
    candidate_limit: int = 30
    evidence_limit: int = 8

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _keywords(text: str) -> list[str]:
    # Keep method names, metrics, identifiers and CJK spans; discard punctuation.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}", text)
    stopwords = {"and", "or", "the", "of", "in", "to", "is", "are", "what", "how"}
    return [token for token in dict.fromkeys(tokens) if token.lower() not in stopwords][:12]


def _fts_query(terms: list[str], fallback: str) -> str:
    usable = terms or [fallback]
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in usable)


def build_query_plan(
    topic: str,
    research_questions: Iterable[str] | None = None,
    *,
    metadata_filter: dict[str, Any] | None = None,
    candidate_limit: int = 30,
    evidence_limit: int = 8,
) -> list[QueryPlan]:
    questions = [str(item).strip() for item in (research_questions or []) if str(item).strip()]
    if not questions:
        questions = [
            f"{topic} 的核心方法和任务定义是什么？",
            f"{topic} 的实验结果、证据和局限是什么？",
        ]
    plans: list[QueryPlan] = []
    for index, question in enumerate(questions, start=1):
        terms = _keywords(question)
        plans.append(
            QueryPlan(
                plan_id=f"subq-{index:02d}",
                sub_question=question,
                query=_fts_query(terms, question),
                keywords=terms,
                metadata_filter=dict(metadata_filter or {}),
                candidate_limit=candidate_limit,
                evidence_limit=evidence_limit,
            )
        )
    return plans
