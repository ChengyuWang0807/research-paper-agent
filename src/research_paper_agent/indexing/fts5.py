from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class FTS5Index:
    """SQLite metadata tables plus an FTS5 virtual table for exact/keyword retrieval."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY, title TEXT NOT NULL, source_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, content_type TEXT NOT NULL,
                    page INTEGER, section TEXT, content TEXT NOT NULL, metadata_json TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED, paper_id UNINDEXED, content, content_type UNINDEXED,
                    section UNINDEXED, page UNINDEXED
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def upsert_paper(self, paper_id: str, title: str, source_path: str, metadata: dict[str, Any], content_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO papers VALUES (?, ?, ?, ?, ?)", (paper_id, title, source_path, json.dumps(metadata, ensure_ascii=False), content_hash))

    def add_chunks(self, paper_id: str, chunks: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            for chunk in chunks:
                connection.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)", (chunk["chunk_id"], paper_id, chunk["content_type"], chunk.get("page"), chunk.get("section", ""), chunk["content"], json.dumps(chunk, ensure_ascii=False)))
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk["chunk_id"],))
                connection.execute("INSERT INTO chunks_fts(chunk_id, paper_id, content, content_type, section, page) VALUES (?, ?, ?, ?, ?, ?)", (chunk["chunk_id"], paper_id, chunk["content"], chunk["content_type"], chunk.get("section", ""), str(chunk.get("page", ""))))

    def search(
        self,
        query: str,
        limit: int = 10,
        content_type: str | None = None,
        paper_ids: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT c.*, p.metadata_json AS paper_metadata_json, bm25(chunks_fts) AS score FROM chunks_fts JOIN chunks c USING(chunk_id) JOIN papers p USING(paper_id) WHERE chunks_fts MATCH ?"
        params: list[Any] = [query]
        if content_type:
            sql += " AND c.content_type = ?"
            params.append(content_type)
        if paper_ids:
            placeholders = ", ".join("?" for _ in paper_ids)
            sql += f" AND c.paper_id IN ({placeholders})"
            params.extend(paper_ids)
        for key, value in (metadata_filter or {}).items():
            if key not in {"publication_year", "venue", "country", "parser", "processing_status"}:
                raise ValueError(f"unsupported metadata filter: {key}")
            sql += " AND json_extract(p.metadata_json, ?) = ?"
            params.extend([f"$.{key}", value])
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item.pop("metadata_json", None)
            item.pop("paper_metadata_json", None)
            chunk_metadata = json.loads(row["metadata_json"])
            item["source_text"] = chunk_metadata.get("source_text", item.get("content", ""))
            item["asset_ref"] = chunk_metadata.get("asset_ref")
            item["element_id"] = chunk_metadata.get("element_id")
            for key in ("chunk_id", "paper_id", "content", "source_text"):
                chunk_metadata.pop(key, None)
            item["metadata"] = chunk_metadata
            item["paper_metadata"] = json.loads(row["paper_metadata_json"])
            item["lexical_score"] = item.pop("score", None)
            results.append(item)
        return results
