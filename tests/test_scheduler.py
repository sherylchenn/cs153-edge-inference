from edge_inference_scheduler.models import BackendConfig, BackendState, InferenceRequest, RoutingMode, RoutingPolicy
from edge_inference_scheduler.registry import BackendRegistry
from edge_inference_scheduler.scheduler import InferenceScheduler


def make_backend(name: str, latency: float, cost: float, quality: float = 0.5, failures: float = 0.0) -> BackendState:
    return BackendState(
        config=BackendConfig(
            name=name,
            model=f"mock/{name}",
            baseline_latency_ms=latency,
            estimated_cost_per_1k_tokens_usd=cost,
            quality_score=quality,
            artificial_failure_rate=failures,
        )
    )


def test_direct_policy_uses_preferred_backend() -> None:
    scheduler = InferenceScheduler(default_backend_name="cheap")
    request = InferenceRequest(input="hello", policy=RoutingPolicy.direct, preferred_backend="quality")
    backends = [make_backend("cheap", 100, 0.001), make_backend("quality", 200, 0.005)]

    decision = scheduler.select_backend(request, backends)

    assert decision is not None
    assert decision.backend.name == "quality"


def test_round_robin_cycles() -> None:
    scheduler = InferenceScheduler()
    request = InferenceRequest(input="hello", policy=RoutingPolicy.round_robin)
    backends = [make_backend("a", 100, 0.001), make_backend("b", 200, 0.001)]

    assert scheduler.select_backend(request, backends).backend.name == "a"
    assert scheduler.select_backend(request, backends).backend.name == "b"
    assert scheduler.select_backend(request, backends).backend.name == "a"


def test_adaptive_fast_mode_prefers_low_latency() -> None:
    scheduler = InferenceScheduler()
    request = InferenceRequest(input="hello", policy=RoutingPolicy.adaptive, mode=RoutingMode.fast)
    backends = [
        make_backend("slow_cheap", latency=2000, cost=0.0001),
        make_backend("fast_expensive", latency=400, cost=0.004),
    ]

    decision = scheduler.select_backend(request, backends)

    assert decision is not None
    assert decision.backend.name == "fast_expensive"


def test_adaptive_cheap_mode_prefers_low_cost() -> None:
    scheduler = InferenceScheduler()
    request = InferenceRequest(input="hello", policy=RoutingPolicy.adaptive, mode=RoutingMode.cheap)
    backends = [
        make_backend("cheap", latency=900, cost=0.0001),
        make_backend("expensive", latency=700, cost=0.01),
    ]

    decision = scheduler.select_backend(request, backends)

    assert decision is not None
    assert decision.backend.name == "cheap"


def test_adaptive_avoids_high_failure_rate() -> None:
    scheduler = InferenceScheduler()
    request = InferenceRequest(input="hello", policy=RoutingPolicy.adaptive, mode=RoutingMode.balanced)
    backends = [
        make_backend("fast_broken", latency=300, cost=0.001, failures=0.9),
        make_backend("stable", latency=700, cost=0.001, failures=0.0),
    ]

    decision = scheduler.select_backend(request, backends)

    assert decision is not None
    assert decision.backend.name == "stable"


def test_registry_updates_runtime_stats() -> None:
    registry = BackendRegistry([make_backend("a", 100, 0.001).config])
    registry.record_success("a", latency_ms=500)
    registry.record_failure("a", latency_ms=1000, error="timeout")

    backend = registry.get("a")

    assert backend is not None
    assert backend.stats.requests == 2
    assert backend.stats.successes == 1
    assert backend.stats.failures == 1
    assert backend.stats.ewma_latency_ms is not None
    assert backend.stats.last_error == "timeout"
