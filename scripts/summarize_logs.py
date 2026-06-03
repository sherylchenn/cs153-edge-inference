from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = int(round((pct / 100) * (len(values) - 1)))
    return values[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize JSONL request logs.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(f"No log file found at {args.path}")

    records = [json.loads(line) for line in args.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise SystemExit("Log file is empty")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["policy"]].append(record)

    print(f"records: {len(records)}")
    print(f"backend counts: {dict(Counter(r.get('selected_backend') for r in records))}")
    print()

    for policy, items in grouped.items():
        latencies = [float(item["latency_ms"]) for item in items if item.get("success")]
        costs = [float(item.get("estimated_cost_usd", 0)) for item in items if item.get("success")]
        failures = [item for item in items if not item.get("success")]
        fallbacks = [item for item in items if item.get("fallback_used")]
        print(policy)
        print(f"  requests: {len(items)}")
        print(f"  failures: {len(failures)}")
        print(f"  fallbacks: {len(fallbacks)}")
        print(f"  avg_latency_ms: {round(statistics.mean(latencies), 2) if latencies else None}")
        print(f"  p95_latency_ms: {round(percentile(latencies, 95), 2) if latencies else None}")
        print(f"  total_estimated_cost_usd: {round(sum(costs), 8)}")
        print()


if __name__ == "__main__":
    main()
