from pathlib import Path

import fitz

from research_paper_agent.indexing.fts5 import FTS5Index
from research_paper_agent.literature_processor import LiteratureProcessor
from research_paper_agent.parsing.chunking import chunk_document
from research_paper_agent.parsing.pdf_parser import PyMuPDFParser
from research_paper_agent.parsing.quality import assess_document


def make_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "A short method description. Table 1 results are below.\nTable 1: Accuracy 91.2\nFigure 2: Workflow overview\ny_i = w^T x_i + b")
    document.save(path)
    document.close()


def test_parser_and_type_aware_chunks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    make_pdf(pdf_path)
    document = PyMuPDFParser().parse(pdf_path)
    chunks = chunk_document(document, max_words=8, overlap_words=2)
    kinds = {chunk["content_type"] for chunk in chunks}
    assert "text" in kinds
    assert {"table", "figure", "formula"} <= kinds
    assert all(chunk["page"] == 1 for chunk in chunks)
    quality = assess_document(document)
    assert quality["requires_ocr"] is False
    assert quality["detected_elements"]["table"] == 1


def test_processor_writes_artifacts_and_fts5_search(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    make_pdf(pdf_path)
    result = LiteratureProcessor(tmp_path / "index").process(pdf_path, tmp_path / "output")
    assert result["paper_card.json"]["processing_status"] == "parsed"
    assert (tmp_path / "output" / "document_ir.json").exists()
    index = FTS5Index(tmp_path / "index" / "literature.db")
    hits = index.search("accuracy")
    assert hits
    assert hits[0]["content_type"] in {"text", "table", "figure", "formula"}
