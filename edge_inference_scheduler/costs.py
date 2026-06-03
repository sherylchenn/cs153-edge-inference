from __future__ import annotations

from edge_inference_scheduler.models import BackendConfig, InferenceRequest, OpenRouterResult


def estimate_tokens_from_request(request: InferenceRequest) -> int:
    text = request.input or " ".join(message.content for message in (request.messages or []))
    # Rough approximation: one token per four characters.
    return max(1, len(text) // 4) + request.max_tokens


def estimate_cost_usd(
    backend: BackendConfig,
    request: InferenceRequest,
    result: OpenRouterResult | None = None,
) -> float:
    total_tokens: int | None = None
    if result is not None:
        usage_total = result.usage.get("total_tokens")
        if isinstance(usage_total, int | float):
            total_tokens = int(usage_total)

    if total_tokens is None:
        total_tokens = estimate_tokens_from_request(request)

    return round((total_tokens / 1000) * backend.estimated_cost_per_1k_tokens_usd, 8)
