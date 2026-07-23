"""Synchronous HTTP client for adding DreamCycle to an existing platform."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover - exercised by clean core-only install
    from dreamcycle.errors import OptionalDependencyError

    raise OptionalDependencyError(
        "DreamCycleClient requires 'pip install dreamcycle[sdk]'"
    ) from exc

from dreamcycle.errors import ConfigurationError
from dreamcycle.sdk.models import (
    AdapterState,
    CycleJob,
    KnowledgeItem,
    KnowledgeNeighbor,
    KnowledgeStats,
    MemoryItem,
)


class DreamCycleSDKError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DreamCycleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise ConfigurationError("DreamCycle base_url is required")
        if not api_key:
            raise ConfigurationError("DreamCycle api_key is required")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DreamCycleClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def health(self) -> Mapping[str, Any]:
        return self._request("GET", "/healthz")

    def record(
        self,
        content: str,
        *,
        role: str = "event",
        source: str = "vendor-sdk",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        data_classification: str = "public",
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryItem:
        value = self._request(
            "POST",
            "/v1/memory/records",
            json={
                "content": content,
                "role": role,
                "source": source,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
                "importance": importance,
                "success": success,
                "data_classification": data_classification,
                "metadata": dict(metadata or {}),
            },
        )
        return MemoryItem.from_dict(value)

    def record_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        source: str = "vendor-sdk",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        data_classification: str = "public",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[MemoryItem, MemoryItem]:
        value = self._request(
            "POST",
            "/v1/memory/turns",
            json={
                "user_content": user_content,
                "assistant_content": assistant_content,
                "source": source,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
                "importance": importance,
                "success": success,
                "data_classification": data_classification,
                "metadata": dict(metadata or {}),
            },
        )
        return MemoryItem.from_dict(value["user"]), MemoryItem.from_dict(value["assistant"])

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        role: str | None = None,
        source: str | None = None,
        successful_only: bool = False,
        reviewed_only: bool = False,
        minimum_importance: float = 0,
        classifications: tuple[str, ...] = (),
        metric: str | None = None,
    ) -> list[MemoryItem]:
        value = self._request(
            "POST",
            "/v1/memory/search",
            json={
                "query": query,
                "limit": limit,
                "role": role,
                "source": source,
                "successful_only": successful_only,
                "reviewed_only": reviewed_only,
                "minimum_importance": minimum_importance,
                "classifications": list(classifications),
                "metric": metric,
            },
        )
        return [MemoryItem.from_dict(item) for item in value["memories"]]

    def review(self, memory_id: str, *, approved_for_training: bool = False) -> bool:
        value = self._request(
            "POST",
            f"/v1/memory/{memory_id}/review",
            json={"approved_for_training": approved_for_training},
        )
        return bool(value["success"])

    def delete(self, memory_id: str) -> bool:
        value = self._request("DELETE", f"/v1/memory/{memory_id}")
        return bool(value["success"])

    def promote_knowledge(
        self,
        memory_ids: tuple[str, ...] | list[str],
        *,
        key: str,
        content: str,
        node_type: str = "validated_memory",
        confidence: float = 0.8,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeItem:
        value = self._request(
            "POST",
            "/v1/knowledge/promotions",
            json={
                "memory_ids": list(memory_ids),
                "node_type": node_type,
                "key": key,
                "content": content,
                "confidence": confidence,
                "metadata": dict(metadata or {}),
            },
        )
        return KnowledgeItem.from_dict(value)

    def recall_knowledge(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
        metric: str | None = None,
    ) -> list[KnowledgeItem]:
        value = self._request(
            "POST",
            "/v1/knowledge/search",
            json={
                "query": query,
                "limit": limit,
                "node_type": node_type,
                "metric": metric,
            },
        )
        return [KnowledgeItem.from_dict(item) for item in value["nodes"]]

    def knowledge_neighbors(
        self,
        node_id: str,
        *,
        relation: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeNeighbor]:
        params: dict[str, Any] = {"limit": limit}
        if relation:
            params["relation"] = relation
        value = self._request(
            "GET",
            f"/v1/knowledge/{node_id}/neighbors",
            params=params,
        )
        return [KnowledgeNeighbor.from_dict(item) for item in value["neighbors"]]

    def knowledge_stats(self) -> KnowledgeStats:
        return KnowledgeStats(**self._request("GET", "/v1/knowledge/stats"))

    def start_cycle(self) -> CycleJob:
        return CycleJob.from_dict(self._request("POST", "/v1/cycles"))

    def cycle_status(self, job_id: str) -> CycleJob:
        return CycleJob.from_dict(self._request("GET", f"/v1/cycles/{job_id}"))

    def active_adapter(self) -> AdapterState:
        return AdapterState(**self._request("GET", "/v1/adapters/active"))

    def rollback_adapter(self) -> AdapterState:
        return AdapterState(**self._request("POST", "/v1/adapters/rollback"))

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DreamCycleSDKError(f"DreamCycle request failed: {exc}") from exc
        if response.is_error:
            try:
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else None
            except ValueError:
                detail = None
            message = str(detail or f"DreamCycle returned HTTP {response.status_code}")
            raise DreamCycleSDKError(message, status_code=response.status_code)
        try:
            value = response.json()
        except ValueError as exc:
            raise DreamCycleSDKError("DreamCycle returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise DreamCycleSDKError("DreamCycle returned an invalid response object")
        return value
