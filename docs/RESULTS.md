# Results

## Evaluation Setup

I evaluated four routing policies: direct, random, round-robin, and adaptive. Each policy sent requests through the same FastAPI scheduler and OpenRouter-backed model backends. The main metrics were average latency, p95 latency, estimated cost, fallback count, and backend selection distribution.

## Clean Concurrency Benchmark

| Policy | Avg Latency | p95 Latency | Cost | Fallbacks | Backend Usage |
|---|---:|---:|---:|---:|---|
| direct | 1516.64 ms | 1836.20 ms | $0.0004740 | 0 | cheap: 8 |
| random | 1478.52 ms | 2954.03 ms | $0.0009739 | 0 | mixed |
| round_robin | 1566.00 ms | 3125.35 ms | $0.0010219 | 0 | mixed |
| adaptive | 716.68 ms | 971.81 ms | $0.0006640 | 0 | fast: 8 |

Under clean concurrency, adaptive routing had the lowest average latency and p95 latency while keeping fallback rate at zero. It cost more than fixed direct routing but less than random and round-robin.

## Controlled Degradation Benchmark

In this experiment, I artificially degraded the `fast` backend by adding delay and a failure rate.

| Policy | Avg Latency | p95 Latency | Cost | Fallbacks | Backend Usage |
|---|---:|---:|---:|---:|---|
| direct | 1667.00 ms | 3180.33 ms | $0.0004662 | 0 | cheap: 8 |
| random | 2207.21 ms | 3982.91 ms | $0.0013647 | 1 | mixed |
| round_robin | 2443.80 ms | 4471.23 ms | $0.0009518 | 1 | mixed |
| adaptive | 1655.76 ms | 3993.46 ms | $0.0005112 | 0 | cheap: 7, fast: 1 |

Under degradation, adaptive routing mostly avoided the degraded `fast` backend and achieved the lowest average latency with zero fallbacks. This supports the main project claim: a lightweight scheduler can use runtime behavior to make better routing decisions than policies that ignore backend health.

## Lightweight Output Quality Check

I manually reviewed outputs from the cheap, fast, and quality backends on three prompts. This was not a full human evaluation, but a sanity check that the scheduler was routing to usable model outputs.

| Backend | Correctness | Completeness | Concision | Notes |
|---|---:|---:|---:|---|
| cheap | 4 | 4 | 4 | Clear and reliable across prompts; best overall balance, though one longer answer was cut off by the token limit. |
| fast | 4 | 3 | 4 | Strong concise explanation for simple prompts, but one answer over-expanded and was cut off before finishing. |
| quality | 3 | 3 | 3 | Usable responses, but not clearly better in this sample; one routing answer interpreted routing as internal model routing instead of backend/API routing. |

Takeaway: all three backends produced usable answers, but the higher-cost backend was not clearly better in this small sample. Because the quality check was small and manual, I did not use it as the main optimization target. The main evaluation focused on latency, cost, fallback behavior, and reliability.

## Limitations

These benchmarks are small because they use paid API calls. The system measures application-level latency, fallback behavior, and estimated cost, not real GPU utilization. OpenRouter also hides the underlying provider infrastructure, so this project should be understood as an application-level inference scheduler rather than a physical GPU scheduler.

## Takeaway

The adaptive policy was not always best in every clean run, but it performed especially well under concurrency and controlled degradation. The most important result is that the system is measurable: it logs each decision, tracks latency and fallback behavior, and exposes runtime metrics through `/metrics`.