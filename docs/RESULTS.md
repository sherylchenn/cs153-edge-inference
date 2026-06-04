# Results

## Evaluation Setup

I evaluated four routing policies: `direct`, `random`, `round_robin`, and `adaptive`. Each policy sent requests through the same FastAPI scheduler and OpenRouter-backed model backends. The three available backends were:

* `cheap`: `openai/gpt-4o-mini`
* `fast`: `google/gemini-2.5-flash-lite`
* `quality`: `anthropic/claude-3-haiku`

The main metrics were average latency, p95 latency, estimated cost, fallback count, and backend selection distribution. I also checked that all three backends could successfully return real model responses before running the final benchmarks.

## Clean Concurrency Benchmark

This benchmark tested the scheduler under mild concurrent load without intentionally degrading any backend.

| Policy        | Avg Latency | p95 Latency |       Cost | Fallbacks | Backend Usage |
| ------------- | ----------: | ----------: | ---------: | --------: | ------------- |
| `direct`      |  1516.64 ms |  1836.20 ms | $0.0004740 |         0 | cheap: 8      |
| `random`      |  1478.52 ms |  2954.03 ms | $0.0009739 |         0 | mixed         |
| `round_robin` |  1566.00 ms |  3125.35 ms | $0.0010219 |         0 | mixed         |
| `adaptive`    |   716.68 ms |   971.81 ms | $0.0006640 |         0 | fast: 8       |

Under clean concurrency, adaptive routing had the lowest average latency and lowest p95 latency while keeping the fallback rate at zero. It cost more than fixed direct routing, but less than random and round-robin. This suggests that the adaptive policy found a better latency-cost balance than the simpler baselines in this run.

## Controlled Degradation Benchmark

In this experiment, I artificially degraded the `fast` backend by adding delay and a failure rate. This tested whether the scheduler could respond when a previously useful backend became worse.

| Policy        | Avg Latency | p95 Latency |       Cost | Fallbacks | Backend Usage     |
| ------------- | ----------: | ----------: | ---------: | --------: | ----------------- |
| `direct`      |  1667.00 ms |  3180.33 ms | $0.0004662 |         0 | cheap: 8          |
| `random`      |  2207.21 ms |  3982.91 ms | $0.0013647 |         1 | mixed             |
| `round_robin` |  2443.80 ms |  4471.23 ms | $0.0009518 |         1 | mixed             |
| `adaptive`    |  1655.76 ms |  3993.46 ms | $0.0005112 |         0 | cheap: 7, fast: 1 |

Under degradation, random and round-robin both routed traffic into the degraded `fast` backend and triggered fallback behavior. Adaptive routing mostly avoided the degraded backend and completed the run with zero fallbacks. Its p95 latency was still high because it made limited contact with the degraded backend, but it achieved the lowest average latency and avoided failed final requests.

This supports the main project claim: a lightweight scheduler can use runtime behavior to make better routing decisions than policies that ignore backend health.

## Lightweight Output Quality Check

I manually reviewed outputs from the cheap, fast, and quality backends on three prompts. This was not a full human evaluation, but a sanity check that the scheduler was routing to usable model outputs.

| Backend   | Correctness | Completeness | Concision | Notes                                                                                                                                                     |
| --------- | ----------: | -----------: | --------: | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cheap`   |           4 |            4 |         4 | Clear and reliable across prompts; best overall balance, though one longer answer was cut off by the token limit.                                         |
| `fast`    |           4 |            3 |         4 | Strong concise explanation for simple prompts, but one answer over-expanded and was cut off before finishing.                                             |
| `quality` |           3 |            3 |         3 | Usable responses, but not clearly better in this sample; one routing answer interpreted routing as internal model routing instead of backend/API routing. |

All three backends produced usable answers. However, the higher-cost backend was not clearly better in this small sample. Because this quality check was small and manual, I did not use it as the main optimization target. The main evaluation focused on latency, estimated cost, fallback behavior, and reliability.

## Tests and Observability

The project also includes automated tests and runtime observability.

The unit test suite passed:

```text
10 passed
```

The FastAPI service exposes Prometheus-style metrics at:

```text
/metrics
```

This makes the scheduler behavior inspectable while it runs. The system records routing decisions, selected backends, latency, fallback behavior, and estimated cost, so the project is not just a black-box API wrapper.

## DigitalOcean Deployment Check

I deployed the FastAPI scheduler to a DigitalOcean Droplet to confirm that the project can run outside my local machine.

Deployment environment:

* Provider: DigitalOcean
* Region: SFO2
* Operating system: Ubuntu 24.04 LTS x64
* Droplet type: Basic shared CPU
* Size: 1 vCPU / 1 GB RAM
* Estimated cost: $6/month
* Runtime: FastAPI + Uvicorn
* External inference provider: OpenRouter
* Server port: 8000
* DigitalOcean insights/metrics: enabled for basic CPU visibility

After deployment, I verified that the cloud-hosted service returned the expected root response and exposed the main project endpoints:

```text
/
/docs
/health
/backends
/infer
/metrics
```

This deployment was used as a reproducibility and cloud smoke test, not as the main benchmark environment. The benchmark results in `docs/RESULTS.md` were collected locally so that the policy comparisons stayed consistent. The DigitalOcean deployment shows that the scheduler can be run on a real cloud VM with minimal resources.


## Limitations

These benchmarks are small because they use paid API calls. The results should be interpreted as evidence from a controlled prototype, not as a large-scale performance study.

The system measures application-level latency, fallback behavior, and estimated cost. It does not measure real GPU utilization or physical edge-device performance. OpenRouter also hides the underlying provider infrastructure, so this project should be understood as an application-level inference scheduler rather than a physical GPU scheduler.

The quality check was also limited. I manually reviewed a small number of outputs, but I did not build a full evaluator or train a learned quality-aware router.

## Takeaway

The adaptive policy was not always best in every clean run, but it performed especially well under concurrency and controlled backend degradation. The strongest result was the degradation test: when the `fast` backend became slower and less reliable, adaptive routing mostly shifted away from it, while random and round-robin still routed into it and triggered fallbacks.

Overall, the project demonstrates a small but functional inference control plane. It routes real model requests, tracks runtime behavior, exposes metrics, and compares adaptive routing against simpler baselines.
