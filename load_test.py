#!/usr/bin/env python3
"""
load_test.py  -  Continuous load generator for the monitoring demo API.

What it does
------------
* Sends an endless stream of requests across every route.
* Deliberately mixes success responses (2xx), client errors (4xx),
  auth errors (401/403), server errors (5xx), and intentional timeouts.
* Prints a live summary line after each batch so you can watch the
  metrics appear in Grafana in real time.
* Detects when the API is down and keeps retrying.

Usage
-----
    # Against a local server started with `uvicorn api.main:app --port 8123`
    python load_test.py

    # Against a different host/port
    python load_test.py --base-url http://localhost:8123

    # Control request rate
    python load_test.py --delay 0.1   # ~10 req/s
    python load_test.py --delay 0     # as fast as possible

Dependencies: only the standard library + `requests`
    pip install requests
"""

import argparse
import random
import time
from collections import Counter
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Scenario definitions  (each is a callable → (method, path, kwargs))
# ---------------------------------------------------------------------------

VALID_TOKENS = ["secret-token-admin", "secret-token-user"]
BAD_TOKENS = ["wrong-token", "expired-token-123", ""]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _build_scenarios(base: str):
    """Return a weighted list of (label, callable) pairs."""

    scenarios = []

    # ------------------------------------------------------------------ health
    scenarios += [("GET /health  → 200", lambda: requests.get(f"{base}/health"))] * 5

    # ------------------------------------------------------------------ hello
    scenarios += [
        ("GET /hello  → 200", lambda: requests.get(f"{base}/hello", params={"name": random.choice(["Alice", "Bob", "World"])}))
    ] * 3

    # ------------------------------------------------------------------ items list
    scenarios += [("GET /items  → 200", lambda: requests.get(f"{base}/items"))] * 4

    # ------------------------------------------------------------------ create item (valid)
    def create_item_valid():
        payload = {
            "name": f"Item-{random.randint(1, 9999)}",
            "price": round(random.uniform(0.5, 500), 2),
            "in_stock": random.choice([True, False]),
        }
        return requests.post(f"{base}/items", json=payload)

    scenarios += [("POST /items  → 201", create_item_valid)] * 3

    # ------------------------------------------------------------------ create item (invalid – missing price)
    def create_item_invalid():
        return requests.post(f"{base}/items", json={"name": "Bad Item"})  # missing `price`

    scenarios += [("POST /items  → 422", create_item_invalid)] * 2

    # ------------------------------------------------------------------ get existing item
    def get_item_found():
        item_id = random.randint(1, 5)  # mostly valid
        return requests.get(f"{base}/items/{item_id}")

    scenarios += [("GET /items/{id} → 200", get_item_found)] * 4

    # ------------------------------------------------------------------ get missing item
    def get_item_missing():
        item_id = random.randint(9000, 9999)
        return requests.get(f"{base}/items/{item_id}")

    scenarios += [("GET /items/{id} → 404", get_item_missing)] * 3

    # ------------------------------------------------------------------ delete item (may 404)
    def delete_item():
        item_id = random.randint(1, 10)
        return requests.delete(f"{base}/items/{item_id}")

    scenarios += [("DELETE /items/{id}", delete_item)] * 2

    # ------------------------------------------------------------------ users/me valid token
    def users_me_valid():
        token = random.choice(VALID_TOKENS)
        return requests.get(f"{base}/users/me", headers=_auth(token))

    scenarios += [("GET /users/me → 200/403", users_me_valid)] * 3

    # ------------------------------------------------------------------ users/me no token → 401
    scenarios += [
        ("GET /users/me → 401", lambda: requests.get(f"{base}/users/me"))
    ] * 2

    # ------------------------------------------------------------------ users/me bad token → 403
    def users_me_bad_token():
        token = random.choice(BAD_TOKENS)
        return requests.get(f"{base}/users/me", headers=_auth(token))

    scenarios += [("GET /users/me → 403", users_me_bad_token)] * 2

    # ------------------------------------------------------------------ compute valid
    def compute_valid():
        ops = ["add", "subtract", "multiply", "divide"]
        op = random.choice(ops)
        a = round(random.uniform(-100, 100), 2)
        b = round(random.uniform(1, 100), 2)  # avoid 0 for divide
        return requests.post(f"{base}/compute", json={"a": a, "b": b, "operation": op})

    scenarios += [("POST /compute → 200", compute_valid)] * 3

    # ------------------------------------------------------------------ compute divide by zero → 400
    scenarios += [
        ("POST /compute → 400 (div/0)", lambda: requests.post(f"{base}/compute", json={"a": 5, "b": 0, "operation": "divide"}))
    ] * 1

    # ------------------------------------------------------------------ compute invalid operation → 422
    scenarios += [
        ("POST /compute → 422", lambda: requests.post(f"{base}/compute", json={"a": 1, "b": 2, "operation": "power"}))
    ] * 1

    # ------------------------------------------------------------------ simulate-error various codes
    for code in [400, 401, 403, 404, 422, 500, 503]:
        c = code  # capture loop variable

        def make_err(code=c):
            return requests.get(f"{base}/simulate-error", params={"code": code})

        scenarios += [(f"GET /simulate-error?code={code}", make_err)] * 1

    return scenarios


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(base_url: str, delay: float, batch_size: int) -> None:
    scenarios = _build_scenarios(base_url)
    total_requests = 0
    status_counter: Counter = Counter()
    down_streak = 0

    print(f"🚀  Starting load test against {base_url}")
    print(f"    Scenarios: {len(scenarios)}  |  delay: {delay}s  |  batch: {batch_size}\n")

    while True:
        # Shuffle to get random order each batch
        batch = random.choices(scenarios, k=batch_size)

        for label, fn in batch:
            try:
                resp = fn()
                status = resp.status_code
                down_streak = 0
            except requests.exceptions.ConnectionError:
                status = "DOWN"
                down_streak += 1
            except requests.exceptions.Timeout:
                status = "TIMEOUT"
                down_streak += 1
            except Exception as exc:
                status = f"ERR({type(exc).__name__})"
                down_streak += 1

            status_counter[status] += 1
            total_requests += 1

            if down_streak >= 3:
                print(f"⚠️  API appears to be DOWN – retrying in 5 s …")
                time.sleep(5)
                down_streak = 0

            if delay:
                time.sleep(delay)

        # Print summary after each batch
        top = sorted(status_counter.items(), key=lambda x: -x[1])[:8]
        summary = "  ".join(f"{k}:{v}" for k, v in top)
        print(f"[total={total_requests:>6}]  {summary}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Continuous load tester for the monitoring demo API")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8123",
        help="Base URL of the API (default: http://localhost:8123)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Seconds to wait between individual requests (default: 0.05)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of requests per display batch (default: 20)",
    )
    args = parser.parse_args()
    run(args.base_url, args.delay, args.batch_size)


if __name__ == "__main__":
    main()
