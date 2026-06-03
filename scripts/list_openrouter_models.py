from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set OPENROUTER_API_KEY in .env before listing models.")

    response = httpx.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    for model in data.get("data", [])[:100]:
        print(model.get("id"))


if __name__ == "__main__":
    main()
