from __future__ import annotations

from typing import Any

from .models import DocumentIR


def assess_document(document: DocumentIR, *, min_page_characters: int = 30) -> dict[str, Any]:
    empty_pages = [page.page for page in document.pages if not page.text.strip()]
    low_text_pages = [page.page for page in document.pages if 0 < len(page.text.strip()) < min_page_characters]
    counts = {
        kind: sum(element.content_type == kind for page in document.pages for element in page.elements)
        for kind in ("table", "figure", "formula")
    }
    return {
        "empty_pages": empty_pages,
        "low_text_pages": low_text_pages,
        "requires_ocr": bool(empty_pages or low_text_pages),
        "requires_table_enhancement": counts["table"] > 0,
        "requires_formula_enhancement": counts["formula"] > 0,
        "detected_elements": counts,
        "manual_review_required": bool(empty_pages or low_text_pages),
    }
