from datetime import datetime, timezone

import httpx
import pytest

from dreamcycle.sdk import DreamCycleClient, DreamCycleSDKError


def memory_value(memory_id="memory-1", role="event"):
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "id": memory_id,
        "namespace": "vendor",
        "user_id": "user",
        "content": "content",
        "role": role,
        "source": "test",
        "conversation_id": "conversation",
        "trace_id": "trace",
        "importance": 0.5,
        "success": True,
        "reviewed": False,
        "approved_for_training": False,
        "data_classification": "public",
        "metadata": {},
        "created_at": timestamp,
        "updated_at": timestamp,
        "distance": None,
        "similarity": None,
    }


def test_sdk_exposes_the_complete_vendor_contract():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "version": "0.2.2", "api": "v1"})
        if path == "/v1/memory/records":
            return httpx.Response(200, json=memory_value())
        if path == "/v1/memory/turns":
            return httpx.Response(
                200,
                json={
                    "user": memory_value("user-memory", "user"),
                    "assistant": memory_value("assistant-memory", "assistant"),
                },
            )
        if path == "/v1/memory/search":
            return httpx.Response(200, json={"memories": [memory_value()]})
        if path.endswith("/review") or request.method == "DELETE":
            return httpx.Response(200, json={"success": True})
        if path == "/v1/cycles":
            return httpx.Response(202, json=_job("job-1", "queued"))
        if path == "/v1/cycles/job-1":
            return httpx.Response(200, json=_job("job-1", "completed"))
        if path == "/v1/adapters/active":
            return httpx.Response(200, json={"available": True, "active_path": "/adapter"})
        if path == "/v1/adapters/rollback":
            return httpx.Response(
                200,
                json={
                    "available": True,
                    "active_path": "/previous",
                    "accepted": True,
                    "reason": "restored",
                    "previous_path": "/adapter",
                },
            )
        raise AssertionError(path)

    with DreamCycleClient(
        "http://dreamcycle.local",
        "vendor-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.health()["status"] == "ok"
        assert client.record("event").id == "memory-1"
        user, assistant = client.record_turn("question", "answer")
        assert (user.role, assistant.role) == ("user", "assistant")
        assert len(client.recall("content")) == 1
        assert client.review("memory-1", approved_for_training=True)
        assert client.delete("memory-1")
        assert client.start_cycle().status == "queued"
        assert client.cycle_status("job-1").status == "completed"
        assert client.active_adapter().active_path == "/adapter"
        assert client.rollback_adapter().accepted is True

    assert seen
    assert {authorization for _, _, authorization in seen} == {"Bearer vendor-secret"}


def test_sdk_raises_typed_error_without_exposing_api_key():
    def handler(request):
        return httpx.Response(401, json={"detail": "invalid key"})

    with (
        DreamCycleClient(
            "http://dreamcycle.local",
            "do-not-leak",
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(DreamCycleSDKError) as captured,
    ):
        client.recall("query")

    assert captured.value.status_code == 401
    assert "do-not-leak" not in str(captured.value)


def _job(job_id, status):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": job_id,
        "status": status,
        "created_at": now,
        "started_at": now if status != "queued" else None,
        "completed_at": now if status == "completed" else None,
        "report": {} if status == "completed" else None,
        "error": None,
    }
