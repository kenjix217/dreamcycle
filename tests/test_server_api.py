from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from dreamcycle.errors import ConfigurationError
from dreamcycle.server.app import create_app
from dreamcycle.server.auth import APIKeyAuthenticator, ClientIdentity
from dreamcycle.server.service import DreamCycleService
from dreamcycle.types import KnowledgeNode, KnowledgeStats, MemoryRecord


def memory_record(identity, content="remembered", role="event"):
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=str(uuid4()),
        namespace=identity.namespace,
        user_id=identity.user_id,
        content=content,
        role=role,
        source="test",
        conversation_id="conversation",
        trace_id="trace",
        importance=0.5,
        success=True,
        reviewed=False,
        approved_for_training=False,
        data_classification="public",
        metadata={},
        created_at=now,
        updated_at=now,
    )


class FakeMemory:
    def __init__(self, identity):
        self.identity = identity
        self.records = []
        self.reviewed = []
        self.deleted = []
        self.nodes = []

    def remember(self, content, **kwargs):
        record = memory_record(self.identity, content, kwargs.get("role", "event"))
        self.records.append(record)
        return record

    def remember_turn(self, user_content, assistant_content, **kwargs):
        user = memory_record(self.identity, user_content, "user")
        assistant = memory_record(self.identity, assistant_content, "assistant")
        self.records.extend((user, assistant))
        return user, assistant

    def recall(self, query, **kwargs):
        return list(self.records)

    def mark_reviewed(self, memory_id, *, approved_for_training=False):
        self.reviewed.append((memory_id, approved_for_training))
        self.records = [
            replace(record, reviewed=True, approved_for_training=approved_for_training)
            if record.id == memory_id
            else record
            for record in self.records
        ]
        return memory_id != "missing"

    def delete(self, memory_id):
        self.deleted.append(memory_id)
        return memory_id != "missing"

    def promote_to_l3(
        self,
        memory_ids,
        *,
        node_type,
        key,
        content,
        confidence=1.0,
        metadata=None,
    ):
        sources = [record for record in self.records if record.id in set(memory_ids)]
        if len(sources) != len(set(memory_ids)):
            raise ConfigurationError("source memories are missing from this namespace")
        low_quality = [
            record.id
            for record in sources
            if not record.success or not record.reviewed or not record.approved_for_training
        ]
        if low_quality:
            raise ConfigurationError(
                "L3 promotion requires reviewed, approved, successful L2 sources"
            )
        now = datetime.now(timezone.utc)
        node = KnowledgeNode(
            id=str(uuid4()),
            namespace=self.identity.namespace,
            user_id=self.identity.user_id,
            node_type=node_type,
            key=key,
            content=content,
            confidence=confidence,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.nodes.append(node)
        return node

    def recall_knowledge(self, query, **kwargs):
        return list(self.nodes)

    def neighbors(self, node_id, **kwargs):
        return []

    def knowledge_stats(self):
        node_types = {}
        for node in self.nodes:
            node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
        return KnowledgeStats(
            nodes=len(self.nodes),
            edges=0,
            provenance_links=len(self.nodes),
            node_types=node_types,
        )


class FakeResolver:
    def __init__(self):
        self.memories = {}

    def resolve(self, identity):
        return self.memories.setdefault(identity, FakeMemory(identity))


@pytest.mark.asyncio
async def test_api_requires_server_bound_identity_and_rejects_scope_overrides():
    resolver = FakeResolver()
    identity = ClientIdentity("vendor-a", "user-a")
    app = create_app(
        authenticator=APIKeyAuthenticator({"secret-a": identity}),
        service=DreamCycleService(resolver),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.post("/v1/memory/records", json={"content": "x"})).status_code == 401
        assert (
            await client.post(
                "/v1/memory/records",
                headers={"Authorization": "Bearer wrong"},
                json={"content": "x"},
            )
        ).status_code == 401
        override = await client.post(
            "/v1/memory/records",
            headers={"Authorization": "Bearer secret-a"},
            json={"content": "x", "namespace": "vendor-b", "user_id": "user-b"},
        )
        assert override.status_code == 422
        assert resolver.memories == {}

        recorded = await client.post(
            "/v1/memory/records",
            headers={"Authorization": "Bearer secret-a"},
            json={"content": "owned by key"},
        )
        assert recorded.status_code == 200
        assert recorded.json()["namespace"] == "vendor-a"
        assert recorded.json()["user_id"] == "user-a"


@pytest.mark.asyncio
async def test_memory_routes_are_scoped_and_mutations_are_truthful():
    resolver = FakeResolver()
    first = ClientIdentity("vendor", "first")
    second = ClientIdentity("vendor", "second")
    app = create_app(
        authenticator=APIKeyAuthenticator({"first-key": first, "second-key": second}),
        service=DreamCycleService(resolver),
    )
    first_headers = {"Authorization": "Bearer first-key"}
    second_headers = {"Authorization": "Bearer second-key"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        turn = await client.post(
            "/v1/memory/turns",
            headers=first_headers,
            json={"user_content": "question", "assistant_content": "answer"},
        )
        assert turn.status_code == 200
        assert turn.json()["assistant"]["reviewed"] is False

        first_results = await client.post(
            "/v1/memory/search", headers=first_headers, json={"query": "question"}
        )
        second_results = await client.post(
            "/v1/memory/search", headers=second_headers, json={"query": "question"}
        )
        assert len(first_results.json()["memories"]) == 2
        assert second_results.json()["memories"] == []

        memory_id = turn.json()["assistant"]["id"]
        blocked = await client.post(
            "/v1/knowledge/promotions",
            headers=first_headers,
            json={
                "memory_ids": [memory_id],
                "node_type": "validated_memory",
                "key": "raw-answer",
                "content": "answer",
                "confidence": 0.8,
            },
        )
        assert blocked.status_code == 400
        assert "reviewed, approved, successful L2" in blocked.json()["detail"]

        reviewed = await client.post(
            f"/v1/memory/{memory_id}/review",
            headers=first_headers,
            json={"approved_for_training": True},
        )
        assert reviewed.json() == {"success": True}
        assert resolver.memories[first].reviewed == [(memory_id, True)]

        promoted = await client.post(
            "/v1/knowledge/promotions",
            headers=first_headers,
            json={
                "memory_ids": [memory_id],
                "node_type": "validated_memory",
                "key": "answer-pattern",
                "content": "answer",
                "confidence": 0.8,
            },
        )
        assert promoted.status_code == 200
        assert promoted.json()["node_type"] == "validated_memory"

        stats = await client.get("/v1/knowledge/stats", headers=first_headers)
        assert stats.json()["nodes"] == 1
        assert stats.json()["node_types"] == {"validated_memory": 1}

        l3_results = await client.post(
            "/v1/knowledge/search",
            headers=first_headers,
            json={"query": "answer", "limit": 5},
        )
        assert [node["key"] for node in l3_results.json()["nodes"]] == ["answer-pattern"]

        neighbors = await client.get(
            f"/v1/knowledge/{promoted.json()['id']}/neighbors",
            headers=first_headers,
        )
        assert neighbors.json() == {"neighbors": []}

        assert (
            await client.delete(f"/v1/memory/{memory_id}", headers=first_headers)
        ).status_code == 200
        assert (await client.delete("/v1/memory/missing", headers=first_headers)).status_code == 404
        assert (
            await client.post(
                "/v1/memory/missing/review",
                headers=first_headers,
                json={"approved_for_training": False},
            )
        ).status_code == 404
