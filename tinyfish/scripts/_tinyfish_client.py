from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator

import requests
from dotenv import load_dotenv

BASE_URL = "https://agent.tinyfish.ai/v1/automation"
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"


def load_api_key() -> str:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("TINYFISH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            f"TINYFISH_API_KEY is missing. Please set it in {ENV_PATH.as_posix()}."
        )
    return api_key


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }


def run_sync(url: str, goal: str, timeout: int = 180, **extra_payload: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"url": url, "goal": goal}
    payload.update(extra_payload)

    api_key = load_api_key()
    response = requests.post(
        f"{BASE_URL}/run",
        headers=_headers(api_key),
        json=payload,
        timeout=timeout,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = response.text[:800]
        raise requests.HTTPError(f"{exc}. Response body: {body}") from exc

    return response.json()


def run_sse_events(
    url: str, goal: str, timeout: int = 300, **extra_payload: Any
) -> Iterator[Dict[str, Any]]:
    payload: Dict[str, Any] = {"url": url, "goal": goal}
    payload.update(extra_payload)

    api_key = load_api_key()
    with requests.post(
        f"{BASE_URL}/run-sse",
        headers=_headers(api_key),
        json=payload,
        stream=True,
        timeout=timeout,
    ) as response:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text[:800]
            raise requests.HTTPError(f"{exc}. Response body: {body}") from exc

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            raw_json = line[6:].strip()
            if not raw_json:
                continue
            try:
                yield json.loads(raw_json)
            except json.JSONDecodeError:
                yield {"type": "RAW", "message": raw_json}
