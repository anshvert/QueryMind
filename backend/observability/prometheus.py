"""
QueryMind — Prometheus Metrics Setup
"""
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
from fastapi import FastAPI

# ─── Metrics ──────────────────────────────────────────────────────────────────

query_total = Counter(
    "querymind_queries_total",
    "Total number of NL queries processed",
    ["source_type", "status"],
)

query_latency = Histogram(
    "querymind_query_latency_seconds",
    "End-to-end query latency",
    ["source_type"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

sql_accuracy = Gauge(
    "querymind_sql_accuracy_ratio",
    "Rolling SQL accuracy (successful / total)",
)

self_correction_total = Counter(
    "querymind_self_corrections_total",
    "Number of SQL self-correction retries",
    ["attempt"],
)

llm_cost_total = Counter(
    "querymind_llm_cost_usd_total",
    "Cumulative LLM API cost in USD",
    ["model"],
)

cache_hits = Counter(
    "querymind_cache_hits_total",
    "Semantic cache hits",
)

cache_misses = Counter(
    "querymind_cache_misses_total",
    "Semantic cache misses",
)

active_sessions = Gauge(
    "querymind_active_sessions",
    "Number of active chat sessions",
)


def setup_prometheus(app: FastAPI):
    """Mount Prometheus /metrics endpoint on the FastAPI app."""
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
