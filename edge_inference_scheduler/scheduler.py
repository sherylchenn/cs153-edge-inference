from __future__ import annotations

import random
from dataclasses import dataclass, field

from edge_inference_scheduler.models import BackendState, InferenceRequest, RoutingMode, RoutingPolicy


@dataclass
class RoutingDecision:
    backend: BackendState
    reason: str
    candidate_scores: dict[str, float] = field(default_factory=dict)


class InferenceScheduler:
    """Selects the backend for a request.

    The adaptive policy uses normalized scoring so that latency, cost,
    reliability, and quality can be combined in a single simple formula.
    """

    def __init__(self, default_backend_name: str | None = None) -> None:
        self.default_backend_name = default_backend_name
        self._round_robin_index = 0

    def select_backend(self, request: InferenceRequest, candidates: list[BackendState]) -> RoutingDecision | None:
        candidates = [candidate for candidate in candidates if candidate.config.enabled]
        if not candidates:
            return None

        if request.policy == RoutingPolicy.direct:
            return self._direct(request, candidates)
        if request.policy == RoutingPolicy.random:
            return self._random(candidates)
        if request.policy == RoutingPolicy.round_robin:
            return self._round_robin(candidates)
        return self._adaptive(request, candidates)

    def score_candidates(self, request: InferenceRequest, candidates: list[BackendState]) -> dict[str, float]:
        candidates = [candidate for candidate in candidates if candidate.config.enabled]
        if not candidates:
            return {}

        weights = self._weights_for_mode(request.mode)

        latencies = [self._effective_latency_ms(candidate) for candidate in candidates]
        costs = [candidate.config.estimated_cost_per_1k_tokens_usd for candidate in candidates]
        errors = [self._effective_error_rate(candidate) for candidate in candidates]
        quality_penalties = [1.0 - candidate.config.quality_score for candidate in candidates]
        in_flight = [candidate.stats.in_flight for candidate in candidates]

        max_latency = max(max(latencies), 1.0)
        max_cost = max(max(costs), 0.000001)
        max_in_flight = max(max(in_flight), 1)

        scores: dict[str, float] = {}
        for candidate in candidates:
            normalized_latency = self._effective_latency_ms(candidate) / max_latency
            normalized_cost = candidate.config.estimated_cost_per_1k_tokens_usd / max_cost
            error_rate = self._effective_error_rate(candidate)
            quality_penalty = 1.0 - candidate.config.quality_score
            queue_pressure = candidate.stats.in_flight / max_in_flight

            score = (
                weights["latency"] * normalized_latency
                + weights["cost"] * normalized_cost
                + weights["error"] * error_rate
                + weights["quality"] * quality_penalty
                + weights["queue"] * queue_pressure
            )
            scores[candidate.name] = round(score, 6)
        return scores

    def _direct(self, request: InferenceRequest, candidates: list[BackendState]) -> RoutingDecision:
        preferred_name = request.preferred_backend or self.default_backend_name
        if preferred_name:
            for candidate in candidates:
                if candidate.name == preferred_name:
                    return RoutingDecision(
                        backend=candidate,
                        reason=f"direct policy selected {candidate.name}",
                        candidate_scores={},
                    )
        return RoutingDecision(
            backend=candidates[0],
            reason=f"direct policy selected default backend {candidates[0].name}",
            candidate_scores={},
        )

    def _random(self, candidates: list[BackendState]) -> RoutingDecision:
        selected = random.choice(candidates)
        return RoutingDecision(backend=selected, reason="random policy selected backend", candidate_scores={})

    def _round_robin(self, candidates: list[BackendState]) -> RoutingDecision:
        selected = candidates[self._round_robin_index % len(candidates)]
        self._round_robin_index += 1
        return RoutingDecision(backend=selected, reason="round-robin policy selected next backend", candidate_scores={})

    def _adaptive(self, request: InferenceRequest, candidates: list[BackendState]) -> RoutingDecision:
        scores = self.score_candidates(request, candidates)
        selected_name = min(scores, key=scores.get)
        selected = next(candidate for candidate in candidates if candidate.name == selected_name)
        return RoutingDecision(
            backend=selected,
            reason="adaptive score selected lowest scoring backend",
            candidate_scores=scores,
        )

    def _effective_latency_ms(self, backend: BackendState) -> float:
        if backend.stats.ewma_latency_ms is not None:
            return backend.stats.ewma_latency_ms
        return backend.config.baseline_latency_ms

    def _effective_error_rate(self, backend: BackendState) -> float:
        # Blend observed EWMA with configured simulated failure rate so tests and
        # failure scenarios influence routing immediately.
        return max(backend.stats.ewma_error_rate, backend.config.artificial_failure_rate)

    def _weights_for_mode(self, mode: RoutingMode) -> dict[str, float]:
        if mode == RoutingMode.fast:
            return {"latency": 0.60, "cost": 0.10, "error": 0.20, "quality": 0.05, "queue": 0.05}
        if mode == RoutingMode.cheap:
            return {"latency": 0.20, "cost": 0.55, "error": 0.15, "quality": 0.05, "queue": 0.05}
        if mode == RoutingMode.quality:
            return {"latency": 0.20, "cost": 0.10, "error": 0.20, "quality": 0.45, "queue": 0.05}
        return {"latency": 0.38, "cost": 0.25, "error": 0.25, "quality": 0.07, "queue": 0.05}
