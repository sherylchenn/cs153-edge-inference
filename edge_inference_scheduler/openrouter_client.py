from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from edge_inference_scheduler.config import Settings
from edge_inference_scheduler.models import BackendConfig, InferenceRequest, OpenRouterResult


class BackendCallError(RuntimeError):
    pass


class OpenRouterClient:
    """OpenRouter chat-completions client with a deterministic mock fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            timeout=settings.openrouter_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def generate(self, backend: BackendConfig, request: InferenceRequest) -> OpenRouterResult:
        await self._apply_simulation(backend)

        if not self.settings.should_use_real_openrouter:
            return await self._mock_generate(backend, request)

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        payload: dict[str, Any] = {
            "model": backend.model,
            "messages": request.to_messages(),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        try:
            response = await self._client.post("/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise BackendCallError(f"OpenRouter HTTP error for {backend.name}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise BackendCallError(f"OpenRouter request failed for {backend.name}: {exc}") from exc

        data = response.json()
        try:
            output = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendCallError(f"Unexpected OpenRouter response shape for {backend.name}: {data}") from exc

        return OpenRouterResult(
            output=output,
            model=data.get("model", backend.model),
            usage=data.get("usage", {}),
            raw=data,
        )

    async def _apply_simulation(self, backend: BackendConfig) -> None:
        if backend.artificial_delay_ms:
            await asyncio.sleep(backend.artificial_delay_ms / 1000)
        if backend.artificial_failure_rate and random.random() < backend.artificial_failure_rate:
            raise BackendCallError(f"Artificial failure injected for backend {backend.name}")

    async def _mock_generate(self, backend: BackendConfig, request: InferenceRequest) -> OpenRouterResult:
        # Simulate rough backend differences without spending API credits.
        jitter_ms = random.uniform(30, 130)
        await asyncio.sleep((backend.baseline_latency_ms * 0.08 + jitter_ms) / 1000)
        prompt = request.input or request.to_messages()[-1]["content"]
        output = (
            f"[mock:{backend.name}] Routed to model {backend.model}. "
            f"Input preview: {prompt[:120]}"
        )
        approx_prompt_tokens = max(1, len(prompt) // 4)
        approx_completion_tokens = max(1, min(request.max_tokens, len(output) // 4))
        return OpenRouterResult(
            output=output,
            model=backend.model,
            usage={
                "prompt_tokens": approx_prompt_tokens,
                "completion_tokens": approx_completion_tokens,
                "total_tokens": approx_prompt_tokens + approx_completion_tokens,
                "mock": True,
            },
            raw={},
        )
