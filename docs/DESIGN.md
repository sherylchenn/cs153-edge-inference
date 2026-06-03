# Design Doc: Adaptive Inference Scheduler

## Project summary

This project builds an adaptive inference scheduler that routes AI requests across multiple model backends using live performance data. Instead of hard-coding one model endpoint, the scheduler chooses a backend based on recent latency, reliability, estimated cost, and request mode.

The project does not require physical edge devices or local GPUs. OpenRouter is used for real model calls when an API key is configured, and mock mode is available for reproducible local development.

## Central technical problem

How can an inference system automatically choose the best backend for each request while balancing latency, cost, and reliability?

The scheduler treats each model route as a backend with changing runtime characteristics. It observes recent behavior and uses that information to make routing decisions over time.

## Scope

The implemented system includes:

- FastAPI scheduler service
- OpenRouter-backed inference client
- Backend registry with runtime stats
- Direct, random, round-robin, and adaptive routing policies
- JSONL request logging
- Prometheus-style `/metrics` endpoint
- Benchmark scripts for policy comparison
- Failure simulation through artificial delay and failure rate controls

It does not claim to perform GPU-level or hardware-level scheduling.

## Adaptive score

The adaptive policy scores each enabled backend. Lower scores are better.

```text
score =
  latency_weight * normalized_recent_latency
+ cost_weight * normalized_estimated_cost
+ error_weight * recent_error_rate
+ quality_weight * quality_penalty
+ queue_weight * queue_pressure
```

Weights change by mode: `fast`, `cheap`, `balanced`, and `quality`.

## Evaluation plan

The benchmark sends the same workload through each policy and compares:

- average latency
- p95 latency
- error rate
- estimated cost
- fallback count
- backend selection distribution

A failure simulation endpoint can slow down or break a backend to test whether adaptive routing reacts better than simple baselines.

## Limitations

OpenRouter hides the underlying provider infrastructure, so the project observes request-level behavior rather than GPU or server internals. The project is therefore best understood as an application-level inference control plane, not a physical edge scheduler.
