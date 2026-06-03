from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RoutingPolicy(str, Enum):
    direct = "direct"
    random = "random"
    round_robin = "round_robin"
    adaptive = "adaptive"


class RoutingMode(str, Enum):
    fast = "fast"
    cheap = "cheap"
    balanced = "balanced"
    quality = "quality"


class ChatMessage(BaseModel):
    role: str = Field(default="user")
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        valid_roles = {"system", "user", "assistant"}
        if value not in valid_roles:
            raise ValueError(f"role must be one of {sorted(valid_roles)}")
        return value


class InferenceRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    input: str | None = Field(default=None, description="Simple user input. Converted to a chat message.")
    messages: list[ChatMessage] | None = Field(default=None, description="Optional OpenAI-style chat messages.")
    policy: RoutingPolicy = RoutingPolicy.adaptive
    mode: RoutingMode = RoutingMode.balanced
    preferred_backend: str | None = Field(default=None, description="Used by direct routing or as a preference hint.")
    max_tokens: int = Field(default=160, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[ChatMessage] | None) -> list[ChatMessage] | None:
        if value is not None and len(value) == 0:
            raise ValueError("messages cannot be empty")
        return value

    def to_messages(self) -> list[dict[str, str]]:
        if self.messages:
            return [message.model_dump() for message in self.messages]
        if self.input:
            return [{"role": "user", "content": self.input}]
        raise ValueError("Either input or messages must be provided")


class BackendConfig(BaseModel):
    name: str = Field(min_length=1)
    model: str = Field(min_length=1)
    estimated_cost_per_1k_tokens_usd: float = Field(default=0.001, ge=0.0)
    baseline_latency_ms: float = Field(default=1000.0, ge=0.0)
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    enabled: bool = True
    artificial_delay_ms: float = Field(default=0.0, ge=0.0)
    artificial_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class BackendStats(BaseModel):
    requests: int = 0
    successes: int = 0
    failures: int = 0
    in_flight: int = 0
    ewma_latency_ms: float | None = None
    ewma_error_rate: float = 0.0
    last_error: str | None = None
    last_updated: datetime | None = None

    @property
    def observed_error_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.failures / self.requests


class BackendState(BaseModel):
    config: BackendConfig
    stats: BackendStats = Field(default_factory=BackendStats)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def healthy(self) -> bool:
        return self.config.enabled and self.stats.ewma_error_rate < 0.8


class BackendUpdateRequest(BaseModel):
    enabled: bool | None = None
    artificial_delay_ms: float | None = Field(default=None, ge=0.0)
    artificial_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_cost_per_1k_tokens_usd: float | None = Field(default=None, ge=0.0)
    baseline_latency_ms: float | None = Field(default=None, ge=0.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)


class BackendAttempt(BaseModel):
    backend: str
    model: str
    success: bool
    latency_ms: float
    estimated_cost_usd: float = 0.0
    error: str | None = None


class InferenceResponse(BaseModel):
    request_id: str
    policy: RoutingPolicy
    mode: RoutingMode
    selected_backend: str | None
    model: str | None
    fallback_used: bool
    output: str | None
    latency_ms: float
    estimated_cost_usd: float
    routing_reason: str
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    attempts: list[BackendAttempt] = Field(default_factory=list)


class OpenRouterResult(BaseModel):
    output: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class RequestLogRecord(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str
    policy: RoutingPolicy
    mode: RoutingMode
    selected_backend: str | None
    model: str | None
    success: bool
    fallback_used: bool
    latency_ms: float
    estimated_cost_usd: float
    routing_reason: str
    candidate_scores: dict[str, float]
    attempts: list[BackendAttempt]
    input_preview: str | None = None
