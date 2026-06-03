# Adaptive Inference Scheduler

A FastAPI service that routes AI inference requests across multiple OpenRouter-backed model backends using latency, estimated cost, and reliability signals.

This project began as an edge inference scheduler. The final version is framed more accurately as an application-level inference scheduler: it does not require local GPUs or physical edge devices. It simulates the control-plane problem of deciding where inference should run, while using OpenRouter for real model calls when an API key is configured.

## What this project does

- Exposes a scheduler API at `/infer`
- Supports multiple model backends through OpenRouter
- Implements four routing policies: `direct`, `random`, `round_robin`, and `adaptive`
- Tracks request latency, backend failures, estimated cost, fallback use, and backend selection counts
- Exposes Prometheus-style metrics at `/metrics`
- Writes one JSONL record per request for evaluation
- Includes a benchmark script for comparing policies
- Runs in mock mode without an API key, so the project is easy to test before using credits

## Architecture

```text
Client / benchmark script
        ↓
FastAPI scheduler API
        ↓
Backend registry + live runtime stats
        ↓
Routing policy
        ↓
OpenRouter client or mock inference path
        ↓
JSONL logs + Prometheus metrics
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The project defaults to mock mode, so it will run even if `OPENROUTER_API_KEY` is blank.

To use real OpenRouter calls, edit `.env`:

```env
OPENROUTER_API_KEY=your_key_here
USE_MOCK_INFERENCE=false
```

Model IDs are configured in `config/backends.json`. If one model is unavailable or too expensive, replace it with another current OpenRouter model slug.

## Run the service

```bash
uvicorn edge_inference_scheduler.main:app --reload --port 8000
```

Open the API docs:

```text
http://localhost:8000/docs
```

Check service health:

```bash
curl http://localhost:8000/health
```

Check Prometheus-style metrics:

```bash
curl http://localhost:8000/metrics
```

## Send an inference request

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Give one sentence explaining inference routing.",
    "policy": "adaptive",
    "mode": "balanced"
  }'
```

Example response:

```json
{
  "request_id": "...",
  "policy": "adaptive",
  "mode": "balanced",
  "selected_backend": "fast",
  "model": "google/gemini-flash-1.5",
  "fallback_used": false,
  "output": "...",
  "latency_ms": 903.2,
  "estimated_cost_usd": 0.00001,
  "routing_reason": "adaptive score selected lowest scoring backend",
  "candidate_scores": {
    "cheap": 0.42,
    "fast": 0.31,
    "quality": 0.55
  }
}
```

## Routing policies

| Policy | Behavior |
|---|---|
| `direct` | Uses a specified backend or the default backend |
| `random` | Chooses a backend randomly |
| `round_robin` | Cycles evenly through enabled backends |
| `adaptive` | Scores backends using recent latency, error rate, estimated cost, and quality score |

## Routing modes

| Mode | What it prioritizes |
|---|---|
| `fast` | Lower latency |
| `cheap` | Lower estimated cost |
| `balanced` | Latency, cost, and reliability |
| `quality` | Higher configured quality score while still avoiding failures |

## Run benchmarks

Start the API first, then run:

```bash
python scripts/run_benchmark.py --requests 12 --concurrency 3 --policies direct random round_robin adaptive --mode balanced
```

Benchmark output is written to `benchmark_results/`.

To test whether the scheduler reacts to a bad backend, artificially degrade one backend:

```bash
python scripts/simulate_degradation.py --backend fast --delay-ms 1800 --failure-rate 0.25
python scripts/run_benchmark.py --requests 12 --concurrency 3 --policies round_robin adaptive --mode balanced
```

Then reset the backend:

```bash
python scripts/simulate_degradation.py --backend fast --delay-ms 0 --failure-rate 0
```

## Logs

By default, request logs are written to:

```text
data/request_logs.jsonl
```

Each line contains the selected backend, policy, mode, latency, success/failure, fallback use, estimated cost, and all attempted backends.

Summarize logs with:

```bash
python scripts/summarize_logs.py data/request_logs.jsonl
```

## Tests

```bash
pytest
```

## Project limitations

This project does not measure real GPU utilization or physical edge-device state. OpenRouter hides the underlying infrastructure, so this project observes request-level behavior rather than hardware-level behavior.

That limitation is intentional. The project focuses on the control-plane problem: using measured application-level signals to make better inference routing decisions than fixed or naive routing baselines.

## Integrity disclosure

The initial scaffold was generated with AI assistance. The substantive implementation in this version includes the backend abstraction, OpenRouter client, adaptive routing policy, routing baselines, metrics/logging layer, Prometheus-style metrics endpoint, benchmark scripts, tests, and documentation.
