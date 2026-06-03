from __future__ import annotations

import json
from pathlib import Path

from edge_inference_scheduler.models import BackendConfig


DEFAULT_BACKENDS = [
    BackendConfig(
        name="cheap",
        model="openai/gpt-4o-mini",
        estimated_cost_per_1k_tokens_usd=0.0006,
        baseline_latency_ms=1200,
        quality_score=0.62,
    ),
    BackendConfig(
        name="fast",
        model="google/gemini-flash-1.5",
        estimated_cost_per_1k_tokens_usd=0.0010,
        baseline_latency_ms=850,
        quality_score=0.70,
    ),
    BackendConfig(
        name="quality",
        model="anthropic/claude-3-haiku",
        estimated_cost_per_1k_tokens_usd=0.0025,
        baseline_latency_ms=1500,
        quality_score=0.82,
    ),
]


def load_backend_configs(path: Path) -> list[BackendConfig]:
    if not path.exists():
        return list(DEFAULT_BACKENDS)

    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    if not isinstance(raw, list):
        raise ValueError(f"Backend config must be a list: {path}")

    configs = [BackendConfig.model_validate(item) for item in raw]
    if not configs:
        raise ValueError("At least one backend must be configured")

    names = [config.name for config in configs]
    if len(names) != len(set(names)):
        raise ValueError("Backend names must be unique")

    return configs
