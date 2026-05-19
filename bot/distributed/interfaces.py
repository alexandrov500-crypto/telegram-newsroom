"""Future-ready extension points (vector DB, GPU workers, analytics stores)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorIndex(ABC):
    @abstractmethod
    async def upsert(self, key: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def search(self, embedding: list[float], *, limit: int = 10) -> list[dict[str, Any]]:
        ...


class InferenceWorker(ABC):
    @abstractmethod
    async def infer(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class AnalyticsStore(ABC):
    """ClickHouse / TimescaleDB style time-series sink."""

    @abstractmethod
    async def write_events(self, table: str, rows: list[dict[str, Any]]) -> None:
        ...
