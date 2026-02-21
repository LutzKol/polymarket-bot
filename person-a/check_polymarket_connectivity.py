#!/usr/bin/env python3
"""Basic Polymarket API connectivity checks for Phase 1."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class EndpointResult:
    name: str
    url: str
    ok: bool
    status: int | None
    latency_ms: float | None
    note: str


def fetch_json(url: str, timeout: float) -> tuple[int, Any, float]:
    req = Request(url, headers={"User-Agent": "polymarketbot-phase1/1.0"})
    started = time.perf_counter()
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        latency_ms = (time.perf_counter() - started) * 1000.0
        return resp.status, json.loads(raw), latency_ms


def check_endpoint(name: str, url: str, timeout: float) -> EndpointResult:
    try:
        status, payload, latency_ms = fetch_json(url, timeout=timeout)
        if isinstance(payload, (list, dict)):
            payload_type = type(payload).__name__
            note = f"JSON {payload_type} received"
        else:
            note = "Response received (non-object JSON)"
        return EndpointResult(name, url, True, status, latency_ms, note)
    except HTTPError as e:
        return EndpointResult(name, url, False, e.code, None, f"HTTP error: {e}")
    except URLError as e:
        return EndpointResult(name, url, False, None, None, f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        return EndpointResult(name, url, False, None, None, f"Invalid JSON: {e}")
    except Exception as e:
        return EndpointResult(name, url, False, None, None, f"Unexpected error: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Polymarket API connectivity")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    endpoints = [
        (
            "Gamma API",
            "https://gamma-api.polymarket.com/events?limit=1",
        ),
        (
            "CLOB API",
            "https://clob.polymarket.com/time",
        ),
    ]

    print("Polymarket Connectivity Check")
    print(f"- Timeout: {args.timeout:.1f}s")

    results = [check_endpoint(name, url, args.timeout) for name, url in endpoints]

    for res in results:
        status = res.status if res.status is not None else "n/a"
        latency = f"{res.latency_ms:.1f}ms" if res.latency_ms is not None else "n/a"
        prefix = "PASS" if res.ok else "FAIL"
        print(f"- [{prefix}] {res.name}: status={status} latency={latency} url={res.url}")
        print(f"  note: {res.note}")

    all_ok = all(r.ok for r in results)
    print("\nPhase-1 Connectivity Criterion:")
    print(f"- Status: {'PASS' if all_ok else 'NOT YET'}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
