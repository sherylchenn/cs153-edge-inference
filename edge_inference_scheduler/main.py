from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from edge_inference_scheduler.backend_config import load_backend_configs
from edge_inference_scheduler.config import get_settings
from edge_inference_scheduler.costs import estimate_cost_usd
from edge_inference_scheduler.logging_store import JSONLRequestLogger
from edge_inference_scheduler.models import (
    BackendAttempt,
    BackendState,
    BackendUpdateRequest,
    InferenceRequest,
    InferenceResponse,
    RequestLogRecord,
)
from edge_inference_scheduler.observability import (
    SCHEDULER_BACKEND_ERRORS,
    SCHEDULER_ESTIMATED_COST_USD,
    SCHEDULER_FALLBACKS,
    SCHEDULER_REQUEST_LATENCY,
    SCHEDULER_REQUESTS,
    SCHEDULER_SELECTED_BACKEND,
    instrument_app,
)
from edge_inference_scheduler.openrouter_client import BackendCallError, OpenRouterClient
from edge_inference_scheduler.registry import BackendRegistry
from edge_inference_scheduler.scheduler import InferenceScheduler

settings = get_settings()
backend_configs = load_backend_configs(settings.backends_config_path)
registry = BackendRegistry(backend_configs)
scheduler = InferenceScheduler(default_backend_name=backend_configs[0].name)
client = OpenRouterClient(settings)
request_logger = JSONLRequestLogger(settings.request_log_path)

app = FastAPI(title="Adaptive Inference Scheduler", version="1.0.0")
instrument_app(app)


@dataclass
class AttemptResult:
    attempt: BackendAttempt
    output: str | None = None


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await client.close()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mock_mode": not settings.should_use_real_openrouter,
        "backend_count": len(registry.list_backends()),
    }


@app.get("/backends", response_model=list[BackendState])
def list_backends(include_disabled: bool = True) -> list[BackendState]:
    return registry.list_backends(include_disabled=include_disabled)


@app.patch("/backends/{backend_name}", response_model=BackendState)
def update_backend(backend_name: str, update: BackendUpdateRequest) -> BackendState:
    try:
        return registry.update_backend(backend_name, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/backends/{backend_name}/reset", response_model=BackendState)
def reset_backend_stats(backend_name: str) -> BackendState:
    try:
        return registry.reset_backend_stats(backend_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/reset-stats")
def reset_stats() -> dict[str, str]:
    registry.reset_stats()
    return {"status": "reset"}


@app.get("/logs")
def tail_logs(limit: int = Query(default=25, ge=1, le=500)) -> list[dict]:
    return request_logger.tail(limit=limit)


@app.post("/infer", response_model=InferenceResponse)
async def infer(request: InferenceRequest) -> InferenceResponse:
    try:
        request.to_messages()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start_time = time.perf_counter()
    candidates = registry.enabled_backends()
    decision = scheduler.select_backend(request, candidates)
    if decision is None:
        raise HTTPException(status_code=503, detail="No enabled inference backends are available")

    selected_backend_name = decision.backend.name
    fallback_order = _build_fallback_order(request, candidates, first_backend_name=selected_backend_name)

    attempts: list[BackendAttempt] = []
    fallback_used = False
    final_output: str | None = None
    final_model: str | None = None
    final_backend_name: str | None = None
    total_estimated_cost = 0.0

    for index, backend_state in enumerate(fallback_order):
        if index > 0:
            fallback_used = True

        result = await _attempt_backend(request, backend_state)
        attempts.append(result.attempt)
        total_estimated_cost += result.attempt.estimated_cost_usd

        if result.attempt.success:
            final_output = result.output
            final_model = result.attempt.model
            final_backend_name = result.attempt.backend
            break

    latency_ms = (time.perf_counter() - start_time) * 1000

    if final_backend_name is None:
        SCHEDULER_REQUESTS.labels(request.policy.value, request.mode.value, "failure").inc()
        request_logger.write(
            RequestLogRecord(
                request_id=request.request_id,
                policy=request.policy,
                mode=request.mode,
                selected_backend=None,
                model=None,
                success=False,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                estimated_cost_usd=total_estimated_cost,
                routing_reason="all attempted backends failed",
                candidate_scores=decision.candidate_scores,
                attempts=attempts,
                input_preview=_input_preview(request),
            )
        )
        raise HTTPException(
            status_code=502,
            detail={"message": "All backends failed", "attempts": [attempt.model_dump() for attempt in attempts]},
        )

    if fallback_used:
        SCHEDULER_FALLBACKS.labels(selected_backend_name, final_backend_name).inc()

    SCHEDULER_REQUESTS.labels(request.policy.value, request.mode.value, "success").inc()
    SCHEDULER_REQUEST_LATENCY.labels(request.policy.value, request.mode.value, final_backend_name).observe(latency_ms / 1000)
    SCHEDULER_ESTIMATED_COST_USD.labels(final_backend_name, request.policy.value, request.mode.value).inc(total_estimated_cost)

    response = InferenceResponse(
        request_id=request.request_id,
        policy=request.policy,
        mode=request.mode,
        selected_backend=final_backend_name,
        model=final_model,
        fallback_used=fallback_used,
        output=final_output,
        latency_ms=latency_ms,
        estimated_cost_usd=round(total_estimated_cost, 8),
        routing_reason=decision.reason if not fallback_used else f"{decision.reason}; fallback used after failed attempt",
        candidate_scores=decision.candidate_scores,
        attempts=attempts,
    )

    request_logger.write(
        RequestLogRecord(
            request_id=request.request_id,
            policy=request.policy,
            mode=request.mode,
            selected_backend=response.selected_backend,
            model=response.model,
            success=True,
            fallback_used=response.fallback_used,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            routing_reason=response.routing_reason,
            candidate_scores=response.candidate_scores,
            attempts=response.attempts,
            input_preview=_input_preview(request),
        )
    )
    return response


async def _attempt_backend(request: InferenceRequest, backend_state: BackendState) -> AttemptResult:
    backend_name = backend_state.name
    registry.set_in_flight(backend_name, +1)
    start_time = time.perf_counter()
    try:
        result = await client.generate(backend_state.config, request)
        latency_ms = (time.perf_counter() - start_time) * 1000
        cost = estimate_cost_usd(backend_state.config, request, result)
        registry.record_success(backend_name, latency_ms)
        SCHEDULER_SELECTED_BACKEND.labels(backend_name, request.policy.value, request.mode.value).inc()
        return AttemptResult(
            attempt=BackendAttempt(
                backend=backend_name,
                model=result.model,
                success=True,
                latency_ms=latency_ms,
                estimated_cost_usd=cost,
            ),
            output=result.output,
        )
    except BackendCallError as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        registry.record_failure(backend_name, latency_ms, str(exc))
        SCHEDULER_BACKEND_ERRORS.labels(backend_name, type(exc).__name__).inc()
        return AttemptResult(
            attempt=BackendAttempt(
                backend=backend_name,
                model=backend_state.model,
                success=False,
                latency_ms=latency_ms,
                estimated_cost_usd=0.0,
                error=str(exc),
            )
        )
    finally:
        registry.set_in_flight(backend_name, -1)


def _build_fallback_order(
    request: InferenceRequest,
    candidates: list[BackendState],
    first_backend_name: str,
) -> list[BackendState]:
    first = [candidate for candidate in candidates if candidate.name == first_backend_name]
    rest = [candidate for candidate in candidates if candidate.name != first_backend_name]
    scores = scheduler.score_candidates(request, rest)
    rest_sorted = sorted(rest, key=lambda candidate: scores.get(candidate.name, 0))
    return first + rest_sorted


def _input_preview(request: InferenceRequest) -> str | None:
    if request.input:
        return request.input[:160]
    if request.messages:
        return request.messages[-1].content[:160]
    return None
