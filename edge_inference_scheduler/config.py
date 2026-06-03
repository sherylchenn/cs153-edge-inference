from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_timeout_seconds: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000")
    openrouter_app_name: str = os.getenv("OPENROUTER_APP_NAME", "Adaptive Inference Scheduler")
    use_mock_inference: bool = _bool_env("USE_MOCK_INFERENCE", True)
    request_log_path: Path = Path(os.getenv("REQUEST_LOG_PATH", "data/request_logs.jsonl"))
    backends_config_path: Path = Path(os.getenv("BACKENDS_CONFIG_PATH", "config/backends.json"))

    @property
    def should_use_real_openrouter(self) -> bool:
        return bool(self.openrouter_api_key.strip()) and not self.use_mock_inference


def get_settings() -> Settings:
    return Settings()
