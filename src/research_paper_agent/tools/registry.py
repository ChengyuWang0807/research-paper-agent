from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, tool: Callable[..., Any]) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = tool

    def resolve(self, allowed_tools: list[str]) -> dict[str, Callable[..., Any]]:
        missing = sorted(set(allowed_tools) - self._tools.keys())
        if missing:
            raise KeyError(f"unregistered tools: {', '.join(missing)}")
        return {name: self._tools[name] for name in allowed_tools}

