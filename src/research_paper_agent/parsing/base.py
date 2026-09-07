from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import DocumentIR


class DocumentParser(Protocol):
    name: str

    def parse(self, pdf_path: str | Path) -> DocumentIR: ...


class DocumentEnhancer(Protocol):
    """Adapter contract for table, OCR or formula-specific processors."""

    name: str
    content_types: tuple[str, ...]

    def enhance(self, document: DocumentIR) -> DocumentIR: ...
