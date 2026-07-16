import asyncio

import pytest

from dreamcycle.server.auth import ClientIdentity
from dreamcycle.server.jobs import (
    CycleConflictError,
    CycleJobManager,
    CycleJobNotFoundError,
    CycleJobStatus,
    CycleUnavailableError,
)
from dreamcycle.types import CycleStatus, DreamCycleReport, utc_now


class WaitingCycle:
    def __init__(self, report):
        self.gate = asyncio.Event()
        self.report = report

    async def run(self):
        await self.gate.wait()
        return self.report


class Resolver:
    def __init__(self, cycle):
        self.cycle = cycle

    def resolve_cycle(self, identity):
        return self.cycle


def report(status=CycleStatus.SUCCESS, reason=""):
    now = utc_now()
    return DreamCycleReport(
        session_id="cycle-1",
        status=status,
        started_at=now,
        completed_at=now,
        phases=(),
        reason=reason,
    )


@pytest.mark.asyncio
async def test_cycle_jobs_reject_concurrency_and_scope_job_reads():
    cycle = WaitingCycle(report())
    manager = CycleJobManager(Resolver(cycle))
    owner = ClientIdentity("vendor", "owner")
    other = ClientIdentity("vendor", "other")

    job = await manager.start(owner)
    assert job.status is CycleJobStatus.QUEUED
    with pytest.raises(CycleConflictError):
        await manager.start(owner)
    with pytest.raises(CycleJobNotFoundError):
        await manager.get(other, job.id)

    cycle.gate.set()
    for _ in range(100):
        current = await manager.get(owner, job.id)
        if current.status is CycleJobStatus.COMPLETED:
            break
        await asyncio.sleep(0.001)
    assert current.status is CycleJobStatus.COMPLETED
    assert current.report["status"] == "success"


@pytest.mark.asyncio
async def test_cycle_error_report_sets_failed_job_state():
    cycle = WaitingCycle(report(CycleStatus.ERROR, "training failed"))
    manager = CycleJobManager(Resolver(cycle))
    identity = ClientIdentity("vendor", "owner")
    job = await manager.start(identity)
    cycle.gate.set()

    for _ in range(100):
        current = await manager.get(identity, job.id)
        if current.status is CycleJobStatus.FAILED:
            break
        await asyncio.sleep(0.001)
    assert current.status is CycleJobStatus.FAILED
    assert current.error == "training failed"


@pytest.mark.asyncio
async def test_cycle_start_is_unavailable_without_training_configuration():
    with pytest.raises(CycleUnavailableError):
        await CycleJobManager(None).start(ClientIdentity("vendor", "user"))
