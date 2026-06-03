import pytest

from edge_inference_scheduler.config import Settings
from edge_inference_scheduler.models import BackendConfig, InferenceRequest
from edge_inference_scheduler.openrouter_client import BackendCallError, OpenRouterClient


@pytest.mark.asyncio
async def test_mock_client_returns_output_without_api_key(tmp_path) -> None:
    settings = Settings(openrouter_api_key="", use_mock_inference=True, request_log_path=tmp_path / "logs.jsonl")
    client = OpenRouterClient(settings)
    backend = BackendConfig(name="cheap", model="mock/cheap", baseline_latency_ms=1)
    request = InferenceRequest(input="hello", max_tokens=12)

    result = await client.generate(backend, request)
    await client.close()

    assert "mock:cheap" in result.output
    assert result.usage["total_tokens"] > 0


@pytest.mark.asyncio
async def test_mock_client_respects_artificial_failure(tmp_path) -> None:
    settings = Settings(openrouter_api_key="", use_mock_inference=True, request_log_path=tmp_path / "logs.jsonl")
    client = OpenRouterClient(settings)
    backend = BackendConfig(name="bad", model="mock/bad", artificial_failure_rate=1.0)
    request = InferenceRequest(input="hello")

    with pytest.raises(BackendCallError):
        await client.generate(backend, request)
    await client.close()
