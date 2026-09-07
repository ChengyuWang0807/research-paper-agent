from __future__ import annotations

import hashlib
import re
from .models import DocumentElement, DocumentIR


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _make_chunk(content: str, content_type: str, page: int, section: str, source_text: str = "", **extra: object) -> dict[str, object]:
    digest = hashlib.sha256(f"{content_type}|{page}|{content}".encode("utf-8")).hexdigest()[:16]
    result: dict[str, object] = {
        "chunk_id": f"chunk-{digest}",
        "content_type": content_type,
        "section": section,
        "page": page,
        "content": content.strip(),
        "source_text": source_text or content,
        "asset_ref": extra.pop("asset_ref", None),
    }
    result.update(extra)
    return result


def chunk_document(document: DocumentIR, max_words: int = 450, overlap_words: int = 80) -> list[dict[str, object]]:
    """Create text chunks plus atomic table/figure/formula chunks with provenance."""
    chunks: list[dict[str, object]] = []
    special_by_page: dict[int, list[DocumentElement]] = {}
    for page in document.pages:
        special_by_page[page.page] = page.elements
        words = _words(page.text)
        if words:
            step = max(1, max_words - overlap_words)
            for start in range(0, len(words), step):
                content = " ".join(words[start : start + max_words])
                if content:
                    chunks.append(_make_chunk(content, "text", page.page, "", page.text, parser_version=document.parser_version))
                if start + max_words >= len(words):
                    break
        for element in special_by_page[page.page]:
            chunks.append(_make_chunk(element.content, element.content_type, element.page, element.section, element.source_text or element.content, asset_ref=element.asset_ref, element_id=element.element_id, parser_version=document.parser_version))
    return chunks
