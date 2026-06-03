from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

DEFAULT_PROMPTS = [
    "Explain inference routing in one sentence.",
    "Summarize why latency matters for AI applications.",
    "Give two reasons a model API might fail.",
    "Write a short description of a fallback system.",
    "What is a routing policy in distributed systems?",
    "Explain the tradeoff between cost and quality in model selection.",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((pct / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]


async def send_request(
    client: httpx.AsyncClient,
    prompt: str,
    policy: str,
    mode: str,
    preferred_backend: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": prompt,
        "policy": policy,
        "mode": mode,
        "max_tokens": 96,
        "temperature": 0.2,
    }
    if preferred_backend:
        payload["preferred_backend"] = preferred_backend

    try:
        response = await client.post("/infer", json=payload)
        if response.status_code >= 400:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text,
                "policy": policy,
                "mode": mode,
            }
        data = response.json()
        data["ok"] = True
        return data
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc), "policy": policy, "mode": mode}


async def run_policy(
    base_url: str,
    policy: str,
    mode: str,
    request_count: int,
    concurrency: int,
    preferred_backend: str | None,
    reset_stats: bool,
) -> dict[str, Any]:
    limits = httpx.Limits(max_connections=max(concurrency, 1) * 2)
    async with httpx.AsyncClient(base_url=base_url, timeout=90, limits=limits) as client:
        if reset_stats:
            await client.post("/reset-stats")

        sem = asyncio.Semaphore(concurrency)

        async def bounded_call(index: int) -> dict[str, Any]:
            prompt = DEFAULT_PROMPTS[index % len(DEFAULT_PROMPTS)]
            async with sem:
                return await send_request(client, prompt, policy, mode, preferred_backend)

        results = await asyncio.gather(*(bounded_call(i) for i in range(request_count)))

    successes = [result for result in results if result.get("ok")]
    failures = [result for result in results if not result.get("ok")]
    latencies = [float(result["latency_ms"]) for result in successes]
    costs = [float(result.get("estimated_cost_usd", 0)) for result in successes]
    fallback_count = sum(1 for result in successes if result.get("fallback_used"))
    backend_counts: dict[str, int] = {}
    for result in successes:
        backend = result.get("selected_backend") or "none"
        backend_counts[backend] = backend_counts.get(backend, 0) + 1

    return {
        "policy": policy,
        "mode": mode,
        "request_count": request_count,
        "success_count": len(successes),
        "failure_count": len(failures),
        "error_rate": round(len(failures) / max(1, request_count), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 95), 2) if latencies else None,
        "total_estimated_cost_usd": round(sum(costs), 8),
        "avg_estimated_cost_usd": round(statistics.mean(costs), 8) if costs else None,
        "fallback_count": fallback_count,
        "backend_counts": backend_counts,
        "raw_results": results,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark scheduler routing policies.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--mode", default="balanced", choices=["fast", "cheap", "balanced", "quality"])
    parser.add_argument("--policies", nargs="+", default=["direct", "random", "round_robin", "adaptive"])
    parser.add_argument("--preferred-backend", default=None, help="Used by direct policy.")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset backend stats between policies.")
    args = parser.parse_args()

    summary = []
    for policy in args.policies:
        result = await run_policy(
            base_url=args.base_url,
            policy=policy,
            mode=args.mode,
            request_count=args.requests,
            concurrency=args.concurrency,
            preferred_backend=args.preferred_backend,
            reset_stats=not args.no_reset,
        )
        summary.append(result)
        print(json.dumps({k: v for k, v in result.items() if k != "raw_results"}, indent=2))

    out_dir = Path("benchmark_results")
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"benchmark_{timestamp}.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote benchmark results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
