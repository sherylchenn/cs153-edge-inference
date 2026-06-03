from __future__ import annotations

import argparse

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply artificial delay/failure to a backend.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--failure-rate", type=float, default=0.0)
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()

    payload = {
        "artificial_delay_ms": args.delay_ms,
        "artificial_failure_rate": args.failure_rate,
        "enabled": not args.disable,
    }
    response = httpx.patch(f"{args.base_url}/backends/{args.backend}", json=payload, timeout=10)
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
