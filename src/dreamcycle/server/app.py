"""FastAPI application exposing the standalone vendor contract."""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from dreamcycle import __version__
from dreamcycle.errors import ConfigurationError, DreamCycleError
from dreamcycle.memory.base import MemoryFilters
from dreamcycle.server.auth import (
    APIKeyAuthenticator,
    AuthenticationError,
    ClientIdentity,
)
from dreamcycle.server.jobs import (
    AdapterResolver,
    CycleConflictError,
    CycleJobManager,
    CycleJobNotFoundError,
    CycleUnavailableError,
)
from dreamcycle.server.models import (
    AdapterStateResponse,
    CycleJobResponse,
    MemoryItem,
    MemoryRecordRequest,
    MemoryReviewRequest,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryTurnRequest,
    MemoryTurnResponse,
    MutationResponse,
)
from dreamcycle.server.proxy import (
    ChatCompletionsProxy,
    ProxyResponse,
    StreamingProxyResponse,
    UpstreamProxyError,
)
from dreamcycle.server.service import DreamCycleService


def create_app(
    *,
    authenticator: APIKeyAuthenticator,
    service: DreamCycleService,
    jobs: CycleJobManager | None = None,
    adapters: AdapterResolver | None = None,
    proxy: ChatCompletionsProxy | None = None,
) -> FastAPI:
    job_manager = jobs or CycleJobManager(None)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if proxy is not None:
            await proxy.close()

    app = FastAPI(
        title="DreamCycle Vendor API",
        version=__version__,
        description="Scoped L2/L3 memory and local dream-cycle add-on API.",
        lifespan=lifespan,
    )

    def require_identity(request: Request) -> ClientIdentity:
        try:
            return authenticator.authenticate(request.headers.get("authorization"))
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    Identity = Annotated[ClientIdentity, Depends(require_identity)]

    @app.exception_handler(ConfigurationError)
    async def configuration_error(_: Request, exc: ConfigurationError):
        return _error_response(status.HTTP_400_BAD_REQUEST, str(exc))

    @app.exception_handler(DreamCycleError)
    async def dreamcycle_error(_: Request, exc: DreamCycleError):
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    @app.exception_handler(UpstreamProxyError)
    async def upstream_proxy_error(_: Request, exc: UpstreamProxyError):
        return _error_response(status.HTTP_502_BAD_GATEWAY, str(exc))

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "api": "v1"}

    @app.post("/v1/memory/records", response_model=MemoryItem)
    async def record(body: MemoryRecordRequest, identity: Identity) -> MemoryItem:
        memory = await asyncio.to_thread(
            service.record,
            identity,
            body.content,
            role=body.role,
            source=body.source,
            conversation_id=body.conversation_id,
            trace_id=body.trace_id,
            importance=body.importance,
            success=body.success,
            data_classification=body.data_classification,
            metadata=body.metadata,
        )
        return MemoryItem.from_record(memory)

    @app.post("/v1/memory/turns", response_model=MemoryTurnResponse)
    async def record_turn(body: MemoryTurnRequest, identity: Identity) -> MemoryTurnResponse:
        user, assistant = await asyncio.to_thread(
            service.record_turn,
            identity,
            body.user_content,
            body.assistant_content,
            source=body.source,
            conversation_id=body.conversation_id,
            trace_id=body.trace_id,
            importance=body.importance,
            success=body.success,
            data_classification=body.data_classification,
            metadata=body.metadata,
        )
        return MemoryTurnResponse(
            user=MemoryItem.from_record(user),
            assistant=MemoryItem.from_record(assistant),
        )

    @app.post("/v1/memory/search", response_model=MemorySearchResponse)
    async def search(body: MemorySearchRequest, identity: Identity) -> MemorySearchResponse:
        memories = await asyncio.to_thread(
            service.search,
            identity,
            body.query,
            limit=body.limit,
            filters=MemoryFilters(
                role=body.role,
                source=body.source,
                successful_only=body.successful_only,
                reviewed_only=body.reviewed_only,
                minimum_importance=body.minimum_importance,
                classifications=body.classifications,
            ),
            metric=body.metric,
        )
        return MemorySearchResponse(memories=[MemoryItem.from_record(item) for item in memories])

    @app.post("/v1/memory/{memory_id}/review", response_model=MutationResponse)
    async def review(
        memory_id: str, body: MemoryReviewRequest, identity: Identity
    ) -> MutationResponse:
        updated = await asyncio.to_thread(
            service.review,
            identity,
            memory_id,
            approved_for_training=body.approved_for_training,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="memory was not found")
        return MutationResponse(success=True)

    @app.delete("/v1/memory/{memory_id}", response_model=MutationResponse)
    async def delete(memory_id: str, identity: Identity) -> MutationResponse:
        deleted = await asyncio.to_thread(service.delete, identity, memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="memory was not found")
        return MutationResponse(success=True)

    @app.post(
        "/v1/cycles",
        response_model=CycleJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_cycle(identity: Identity) -> CycleJobResponse:
        try:
            return CycleJobResponse.from_state(await job_manager.start(identity))
        except CycleUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except CycleConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/cycles/{job_id}", response_model=CycleJobResponse)
    async def cycle_status(job_id: str, identity: Identity) -> CycleJobResponse:
        try:
            return CycleJobResponse.from_state(await job_manager.get(identity, job_id))
        except CycleJobNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/adapters/active", response_model=AdapterStateResponse)
    async def active_adapter(identity: Identity) -> AdapterStateResponse:
        manager = adapters.resolve_adapter(identity) if adapters is not None else None
        if manager is None:
            return AdapterStateResponse(available=False)
        active = await asyncio.to_thread(manager.active_adapter)
        return AdapterStateResponse(
            available=True,
            active_path=str(active) if active is not None else None,
        )

    @app.post("/v1/adapters/rollback", response_model=AdapterStateResponse)
    async def rollback_adapter(identity: Identity) -> AdapterStateResponse:
        manager = adapters.resolve_adapter(identity) if adapters is not None else None
        if manager is None:
            raise HTTPException(
                status_code=503,
                detail="local adapter management is not configured",
            )
        result = await asyncio.to_thread(manager.rollback)
        return AdapterStateResponse(
            available=True,
            active_path=str(result.promoted_path) if result.promoted_path else None,
            accepted=result.accepted,
            reason=result.reason,
            previous_path=str(result.previous_path) if result.previous_path else None,
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        identity: Identity,
        x_dreamcycle_conversation_id: Annotated[str | None, Header()] = None,
    ) -> Response:
        if proxy is None:
            raise HTTPException(status_code=503, detail="model proxy is not configured")
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="request body must be JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        result = await proxy.forward(
            identity,
            payload,
            conversation_id_header=x_dreamcycle_conversation_id or "",
        )
        if isinstance(result, StreamingProxyResponse):
            return StreamingResponse(
                result.body,
                status_code=result.status_code,
                headers=dict(result.headers),
            )
        if isinstance(result, ProxyResponse):
            return Response(
                content=result.body,
                status_code=result.status_code,
                headers=dict(result.headers),
            )
        raise HTTPException(status_code=502, detail="proxy returned an invalid response")

    return app


def _error_response(status_code: int, detail: str) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": detail})
