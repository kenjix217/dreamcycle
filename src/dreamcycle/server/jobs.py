"""Truthful in-process job state for long-running dream cycles."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

from dreamcycle.adapters import AdapterManager
from dreamcycle.cycle import DreamCycle
from dreamcycle.server.auth import ClientIdentity
from dreamcycle.types import CycleStatus, utc_now


class CycleJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CycleJobState:
    id: str
    identity: ClientIdentity
    status: CycleJobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report: Mapping[str, Any] | None = None
    error: str | None = None


class CycleResolver(Protocol):
    def resolve_cycle(self, identity: ClientIdentity) -> DreamCycle | None: ...


class AdapterResolver(Protocol):
    def resolve_adapter(self, identity: ClientIdentity) -> AdapterManager | None: ...


class CycleUnavailableError(Exception):
    """Raised when no local cycle can run for the authenticated identity."""


class CycleConflictError(Exception):
    """Raised when an identity already has a queued or running cycle."""


class CycleJobNotFoundError(Exception):
    """Raised when a job is absent from the authenticated identity scope."""


class CycleJobManager:
    def __init__(self, cycles: CycleResolver | None) -> None:
        self._cycles = cycles
        self._jobs: dict[str, CycleJobState] = {}
        self._active: dict[ClientIdentity, str] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def start(self, identity: ClientIdentity) -> CycleJobState:
        if self._cycles is None:
            raise CycleUnavailableError("local training is not configured")
        cycle = self._cycles.resolve_cycle(identity)
        if cycle is None:
            raise CycleUnavailableError("local training is not configured for this identity")
        async with self._lock:
            active_id = self._active.get(identity)
            if active_id is not None:
                active = self._jobs[active_id]
                if active.status in {CycleJobStatus.QUEUED, CycleJobStatus.RUNNING}:
                    raise CycleConflictError("a dream cycle is already active for this identity")
            job = CycleJobState(
                id=f"job-{uuid4().hex}",
                identity=identity,
                status=CycleJobStatus.QUEUED,
                created_at=utc_now(),
            )
            self._jobs[job.id] = job
            self._active[identity] = job.id
            task = asyncio.create_task(self._run(job.id, cycle))
            self._tasks[job.id] = task
            return replace(job)

    async def get(self, identity: ClientIdentity, job_id: str) -> CycleJobState:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.identity != identity:
                raise CycleJobNotFoundError("cycle job was not found")
            return replace(job)

    async def _run(self, job_id: str, cycle: DreamCycle) -> None:
        try:
            async with self._lock:
                job = self._jobs[job_id]
                job.status = CycleJobStatus.RUNNING
                job.started_at = utc_now()
            report = await cycle.run()
            async with self._lock:
                job = self._jobs[job_id]
                job.report = report.to_dict()
                job.completed_at = utc_now()
                if report.status is CycleStatus.ERROR:
                    job.status = CycleJobStatus.FAILED
                    job.error = report.reason or "dream cycle failed"
                else:
                    job.status = CycleJobStatus.COMPLETED
        except asyncio.CancelledError:
            async with self._lock:
                job = self._jobs[job_id]
                job.status = CycleJobStatus.FAILED
                job.completed_at = utc_now()
                job.error = "dream cycle was cancelled"
            raise
        except Exception as exc:
            async with self._lock:
                job = self._jobs[job_id]
                job.status = CycleJobStatus.FAILED
                job.completed_at = utc_now()
                job.error = f"{type(exc).__name__}: {exc}"
        finally:
            async with self._lock:
                job = self._jobs[job_id]
                if self._active.get(job.identity) == job_id:
                    self._active.pop(job.identity, None)
                self._tasks.pop(job_id, None)
