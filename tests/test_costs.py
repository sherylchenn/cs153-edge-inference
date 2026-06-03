from edge_inference_scheduler.costs import estimate_cost_usd
from edge_inference_scheduler.models import BackendConfig, InferenceRequest, OpenRouterResult


def test_estimate_cost_uses_usage_total_tokens() -> None:
    backend = BackendConfig(name="cheap", model="mock/model", estimated_cost_per_1k_tokens_usd=0.002)
    request = InferenceRequest(input="hello")
    result = OpenRouterResult(output="hi", model="mock/model", usage={"total_tokens": 500})

    assert estimate_cost_usd(backend, request, result) == 0.001


def test_estimate_cost_falls_back_to_request_estimate() -> None:
    backend = BackendConfig(name="cheap", model="mock/model", estimated_cost_per_1k_tokens_usd=0.001)
    request = InferenceRequest(input="abcd", max_tokens=10)

    assert estimate_cost_usd(backend, request) > 0
