from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


class Scheduler:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers

    def map(self, function: Callable[[T], R], items: list[T]) -> list[R]:
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(items))) as executor:
            return list(executor.map(function, items))

