"""Unit tests for ``server_app/metrics.py`` (T-014, modularised by T-020).

These tests load the module by file path with ``importlib.util`` so the
import does not depend on the package being importable (e.g. when the
test runner is invoked from a directory that does not include the repo
root in ``sys.path``). T-020 moved the metrics implementation from
``server/metrics.py`` to ``server_app/metrics.py`` — the loader below
prefers the new location and falls back to the legacy path so the
contract is forward-compatible if either file is missing during a
cherry-pick.
"""

from __future__ import annotations

import importlib.util
import threading
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
# Prefer the modularised location introduced by T-020; fall back to the
# legacy top-level ``server/metrics.py`` path for any commit that has
# not yet picked up the modularisation (e.g. cherry-picks to a hotfix
# branch that still sees the old layout).
METRICS_PATH = REPO_ROOT / "server_app" / "metrics.py"
if not METRICS_PATH.is_file():  # pragma: no cover - defensive
    METRICS_PATH = REPO_ROOT / "server" / "metrics.py"


def _load_metrics_module():
    spec = importlib.util.spec_from_file_location(
        "lvcodex_metrics_test", METRICS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metrics = _load_metrics_module()


class RequestMetricsCounterTests(unittest.TestCase):
    def test_inc_request_increments_per_route_status_pair(self) -> None:
        registry = metrics.RequestMetrics()

        registry.inc_request("/api/exams/catalog", 200, latency_ms=5)
        registry.inc_request("/api/exams/catalog", 200, latency_ms=7)
        registry.inc_request("/api/exams/catalog", 404, latency_ms=3)
        registry.inc_request("/api/dashboard", 200, latency_ms=12)

        snapshot = registry.snapshot()
        self.assertEqual(
            snapshot["requests"][("/api/exams/catalog", "200")], 2
        )
        self.assertEqual(
            snapshot["requests"][("/api/exams/catalog", "404")], 1
        )
        self.assertEqual(
            snapshot["requests"][("/api/dashboard", "200")], 1
        )

    def test_5xx_responses_increment_error_counter(self) -> None:
        registry = metrics.RequestMetrics()
        registry.inc_request("/api/score", 500, latency_ms=1200)
        registry.inc_request("/api/score", 503, latency_ms=900)
        registry.inc_request("/api/score", 200, latency_ms=50)

        snapshot = registry.snapshot()
        self.assertEqual(snapshot["errors"]["/api/score"], 2)

    def test_route_label_cardinality_is_collapsed(self) -> None:
        registry = metrics.RequestMetrics()

        registry.inc_request(
            "/api/attempts/0123456789abcdef0123/score", 200, latency_ms=10
        )
        registry.inc_request(
            "/api/attempts/9c8d1e4f-7a21-4b3e-9c10-ab12cd34ef56/score",
            200,
            latency_ms=11,
        )
        registry.inc_request("/api/attempts/42/score", 200, latency_ms=12)

        snapshot = registry.snapshot()
        keys = list(snapshot["requests"].keys())
        # All three should collapse to the same canonical route label.
        self.assertEqual(len(keys), 1)
        route, status = keys[0]
        self.assertEqual(status, "200")
        self.assertIn(":id", route)
        self.assertEqual(snapshot["requests"][(route, "200")], 3)

    def test_latency_histogram_records_observation_in_correct_bucket(self) -> None:
        registry = metrics.RequestMetrics()

        # 7ms => falls into the 0.01s bucket and every bucket above.
        registry.inc_request("/api/healthz", 200, latency_ms=7)

        snapshot = registry.snapshot()
        latency = snapshot["latency"]["/api/healthz"]
        buckets = latency["buckets"]
        bucket_bounds = snapshot["buckets_seconds"]

        for upper, count in zip(bucket_bounds, buckets):
            if upper < 0.007:
                self.assertEqual(count, 0, msg=f"bucket {upper} should be 0")
            else:
                self.assertEqual(count, 1, msg=f"bucket {upper} should be 1")
        self.assertEqual(latency["count"], 1)
        self.assertAlmostEqual(latency["sum"], 0.007, places=6)


class RenderTextTests(unittest.TestCase):
    def test_render_text_emits_help_and_type_lines_for_each_family(self) -> None:
        registry = metrics.RequestMetrics()
        registry.inc_request("/api/session", 200, latency_ms=15)
        registry.inc_request("/api/session", 401, latency_ms=4)

        rendered = registry.render_text()

        self.assertIn("# HELP http_requests_total", rendered)
        self.assertIn("# TYPE http_requests_total counter", rendered)
        self.assertIn("# HELP http_request_errors_total", rendered)
        self.assertIn("# TYPE http_request_errors_total counter", rendered)
        self.assertIn("# HELP http_request_duration_seconds", rendered)
        self.assertIn("# TYPE http_request_duration_seconds histogram", rendered)

    def test_render_text_includes_observed_series(self) -> None:
        registry = metrics.RequestMetrics()
        registry.inc_request("/api/session", 200, latency_ms=15)
        registry.inc_request("/api/session", 200, latency_ms=20)

        rendered = registry.render_text()

        self.assertIn(
            'http_requests_total{route="/api/session",status="200"} 2',
            rendered,
        )
        self.assertIn(
            'http_request_duration_seconds_count{route="/api/session"} 2',
            rendered,
        )
        # Histogram always emits the +Inf bucket.
        self.assertIn(
            'http_request_duration_seconds_bucket{route="/api/session",le="+Inf"} 2',
            rendered,
        )
        # Output must end with a newline per the exposition format.
        self.assertTrue(rendered.endswith("\n"))

    def test_render_text_is_stable_when_registry_empty(self) -> None:
        registry = metrics.RequestMetrics()

        rendered = registry.render_text()

        # Help/Type lines must still be present for an empty registry so
        # Grafana panels render gracefully on cold start.
        self.assertIn("# TYPE http_requests_total counter", rendered)
        self.assertIn(
            "# TYPE http_request_duration_seconds histogram", rendered
        )
        self.assertNotIn("http_requests_total{", rendered)

    def test_render_text_escapes_label_values(self) -> None:
        registry = metrics.RequestMetrics()
        # Route with a backslash and quote should be escaped.
        registry.inc_request('/api/odd"path\\segment', 200, latency_ms=2)

        rendered = registry.render_text()
        self.assertIn(r'route="/api/odd\"path\\segment"', rendered)


class ThreadSafetyTests(unittest.TestCase):
    def test_concurrent_inc_request_does_not_lose_counts(self) -> None:
        registry = metrics.RequestMetrics()
        thread_count = 8
        per_thread = 250
        barrier = threading.Barrier(thread_count)

        def worker() -> None:
            barrier.wait()
            for index in range(per_thread):
                # Alternate two routes + three status codes to exercise
                # the dictionary upserts from multiple writers.
                route = "/api/a" if index % 2 == 0 else "/api/b"
                status = 200 if index % 3 else (500 if index % 5 else 404)
                registry.inc_request(route, status, latency_ms=float(index % 50))

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        snapshot = registry.snapshot()
        total_requests = sum(snapshot["requests"].values())
        self.assertEqual(total_requests, thread_count * per_thread)

        total_observations = sum(
            int(slot["count"]) for slot in snapshot["latency"].values()
        )
        self.assertEqual(total_observations, thread_count * per_thread)


if __name__ == "__main__":
    unittest.main()
