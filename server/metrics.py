"""In-process Prometheus metrics registry for the Latvian A2 exam server.

This module is intentionally dependency-free: it implements just enough of
the Prometheus text exposition format (version 0.0.4) to publish counters
and a fixed-bucket latency histogram for HTTP requests.

The module is **not** imported via ``import server.metrics`` (the
single-file ``server.py`` module would clash with a ``server`` package).
``server.py`` loads it explicitly via ``importlib.util`` from a trailing
T-014 hook block, and the unit tests in ``tests/server/test_metrics.py``
load it the same way. This keeps ``server.py`` as the canonical module
for ``import server`` while satisfying the modular file layout required
by the delivery plan.
"""

from __future__ import annotations

import threading
from typing import Iterable


# Default histogram buckets in seconds, modelled on the Prometheus client
# defaults but with an extra coarse 10s bucket to capture long-tail latency
# from upstream LLM calls. ``+Inf`` is appended implicitly by ``render_text``.
DEFAULT_BUCKETS_SECONDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _format_float(value: float) -> str:
    """Render a float using Prometheus' canonical exposition style."""

    if value == float("inf"):
        return "+Inf"
    if value == float("-inf"):
        return "-Inf"
    if value != value:  # NaN
        return "NaN"
    # ``repr`` produces the shortest round-trippable representation. Prometheus
    # accepts integer-valued counters either as ``1`` or ``1.0``; we keep the
    # ``.0`` suffix so the output is unambiguous when scraped by older clients.
    if value.is_integer():
        return f"{int(value)}"
    return repr(value)


def _escape_label_value(value: str) -> str:
    """Escape a label value per the Prometheus text exposition spec."""

    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _sanitize_route(route: str) -> str:
    """Collapse high-cardinality path segments before they hit the registry.

    The metric ``route`` label must have bounded cardinality, otherwise the
    histogram series cardinality explodes. We replace any segment that looks
    like an opaque id (UUID, integer, long random token) with ``:id``.
    """

    if not route:
        return "/"
    if "?" in route:
        route = route.split("?", 1)[0]
    if "#" in route:
        route = route.split("#", 1)[0]
    if route != "/" and route.endswith("/"):
        route = route.rstrip("/") or "/"

    segments = route.split("/")
    sanitized: list[str] = []
    for segment in segments:
        if not segment:
            sanitized.append(segment)
            continue
        if segment.isdigit():
            sanitized.append(":id")
            continue
        if len(segment) >= 16 and any(ch.isdigit() for ch in segment) and any(
            ch.isalpha() for ch in segment
        ):
            sanitized.append(":id")
            continue
        if len(segment) == 36 and segment.count("-") == 4:
            sanitized.append(":id")
            continue
        sanitized.append(segment)
    return "/".join(sanitized) or "/"


class RequestMetrics:
    """Thread-safe in-process registry for HTTP request metrics.

    The registry exposes three Prometheus families:

    * ``http_requests_total`` — counter labelled by route + status.
    * ``http_request_duration_seconds`` — histogram of request latency,
      labelled by route, with a fixed bucket set.
    * ``http_request_errors_total`` — counter of responses with status
      ``>= 500``; useful for SLO burn-rate alerts that do not want to
      ``sum()`` across every status label.

    All mutations take ``self._lock`` so concurrent ``inc_request`` calls from
    Python's ``ThreadingHTTPServer`` worker threads never lose increments.
    """

    def __init__(
        self,
        buckets_seconds: Iterable[float] = DEFAULT_BUCKETS_SECONDS,
    ) -> None:
        cleaned = tuple(sorted({float(b) for b in buckets_seconds if b > 0}))
        if not cleaned:
            cleaned = DEFAULT_BUCKETS_SECONDS
        self._buckets: tuple[float, ...] = cleaned
        self._lock = threading.Lock()
        # counter: {(route, status): count}
        self._requests: dict[tuple[str, str], int] = {}
        # errors: {route: count}
        self._errors: dict[str, int] = {}
        # histogram observations per route:
        # {route: {"buckets": [counts...], "sum": float, "count": int}}
        self._latency: dict[str, dict[str, object]] = {}

    @property
    def buckets_seconds(self) -> tuple[float, ...]:
        return self._buckets

    def _ensure_latency_slot(self, route: str) -> dict[str, object]:
        slot = self._latency.get(route)
        if slot is None:
            slot = {
                "buckets": [0] * len(self._buckets),
                "sum": 0.0,
                "count": 0,
            }
            self._latency[route] = slot
        return slot

    def inc_request(self, route: str, status: int, latency_ms: float) -> None:
        """Record one HTTP request.

        ``route`` is sanitized to keep cardinality bounded. ``status`` is
        coerced to ``str`` to mirror the Prometheus convention. ``latency_ms``
        is observed in the latency histogram (converted to seconds) — values
        below zero are clamped to zero.
        """

        safe_route = _sanitize_route(str(route))
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            status_int = 0
        status_label = str(status_int)
        try:
            latency_seconds = max(0.0, float(latency_ms) / 1000.0)
        except (TypeError, ValueError):
            latency_seconds = 0.0

        with self._lock:
            key = (safe_route, status_label)
            self._requests[key] = self._requests.get(key, 0) + 1
            if status_int >= 500:
                self._errors[safe_route] = self._errors.get(safe_route, 0) + 1

            slot = self._ensure_latency_slot(safe_route)
            buckets = slot["buckets"]  # type: ignore[assignment]
            assert isinstance(buckets, list)
            for index, upper in enumerate(self._buckets):
                if latency_seconds <= upper:
                    buckets[index] += 1
            slot["sum"] = float(slot["sum"]) + latency_seconds  # type: ignore[arg-type]
            slot["count"] = int(slot["count"]) + 1  # type: ignore[arg-type]

    def snapshot(self) -> dict[str, object]:
        """Return a deep-copy snapshot of the current registry state.

        Useful for tests and for any callers that want to inspect the
        metrics without going through the text exposition format.
        """

        with self._lock:
            return {
                "requests": dict(self._requests),
                "errors": dict(self._errors),
                "latency": {
                    route: {
                        "buckets": list(slot["buckets"]),  # type: ignore[arg-type]
                        "sum": float(slot["sum"]),  # type: ignore[arg-type]
                        "count": int(slot["count"]),  # type: ignore[arg-type]
                    }
                    for route, slot in self._latency.items()
                },
                "buckets_seconds": list(self._buckets),
            }

    def render_text(self) -> str:
        """Render the registry as Prometheus text exposition (v0.0.4).

        The output always starts with ``# HELP`` and ``# TYPE`` headers for
        every metric family — even families with no observations yet — so
        Grafana panels render an empty series instead of erroring out.
        """

        with self._lock:
            requests_items = sorted(self._requests.items())
            errors_items = sorted(self._errors.items())
            latency_items = sorted(self._latency.items())
            buckets = self._buckets

        lines: list[str] = []

        # http_requests_total
        lines.append(
            "# HELP http_requests_total Total HTTP requests served by the lvcodex API."
        )
        lines.append("# TYPE http_requests_total counter")
        for (route, status_label), count in requests_items:
            lines.append(
                'http_requests_total{route="%s",status="%s"} %s'
                % (
                    _escape_label_value(route),
                    _escape_label_value(status_label),
                    _format_float(float(count)),
                )
            )

        # http_request_errors_total
        lines.append(
            "# HELP http_request_errors_total Total HTTP 5xx responses served by the lvcodex API."
        )
        lines.append("# TYPE http_request_errors_total counter")
        for route, count in errors_items:
            lines.append(
                'http_request_errors_total{route="%s"} %s'
                % (_escape_label_value(route), _format_float(float(count)))
            )

        # http_request_duration_seconds (histogram)
        lines.append(
            "# HELP http_request_duration_seconds HTTP request latency in seconds, observed per route."
        )
        lines.append("# TYPE http_request_duration_seconds histogram")
        for route, slot in latency_items:
            route_label = _escape_label_value(route)
            bucket_counts = slot["buckets"]  # type: ignore[index]
            assert isinstance(bucket_counts, list)
            for index, upper in enumerate(buckets):
                lines.append(
                    'http_request_duration_seconds_bucket{route="%s",le="%s"} %s'
                    % (
                        route_label,
                        _format_float(upper),
                        _format_float(float(bucket_counts[index])),
                    )
                )
            total_count = int(slot["count"])  # type: ignore[arg-type]
            lines.append(
                'http_request_duration_seconds_bucket{route="%s",le="+Inf"} %s'
                % (route_label, _format_float(float(total_count)))
            )
            lines.append(
                'http_request_duration_seconds_sum{route="%s"} %s'
                % (route_label, _format_float(float(slot["sum"])))  # type: ignore[arg-type]
            )
            lines.append(
                'http_request_duration_seconds_count{route="%s"} %s'
                % (route_label, _format_float(float(total_count)))
            )

        # Trailing newline keeps the output compatible with the Prometheus
        # parser, which expects every record (including the last) to end
        # with ``\n``.
        return "\n".join(lines) + "\n"


__all__ = [
    "DEFAULT_BUCKETS_SECONDS",
    "RequestMetrics",
]
