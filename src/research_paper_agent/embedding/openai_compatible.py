from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


class OpenAICompatibleEmbedding:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 60) -> None:
        self.url = base_url.rstrip("/") + "/embeddings"
        self.model = model
        self.api_key = api_key or os.getenv("RPA_EMBEDDING_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.timeout = timeout

    def __call__(self, texts: list[str]) -> list[list[float]]:
        request = Request(self.url, data=json.dumps({"model": self.model, "input": texts}).encode(), headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [item["embedding"] for item in sorted(payload["data"], key=lambda item: item.get("index", 0))]
