# Rubric Mapping

## Problem & Insight

The project addresses a real infrastructure problem: model APIs differ in latency, cost, and reliability, but many applications still route all traffic to a single fixed backend.

## Execution & Technical Work

The implementation includes a working FastAPI scheduler, OpenRouter client, backend registry, adaptive routing policy, routing baselines, logging, metrics, tests, and benchmark scripts.

## Evaluation & Evidence

The benchmark framework compares adaptive routing against direct, random, and round-robin routing. JSONL logs and Prometheus-style metrics provide evidence for latency, failure rate, fallback behavior, cost, and backend selection.

## Communication & Presentation

The README explains setup, execution, benchmark use, limitations, and project framing. The design doc summarizes the technical architecture.

## Process, Integrity & Disclosure

The README discloses that the initial scaffold was generated with AI assistance. The final implementation documents the substantive changes and states project limitations clearly.
