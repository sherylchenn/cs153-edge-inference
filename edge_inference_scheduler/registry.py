from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from edge_inference_scheduler.models import BackendConfig, BackendState, BackendStats, BackendUpdateRequest


class BackendRegistry:
    """Thread-safe in-memory backend registry and runtime stats store."""

    def __init__(self, configs: list[BackendConfig], ewma_alpha: float = 0.35) -> None:
        if not configs:
            raise ValueError("At least one backend is required")
        self._lock = RLock()
        self._backends: dict[str, BackendState] = {
            config.name: BackendState(config=config) for config in configs
        }
        self._ewma_alpha = ewma_alpha

    def list_backends(self, include_disabled: bool = True) -> list[BackendState]:
        with self._lock:
            backends = list(self._backends.values())
            if include_disabled:
                return [backend.model_copy(deep=True) for backend in backends]
            return [backend.model_copy(deep=True) for backend in backends if backend.config.enabled]

    def get(self, name: str) -> BackendState | None:
        with self._lock:
            backend = self._backends.get(name)
            return backend.model_copy(deep=True) if backend else None

    def enabled_backends(self) -> list[BackendState]:
        return [backend for backend in self.list_backends(include_disabled=False) if backend.healthy]

    def set_in_flight(self, name: str, delta: int) -> None:
        with self._lock:
            backend = self._require_backend(name)
            backend.stats.in_flight = max(0, backend.stats.in_flight + delta)
            backend.stats.last_updated = datetime.now(timezone.utc)

    def record_success(self, name: str, latency_ms: float) -> BackendState:
        with self._lock:
            backend = self._require_backend(name)
            backend.stats.requests += 1
            backend.stats.successes += 1
            backend.stats.ewma_latency_ms = self._update_ewma(backend.stats.ewma_latency_ms, latency_ms)
            backend.stats.ewma_error_rate = self._update_ewma(backend.stats.ewma_error_rate, 0.0)
            backend.stats.last_error = None
            backend.stats.last_updated = datetime.now(timezone.utc)
            return backend.model_copy(deep=True)

    def record_failure(self, name: str, latency_ms: float, error: str) -> BackendState:
        with self._lock:
            backend = self._require_backend(name)
            backend.stats.requests += 1
            backend.stats.failures += 1
            backend.stats.ewma_latency_ms = self._update_ewma(backend.stats.ewma_latency_ms, latency_ms)
            backend.stats.ewma_error_rate = self._update_ewma(backend.stats.ewma_error_rate, 1.0)
            backend.stats.last_error = error[:500]
            backend.stats.last_updated = datetime.now(timezone.utc)
            return backend.model_copy(deep=True)

    def update_backend(self, name: str, update: BackendUpdateRequest) -> BackendState:
        with self._lock:
            backend = self._require_backend(name)
            current = backend.config.model_dump()
            update_data = update.model_dump(exclude_none=True)
            current.update(update_data)
            backend.config = BackendConfig.model_validate(current)
            backend.stats.last_updated = datetime.now(timezone.utc)
            return backend.model_copy(deep=True)

    def reset_stats(self) -> None:
        with self._lock:
            for backend in self._backends.values():
                backend.stats = BackendStats()

    def reset_backend_stats(self, name: str) -> BackendState:
        with self._lock:
            backend = self._require_backend(name)
            backend.stats = BackendStats()
            return backend.model_copy(deep=True)

    def _require_backend(self, name: str) -> BackendState:
        backend = self._backends.get(name)
        if backend is None:
            raise KeyError(f"Unknown backend: {name}")
        return backend

    def _update_ewma(self, previous: float | None, value: float) -> float:
        if previous is None:
            return value
        return self._ewma_alpha * value + (1 - self._ewma_alpha) * previous
