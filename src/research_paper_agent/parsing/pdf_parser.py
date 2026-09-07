from __future__ import annotations

import re
from pathlib import Path

from .models import DocumentElement, DocumentIR, DocumentPage


class PyMuPDFParser:
    """Deterministic baseline parser; heavier layout parsers can implement the same contract."""

    name = "pymupdf"

    def parse(self, pdf_path: str | Path) -> DocumentIR:
        path = Path(pdf_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            import fitz
        except ImportError as error:  # pragma: no cover - exercised in minimal installs
            raise RuntimeError("PyMuPDF is required for PDF processing; install 'PyMuPDF'.") from error

        pages: list[DocumentPage] = []
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                elements = self._detect_elements(text, page_number)
                pages.append(DocumentPage(page_number, text, elements))
            metadata = dict(document.metadata or {})
        return DocumentIR(str(path), self.name, fitz.VersionBind, pages, metadata)

    @staticmethod
    def _detect_elements(text: str, page: int) -> list[DocumentElement]:
        """Keep table/figure/formula markers separate without pretending to recover layout."""
        elements: list[DocumentElement] = []
        for index, line in enumerate(text.splitlines()):
            value = line.strip()
            if not value:
                continue
            lower = value.lower()
            if re.match(r"^(table|tab\.?|表)\s*[-.:#]?\s*\d+", lower):
                kind = "table"
            elif re.match(r"^(figure|fig\.?|图)\s*[-.:#]?\s*\d+", lower):
                kind = "figure"
            elif value.startswith("$$") or ("=" in value and len(value) < 180 and re.search(r"[\^_]", value)):
                kind = "formula"
            else:
                continue
            elements.append(DocumentElement(kind, value, page, element_id=f"{kind}-{page}-{index}", source_text=value))
        return elements
