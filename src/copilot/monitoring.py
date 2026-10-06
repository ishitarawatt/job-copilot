"""Lightweight tracing: one JSON line per agent call, plus an aggregate summary.

Swap `Tracer._emit` for OpenTelemetry / Langfuse / Datadog in production; the
span fields are chosen to map directly onto those systems.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

# Illustrative $ per 1M tokens (input, output). Update to your model's real pricing.
PRICE_PER_MTOK = (3.0, 15.0)


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class Tracer:
    def __init__(self, path: str | Path | None = "logs/traces.jsonl"):
        self.path = Path(path) if path else None
        self.spans: list[dict] = []
        self._lock = Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex[:12]

    @contextmanager
    def span(self, trace_id: str, agent: str, input_text: str = ""):
        rec = {"trace_id": trace_id, "agent": agent, "status": "ok",
               "in_tokens": approx_tokens(input_text), "out_tokens": 0, "retries": 0}
        start = time.perf_counter()
        try:
            yield rec
        except Exception as e:  # record, then re-raise so the orchestrator decides
            rec["status"] = "error"
            rec["error"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            rec["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            rec["cost_usd"] = round(
                (rec["in_tokens"] * PRICE_PER_MTOK[0] + rec["out_tokens"] * PRICE_PER_MTOK[1]) / 1e6, 6)
            self._emit(rec)

    def _emit(self, rec: dict) -> None:
        with self._lock:
            self.spans.append(rec)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(rec) + "\n")

    def summary(self) -> dict:
        n = len(self.spans)
        if not n:
            return {"spans": 0}
        errors = sum(1 for s in self.spans if s["status"] == "error")
        lat = sorted(s["latency_ms"] for s in self.spans)
        return {
            "spans": n,
            "error_rate": round(errors / n, 4),
            "p50_ms": lat[n // 2],
            "p95_ms": lat[min(n - 1, int(n * 0.95))],
            "total_cost_usd": round(sum(s["cost_usd"] for s in self.spans), 6),
            "retries": sum(s["retries"] for s in self.spans),
        }
