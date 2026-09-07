from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class ZvecIndex:
    """Small adapter around Zvec; import is delayed so keyword-only installs still work."""

    def __init__(self, root: str | Path, dimension: int, embed: Callable[[list[str]], list[list[float]]]) -> None:
        self.root = Path(root)
        self.dimension = dimension
        self.embed = embed
        self.root.mkdir(parents=True, exist_ok=True)
        self._collection = None

    def _load(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import zvec
        except ImportError as error:
            raise RuntimeError("Zvec is optional. Install with 'pip install -e .[retrieval]'.") from error
        # Zvec's public API has changed across prereleases; keep construction in one adapter.
        if hasattr(zvec, "open"):
            self._collection = zvec.open(str(self.root), dimension=self.dimension)
        elif hasattr(zvec, "Collection"):
            self._collection = zvec.Collection(str(self.root), dimension=self.dimension)
        else:
            raise RuntimeError("Unsupported Zvec version: no open/Collection API found")
        return self._collection

    def add(self, chunks: list[dict[str, Any]]) -> None:
        collection = self._load()
        vectors = self.embed([str(chunk["content"]) for chunk in chunks])
        self.add_vectors(chunks, vectors, collection=collection)

    def add_vectors(self, chunks: list[dict[str, Any]], vectors: list[list[float]], collection: Any | None = None) -> None:
        collection = collection or self._load()
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        records = [{"id": chunk["chunk_id"], "vector": vector, "payload": json.dumps(chunk, ensure_ascii=False)} for chunk, vector in zip(chunks, vectors)]
        for method_name in ("upsert", "insert", "add"):
            method = getattr(collection, method_name, None)
            if callable(method):
                method(records)
                return
        raise RuntimeError("Unsupported Zvec collection: no upsert/insert/add method found")

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search an existing collection; exact method names vary by Zvec release."""
        collection = self._load()
        vector = self.embed([query])[0]
        for method_name in ("search", "query", "knn_search"):
            method = getattr(collection, method_name, None)
            if not callable(method):
                continue
            try:
                raw = method(vector, top_k=limit)
            except TypeError:
                raw = method(vector, limit)
            return [self._normalize_hit(item) for item in raw]
        raise RuntimeError("Unsupported Zvec collection: no search/query/knn_search method found")

    @staticmethod
    def _normalize_hit(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            payload = item.get("payload", item)
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"content": payload}
            return dict(payload, semantic_score=item.get("score", item.get("distance")))
        payload = getattr(item, "payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {"content": payload}
        return dict(payload, semantic_score=getattr(item, "score", getattr(item, "distance", None)))
