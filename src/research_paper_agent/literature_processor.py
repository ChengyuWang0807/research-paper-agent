from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .indexing.fts5 import FTS5Index
from .parsing.chunking import chunk_document
from .parsing.pdf_parser import PyMuPDFParser
from .parsing.quality import assess_document


class LiteratureProcessor:
    """Local, deterministic 02-stage processor used by paper workers and tests."""

    def __init__(self, index_root: str | Path, parser: PyMuPDFParser | None = None) -> None:
        self.index_root = Path(index_root)
        self.index = FTS5Index(self.index_root / "literature.db")
        self.parser = parser or PyMuPDFParser()

    def process(self, pdf_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
        path = Path(pdf_path).expanduser().resolve()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        paper_id = content_hash[:16]
        document = self.parser.parse(path)
        quality = assess_document(document)
        chunks = chunk_document(document)
        title = document.metadata.get("title") or path.stem
        metadata = {
            "paper_id": paper_id, "title": title, "source_path": str(path),
            "authors": [], "first_author_affiliation": None, "country": None,
            "publication_year": None, "venue": None, "doi": None, "arxiv_id": None,
            "source_url": None, "pdf_url": None, "project_url": None,
            "local_pdf_path": str(path), "file_sha256": content_hash,
            "page_count": document.page_count, "parser": document.parser,
            "parser_version": document.parser_version, "content_hash": content_hash,
            "processing_status": "parsed", "quality": quality | {"chunk_count": len(chunks)},
        }
        self.index.upsert_paper(paper_id, title, str(path), metadata, content_hash)
        chunks = [dict(chunk, paper_id=paper_id) for chunk in chunks]
        self.index.add_chunks(paper_id, chunks)
        semantic_status = self._maybe_build_semantic_index(paper_id, chunks)
        evidence = [{"evidence_id": chunk["chunk_id"], "paper_id": paper_id, "page": chunk["page"], "section": chunk["section"], "content_type": chunk["content_type"], "source_text": chunk["source_text"], "content": chunk["content"]} for chunk in chunks]
        paper_card = metadata | {"index": {"fts5": str(self.index.database_path.resolve()), "semantic": semantic_status}}
        parse_report = {"paper_id": paper_id, "parser": document.parser, "parser_version": document.parser_version, "page_count": document.page_count, "chunk_count": len(chunks), "special_chunk_counts": {kind: sum(1 for c in chunks if c["content_type"] == kind) for kind in ("table", "figure", "formula")}, "quality": metadata["quality"], "semantic_index": semantic_status}
        for filename, value in (("paper_card.json", paper_card), ("evidence_cards.json", evidence), ("parse_report.json", parse_report), ("document_ir.json", document.to_dict()), ("chunks.json", chunks)):
            (output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"paper_card.json": paper_card, "evidence_cards.json": evidence, "parse_report.json": parse_report}

    def _maybe_build_semantic_index(self, paper_id: str, chunks: list[dict[str, object]]) -> dict[str, Any]:
        if os.getenv("RPA_ENABLE_SEMANTIC_INDEX", "false").lower() not in {"1", "true", "yes"}:
            return {"status": "disabled", "reason": "set RPA_ENABLE_SEMANTIC_INDEX=true to enable"}
        base_url = os.getenv("RPA_EMBEDDING_BASE_URL")
        model = os.getenv("RPA_EMBEDDING_MODEL", "qwen3-embedding-8b")
        zvec_root = os.getenv("RPA_ZVEC_ROOT")
        if not base_url or not zvec_root:
            return {"status": "skipped", "reason": "RPA_EMBEDDING_BASE_URL and RPA_ZVEC_ROOT are required"}
        try:
            from .embedding.openai_compatible import OpenAICompatibleEmbedding
            from .indexing.zvec_index import ZvecIndex

            vectors = OpenAICompatibleEmbedding(base_url, model)([str(chunk["content"]) for chunk in chunks])
            if not vectors:
                return {"status": "skipped", "reason": "embedding endpoint returned no vectors"}
            index = ZvecIndex(Path(zvec_root) / paper_id, len(vectors[0]), lambda texts: [])
            index.add_vectors(chunks, vectors)
            return {"status": "indexed", "root": str((Path(zvec_root) / paper_id).resolve()), "model": model, "dimension": len(vectors[0])}
        except Exception as error:  # semantic indexing is optional and must not lose parsed artifacts
            return {"status": "failed", "error": str(error)}
