from __future__ import annotations


def compute_backoff(base_seconds: int, consecutive_failures: int, max_seconds: int) -> int:
    attempts = max(consecutive_failures, 1)
    return min(base_seconds * (2 ** (attempts - 1)), max_seconds)
