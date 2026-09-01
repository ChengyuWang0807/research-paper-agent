from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def commit(self, task_id: str, stage_id: str, run_id: str, value: dict[str, Any]) -> dict[str, str]:
        target = self.root / "tasks" / task_id / stage_id
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{run_id}.json"
        content = json.dumps(value, ensure_ascii=False, indent=2)
        path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {"uri": path.resolve().as_uri(), "sha256": digest, "run_id": run_id}

