from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentElement:
    content_type: str
    content: str
    page: int
    section: str = ""
    element_id: str | None = None
    asset_ref: str | None = None
    bbox: list[float] | None = None
    source_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentPage:
    page: int
    text: str
    elements: list[DocumentElement] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page, "text": self.text, "elements": [e.to_dict() for e in self.elements]}


@dataclass
class DocumentIR:
    source_path: str
    parser: str
    parser_version: str
    pages: list[DocumentPage]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "parser": self.parser,
            "parser_version": self.parser_version,
            "page_count": self.page_count,
            "metadata": self.metadata,
            "pages": [page.to_dict() for page in self.pages],
        }
