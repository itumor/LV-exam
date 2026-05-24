"""AI cost telemetry service (T-027).

Records per-AI-request token usage and converts it into a EUR-cents cost
estimate, then exposes the totals through a thread-safe in-process
Prometheus-text registry. The registry is rendered alongside the HTTP
metrics in the trailing T-014 ``/metrics`` hook (see
``server_app/core.py::_t014_install_metrics_hook``).

Design goals
------------
* **Telemetry MUST NOT poison success path.** Every public entry point is
  wrapped by the caller in ``try/except`` (see ``_record_ai_cost_telemetry``
  in ``server_app/core.py``); we additionally guard our own internals so a
  malformed cost table or unknown model never raises out of ``record``.
* **Provider+model → EUR cents/1M tokens** comes from the
  ``LVCODEX_AI_COST_TABLE_JSON`` env var when present, otherwise a small
  built-in default keyed by the providers in T-014 / T-026 (Groq
  Llama-3.3-70b, OpenAI GPT-5.2, OpenAI GPT-4o).
* **Thread safety.** ``ThreadingHTTPServer`` will call ``record`` from
  multiple worker threads when scoring is parallel-dispatched, so all
  state mutations take ``self._lock``.
* **No external dependencies.** This module deliberately uses only the
  standard library, mirroring ``server_app/metrics.py``.

USD → EUR conversion
--------------------
The default cost table is published by Groq/OpenAI in USD per 1M tokens.
We convert to EUR cents using ``LVCODEX_AI_USD_TO_EUR_RATE`` (default
``0.92``). The conversion is deliberately a single env-tunable scalar so
finance ops can adjust it without redeploying; FX precision better than
~5% is not material to the daily-budget alert which is the only consumer.

Public surface
--------------
* :func:`record(provider, model, input_tokens, output_tokens, eur_cents=None)`
  — increments the counter families. ``eur_cents`` may be supplied by the
  caller to override the lookup-derived value (used by tests).
* :func:`extract_usage(usage)` — pulls ``input_tokens`` and
  ``output_tokens`` from the provider's ``usage`` dict (OpenAI / Groq
  shape: ``prompt_tokens`` / ``completion_tokens``). Returns ``(0, 0)``
  on any missing/invalid shape.
* :func:`cost_registry()` — the singleton ``CostMetrics`` instance.
* :func:`cost_for(provider, model, input_tokens, output_tokens)` — pure
  calculator, returns EUR cents as a non-negative integer.
* :func:`reset_cost_registry()` — test helper, replaces the singleton.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Iterable


logger = logging.getLogger("lvcodex.cost")


# ---------------------------------------------------------------------------
# Cost table — USD per 1,000,000 tokens, split per direction.
# ---------------------------------------------------------------------------

# These defaults match the prices documented in the T-027 plan (Groq
# Llama-3.3-70b, OpenAI GPT-5.2, OpenAI GPT-4o). The plan only specifies
# a single per-1M rate so we use the same value for input + output unless
# the operator overrides via ``LVCODEX_AI_COST_TABLE_JSON``.
DEFAULT_COST_TABLE_USD_PER_M: dict[tuple[str, str], dict[str, float]] = {
    ("groq", "llama-3.3-70b"): {"input": 0.59, "output": 0.59},
    ("openai", "gpt-5.2"): {"input": 10.0, "output": 10.0},
    ("openai", "gpt-4o"): {"input": 5.0, "output": 5.0},
}

# Fallback used when the (provider, model) key is unknown. Picked
# conservatively so an unknown model still produces a non-zero cost
# estimate (better to over-report than silently drop spend).
UNKNOWN_MODEL_USD_PER_M: dict[str, float] = {"input": 5.0, "output": 5.0}

DEFAULT_USD_TO_EUR_RATE = 0.92


def _normalize_provider(provider: Any) -> str:
    return str(provider or "").strip().lower() or "unknown"


def _normalize_model(model: Any) -> str:
    return str(model or "").strip().lower() or "unknown"


def _normalize_direction(direction: Any) -> str:
    value = str(direction or "").strip().lower()
    return value if value in {"input", "output"} else "input"


def _load_cost_table_from_env() -> dict[tuple[str, str], dict[str, float]] | None:
    """Parse ``LVCODEX_AI_COST_TABLE_JSON`` into the internal cost-table shape.

    Expected JSON shape::

        {
          "groq:llama-3.3-70b": {"input": 0.59, "output": 0.59},
          "openai:gpt-5.2":     {"input": 10.0, "output": 10.0}
        }

    The single-rate shorthand ``{"groq:llama-3.3-70b": 0.59}`` is also
    accepted (applied to both directions). Returns ``None`` when the env
    var is unset or malformed — callers fall back to the built-in
    defaults.
    """

    raw = os.getenv("LVCODEX_AI_COST_TABLE_JSON")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as error:
        logger.warning("t027_cost_table_parse_failed error=%s", error)
        return None
    if not isinstance(parsed, dict):
        logger.warning("t027_cost_table_not_object type=%s", type(parsed).__name__)
        return None

    table: dict[tuple[str, str], dict[str, float]] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or ":" not in key:
            continue
        provider_raw, _, model_raw = key.partition(":")
        provider = _normalize_provider(provider_raw)
        model = _normalize_model(model_raw)
        if isinstance(value, (int, float)):
            rate = max(0.0, float(value))
            table[(provider, model)] = {"input": rate, "output": rate}
            continue
        if isinstance(value, dict):
            input_rate = value.get("input", value.get("in"))
            output_rate = value.get("output", value.get("out", input_rate))
            try:
                table[(provider, model)] = {
                    "input": max(0.0, float(input_rate or 0.0)),
                    "output": max(0.0, float(output_rate or 0.0)),
                }
            except (TypeError, ValueError):
                continue
    return table or None


def _active_cost_table() -> dict[tuple[str, str], dict[str, float]]:
    return _load_cost_table_from_env() or DEFAULT_COST_TABLE_USD_PER_M


def _usd_to_eur_rate() -> float:
    raw = os.getenv("LVCODEX_AI_USD_TO_EUR_RATE")
    if not raw:
        return DEFAULT_USD_TO_EUR_RATE
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_USD_TO_EUR_RATE
    if rate <= 0:
        return DEFAULT_USD_TO_EUR_RATE
    return rate


def cost_for(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> int:
    """Return the EUR-cents cost for a (provider, model, tokens) tuple.

    The result is rounded to the nearest cent (minimum 0). An unknown
    (provider, model) pair falls back to :data:`UNKNOWN_MODEL_USD_PER_M`
    so spend is never silently dropped.
    """

    p = _normalize_provider(provider)
    m = _normalize_model(model)
    try:
        in_tokens = max(0, int(input_tokens))
        out_tokens = max(0, int(output_tokens))
    except (TypeError, ValueError):
        return 0

    table = _active_cost_table()
    rates = table.get((p, m)) or UNKNOWN_MODEL_USD_PER_M
    input_rate = float(rates.get("input", UNKNOWN_MODEL_USD_PER_M["input"]))
    output_rate = float(rates.get("output", UNKNOWN_MODEL_USD_PER_M["output"]))

    usd = (in_tokens * input_rate + out_tokens * output_rate) / 1_000_000.0
    eur = usd * _usd_to_eur_rate()
    eur_cents = round(eur * 100)
    return max(0, int(eur_cents))


def extract_usage(usage: Any) -> tuple[int, int]:
    """Normalise a provider ``usage`` payload to ``(input, output)`` tokens.

    Supports the OpenAI / Groq shape (``prompt_tokens`` /
    ``completion_tokens``) and Anthropic-style fields
    (``input_tokens`` / ``output_tokens``). Returns ``(0, 0)`` if the
    payload is missing, malformed, or contains negative values — telemetry
    must never raise.
    """

    if not isinstance(usage, dict):
        return (0, 0)

    def _coerce(key: str, *fallbacks: str) -> int:
        for candidate in (key, *fallbacks):
            value = usage.get(candidate)
            if value is None:
                continue
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                continue
        return 0

    input_tokens = _coerce("prompt_tokens", "input_tokens")
    output_tokens = _coerce("completion_tokens", "output_tokens")
    return (input_tokens, output_tokens)


# ---------------------------------------------------------------------------
# Counter registry
# ---------------------------------------------------------------------------


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_float(value: float) -> str:
    if value == float("inf"):
        return "+Inf"
    if value == float("-inf"):
        return "-Inf"
    if value != value:  # NaN
        return "NaN"
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value)}"
    return repr(float(value))


class CostMetrics:
    """Thread-safe counter registry for AI token + EUR-cents totals.

    Exposes two Prometheus counter families:

    * ``lvcodex_ai_tokens_total{provider,model,direction}``
    * ``lvcodex_ai_cost_cents_total{provider,model}``

    Cardinality is bounded by the cost table size (a handful of models),
    plus an ``unknown`` bucket for any provider/model combination that
    isn't pre-registered. The ``direction`` label is one of
    ``input`` / ``output``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {(provider, model, direction): tokens}
        self._tokens: dict[tuple[str, str, str], int] = {}
        # {(provider, model): cents}
        self._cost_cents: dict[tuple[str, str], int] = {}

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        eur_cents: int | None = None,
    ) -> dict[str, int]:
        """Record one AI provider call.

        Returns a snapshot dict of the increment for the convenience of
        unit tests. Always returns even when token counts are zero so the
        caller can observe a request was processed.
        """

        p = _normalize_provider(provider)
        m = _normalize_model(model)
        try:
            in_tokens = max(0, int(input_tokens))
        except (TypeError, ValueError):
            in_tokens = 0
        try:
            out_tokens = max(0, int(output_tokens))
        except (TypeError, ValueError):
            out_tokens = 0

        if eur_cents is None:
            cents = cost_for(p, m, in_tokens, out_tokens)
        else:
            try:
                cents = max(0, int(eur_cents))
            except (TypeError, ValueError):
                cents = 0

        with self._lock:
            if in_tokens:
                key_in = (p, m, "input")
                self._tokens[key_in] = self._tokens.get(key_in, 0) + in_tokens
            if out_tokens:
                key_out = (p, m, "output")
                self._tokens[key_out] = self._tokens.get(key_out, 0) + out_tokens
            if cents:
                cost_key = (p, m)
                self._cost_cents[cost_key] = self._cost_cents.get(cost_key, 0) + cents

        return {
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "eur_cents": cents,
        }

    # Alias for callers that prefer the .inc() convention used by other
    # in-house metric registries (matches the surface offered by the
    # earlier T-027 draft so any downstream code that already binds to
    # ``.inc`` keeps working without an alias rename PR).
    def inc(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        eur_cents: int | None = None,
    ) -> dict[str, int]:
        return self.record(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            eur_cents=eur_cents,
        )

    def snapshot(self) -> dict[str, dict[tuple[str, ...], int]]:
        with self._lock:
            return {
                "tokens": dict(self._tokens),
                "cost_cents": dict(self._cost_cents),
            }

    def total_cost_cents(self) -> int:
        with self._lock:
            return sum(self._cost_cents.values())

    def render_text(self) -> str:
        """Render the registry in Prometheus text exposition v0.0.4 format."""

        with self._lock:
            tokens_items = sorted(self._tokens.items())
            cost_items = sorted(self._cost_cents.items())

        lines: list[str] = []

        lines.append(
            "# HELP lvcodex_ai_tokens_total Total AI provider tokens accounted by lvcodex (T-027)."
        )
        lines.append("# TYPE lvcodex_ai_tokens_total counter")
        for (provider, model, direction), count in tokens_items:
            lines.append(
                'lvcodex_ai_tokens_total{provider="%s",model="%s",direction="%s"} %s'
                % (
                    _escape_label_value(provider),
                    _escape_label_value(model),
                    _escape_label_value(direction),
                    _format_float(count),
                )
            )

        lines.append(
            "# HELP lvcodex_ai_cost_cents_total Total AI provider spend in EUR cents (T-027)."
        )
        lines.append("# TYPE lvcodex_ai_cost_cents_total counter")
        for (provider, model), cents in cost_items:
            lines.append(
                'lvcodex_ai_cost_cents_total{provider="%s",model="%s"} %s'
                % (
                    _escape_label_value(provider),
                    _escape_label_value(model),
                    _format_float(cents),
                )
            )

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Module-level singleton + thin facade.
# ---------------------------------------------------------------------------


_REGISTRY_LOCK = threading.Lock()
_REGISTRY: CostMetrics | None = None


def cost_registry() -> CostMetrics:
    """Return the process-wide :class:`CostMetrics` singleton.

    Lazy-constructed so importing this module is side-effect-free. The
    ``/metrics`` hook in :func:`server_app.core._t014_install_metrics_hook`
    calls this every scrape, so creation must be cheap and idempotent.
    """

    global _REGISTRY
    if _REGISTRY is None:
        with _REGISTRY_LOCK:
            if _REGISTRY is None:
                _REGISTRY = CostMetrics()
    return _REGISTRY


def reset_cost_registry() -> CostMetrics:
    """Replace the singleton — test helper.

    Production code never calls this. Tests that exercise ``record`` use
    this to start each case with an empty counter set.
    """

    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = CostMetrics()
        return _REGISTRY


def record(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    eur_cents: int | None = None,
) -> dict[str, int]:
    """Module-level facade over :meth:`CostMetrics.record` (singleton).

    Lazily resolves the singleton so callers don't have to keep a
    reference. Used by ``server_app/core.py::_record_ai_cost_telemetry``.
    """

    return cost_registry().record(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        eur_cents=eur_cents,
    )


def daily_budget_eur() -> float:
    """Return ``LVCODEX_AI_DAILY_BUDGET_EUR`` (default ``5.0`` EUR)."""

    raw = os.getenv("LVCODEX_AI_DAILY_BUDGET_EUR")
    if not raw:
        return 5.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return max(0.0, value)


__all__ = [
    "CostMetrics",
    "DEFAULT_COST_TABLE_USD_PER_M",
    "DEFAULT_USD_TO_EUR_RATE",
    "UNKNOWN_MODEL_USD_PER_M",
    "cost_for",
    "cost_registry",
    "daily_budget_eur",
    "extract_usage",
    "record",
    "reset_cost_registry",
]


def _iter_cost_table_items() -> Iterable[tuple[tuple[str, str], dict[str, float]]]:
    """Helper for introspection / tests."""

    return _active_cost_table().items()
