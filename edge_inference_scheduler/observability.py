from __future__ import annotations

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


SCHEDULER_REQUESTS = Counter(
    "scheduler_requests",
    "Number of scheduler requests processed.",
    ["policy", "mode", "status"],
)

SCHEDULER_REQUEST_LATENCY = Histogram(
    "scheduler_request_latency_seconds",
    "End-to-end scheduler request latency in seconds.",
    ["policy", "mode", "backend"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

SCHEDULER_BACKEND_ERRORS = Counter(
    "scheduler_backend_errors",
    "Backend call errors by backend and error type.",
    ["backend", "error_type"],
)

SCHEDULER_FALLBACKS = Counter(
    "scheduler_fallbacks",
    "Number of times the scheduler had to use a fallback backend.",
    ["from_backend", "to_backend"],
)

SCHEDULER_SELECTED_BACKEND = Counter(
    "scheduler_selected_backend",
    "Number of times each backend was selected by policy and mode.",
    ["backend", "policy", "mode"],
)

SCHEDULER_ESTIMATED_COST_USD = Counter(
    "scheduler_estimated_cost_usd",
    "Estimated cost accumulated by backend, policy, and mode.",
    ["backend", "policy", "mode"],
)


def instrument_app(app: FastAPI) -> None:
    """Expose Prometheus-style metrics.

    If prometheus-fastapi-instrumentator is installed, it also instruments
    generic HTTP metrics. The manual fallback keeps the project runnable even
    in minimal environments.
    """

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, include_in_schema=False)
    except Exception:
        @app.get("/metrics", include_in_schema=False)
        def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
