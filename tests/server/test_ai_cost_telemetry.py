"""T-027 AI cost telemetry unit tests.

Covers:

* :func:`server_app.services.cost.cost_for` — provider+model rate lookup,
  USD→EUR conversion, fallback for unknown models, env override via
  ``LVCODEX_AI_COST_TABLE_JSON``.
* :func:`server_app.services.cost.extract_usage` — OpenAI/Groq shape
  (``prompt_tokens``/``completion_tokens``) plus Anthropic-style fallback.
* :class:`server_app.services.cost.CostMetrics` — thread-safe counter
  increments and Prometheus text rendering for the families
  ``lvcodex_ai_tokens_total{provider,model,direction}`` and
  ``lvcodex_ai_cost_cents_total{provider,model}``.
* :func:`server_app.services.evaluator.record_ai_cost_from_response` —
  end-to-end happy path and defensive no-op on malformed payloads.
* ``monitoring/alerts/cost-budget.yml`` — basic structural sanity checks
  so a typo in the alert rules does not silently disable budget pages.
"""

from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from server_app.services import cost as cost_service
from server_app.services.evaluator import record_ai_cost_from_response


REPO_ROOT = Path(__file__).resolve().parents[2]


def _isolate_registry() -> cost_service.CostMetrics:
    """Replace the module singleton with a fresh registry for one test."""

    return cost_service.reset_cost_registry()


# ---------------------------------------------------------------------------
# cost_for — rate table lookups
# ---------------------------------------------------------------------------


class CostForLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        # Force the deterministic default FX rate so the test does not
        # depend on the operator's local override.
        self._fx_patch = patch.dict(
            os.environ, {"LVCODEX_AI_USD_TO_EUR_RATE": "0.92"}, clear=False
        )
        self._fx_patch.start()
        # Strip any operator-supplied cost table so the built-in defaults
        # are used unless a sub-test re-injects one.
        os.environ.pop("LVCODEX_AI_COST_TABLE_JSON", None)

    def tearDown(self) -> None:
        self._fx_patch.stop()
        os.environ.pop("LVCODEX_AI_COST_TABLE_JSON", None)

    def test_groq_llama_at_default_rate(self) -> None:
        # 1M input tokens at $0.59/M with 0.92 EUR/USD = 0.5428 EUR = 54 cents.
        cents = cost_service.cost_for("groq", "llama-3.3-70b", 1_000_000, 0)
        self.assertEqual(cents, 54)

    def test_openai_gpt52_input_plus_output(self) -> None:
        # 100k input + 50k output at $10/M, 0.92 EUR/USD.
        # (100_000+50_000) * 10 / 1_000_000 = $1.5 → 1.38 EUR → 138 cents.
        cents = cost_service.cost_for("openai", "gpt-5.2", 100_000, 50_000)
        self.assertEqual(cents, 138)

    def test_openai_gpt4o_half_price_of_gpt52(self) -> None:
        cents_gpt4o = cost_service.cost_for("openai", "gpt-4o", 100_000, 50_000)
        cents_gpt52 = cost_service.cost_for("openai", "gpt-5.2", 100_000, 50_000)
        # GPT-4o is $5/M, GPT-5.2 is $10/M — should be exactly half.
        self.assertEqual(cents_gpt4o * 2, cents_gpt52)

    def test_unknown_model_falls_back_to_default_rate(self) -> None:
        cents = cost_service.cost_for("groq", "mystery-model-9b", 1_000_000, 0)
        # Falls back to UNKNOWN_MODEL_USD_PER_M ($5/M input) → $5 → 4.6 EUR → 460 cents.
        self.assertEqual(cents, 460)

    def test_env_cost_table_overrides_defaults(self) -> None:
        os.environ["LVCODEX_AI_COST_TABLE_JSON"] = (
            '{"groq:llama-3.3-70b": {"input": 1.0, "output": 2.0}}'
        )
        # 1M input at $1/M = $1 → 0.92 EUR → 92 cents.
        self.assertEqual(
            cost_service.cost_for("groq", "llama-3.3-70b", 1_000_000, 0), 92
        )
        # 1M output at $2/M = $2 → 1.84 EUR → 184 cents.
        self.assertEqual(
            cost_service.cost_for("groq", "llama-3.3-70b", 0, 1_000_000), 184
        )

    def test_env_cost_table_supports_scalar_shorthand(self) -> None:
        os.environ["LVCODEX_AI_COST_TABLE_JSON"] = (
            '{"groq:llama-3.3-70b": 3.0}'
        )
        # 1M tokens at $3/M = $3 → 2.76 EUR → 276 cents (per direction).
        self.assertEqual(
            cost_service.cost_for("groq", "llama-3.3-70b", 1_000_000, 1_000_000),
            552,
        )

    def test_negative_tokens_clamped_to_zero(self) -> None:
        cents = cost_service.cost_for("groq", "llama-3.3-70b", -50, -10)
        self.assertEqual(cents, 0)

    def test_non_numeric_tokens_return_zero(self) -> None:
        cents = cost_service.cost_for("groq", "llama-3.3-70b", "lots", "many")  # type: ignore[arg-type]
        self.assertEqual(cents, 0)

    def test_provider_and_model_are_case_insensitive(self) -> None:
        a = cost_service.cost_for("GROQ", "Llama-3.3-70b", 1_000_000, 0)
        b = cost_service.cost_for("groq", "llama-3.3-70b", 1_000_000, 0)
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# extract_usage — provider payload shape normalisation
# ---------------------------------------------------------------------------


class ExtractUsageTests(unittest.TestCase):
    def test_openai_groq_shape(self) -> None:
        usage = {"prompt_tokens": 120, "completion_tokens": 35}
        self.assertEqual(cost_service.extract_usage(usage), (120, 35))

    def test_anthropic_shape_fallback(self) -> None:
        usage = {"input_tokens": 40, "output_tokens": 5}
        self.assertEqual(cost_service.extract_usage(usage), (40, 5))

    def test_missing_payload_returns_zeros(self) -> None:
        self.assertEqual(cost_service.extract_usage(None), (0, 0))
        self.assertEqual(cost_service.extract_usage({}), (0, 0))
        self.assertEqual(cost_service.extract_usage("not-a-dict"), (0, 0))

    def test_negative_values_clamped_to_zero(self) -> None:
        usage = {"prompt_tokens": -1, "completion_tokens": -2}
        self.assertEqual(cost_service.extract_usage(usage), (0, 0))

    def test_non_numeric_values_ignored(self) -> None:
        usage = {"prompt_tokens": "many", "completion_tokens": None}
        self.assertEqual(cost_service.extract_usage(usage), (0, 0))


# ---------------------------------------------------------------------------
# CostMetrics — counter increments + Prometheus rendering
# ---------------------------------------------------------------------------


class CostMetricsCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("LVCODEX_AI_COST_TABLE_JSON", None)
        os.environ["LVCODEX_AI_USD_TO_EUR_RATE"] = "0.92"
        self.registry = _isolate_registry()

    def tearDown(self) -> None:
        cost_service.reset_cost_registry()
        os.environ.pop("LVCODEX_AI_USD_TO_EUR_RATE", None)

    def test_record_increments_token_and_cost_counters(self) -> None:
        # Two requests in a row should accumulate into the same labels.
        self.registry.record("groq", "llama-3.3-70b", 1_000_000, 0)
        self.registry.record("groq", "llama-3.3-70b", 500_000, 100_000)

        snapshot = self.registry.snapshot()
        self.assertEqual(
            snapshot["tokens"][("groq", "llama-3.3-70b", "input")],
            1_500_000,
        )
        self.assertEqual(
            snapshot["tokens"][("groq", "llama-3.3-70b", "output")],
            100_000,
        )
        # The summed counter is the sum of independently rounded calls,
        # not the rounded sum — keep the assertion math reproducible by
        # adding the per-call lookup values back together here.
        first = cost_service.cost_for("groq", "llama-3.3-70b", 1_000_000, 0)
        second = cost_service.cost_for("groq", "llama-3.3-70b", 500_000, 100_000)
        self.assertEqual(
            snapshot["cost_cents"][("groq", "llama-3.3-70b")],
            first + second,
        )

    def test_override_eur_cents_bypasses_lookup(self) -> None:
        result = self.registry.record(
            "openai", "gpt-5.2", 1_000, 200, eur_cents=999
        )
        self.assertEqual(result["eur_cents"], 999)
        self.assertEqual(
            self.registry.snapshot()["cost_cents"][("openai", "gpt-5.2")], 999
        )

    def test_zero_tokens_do_not_emit_label_series(self) -> None:
        # When both directions are zero we still want a clean snapshot — no
        # spurious 0-count series.
        self.registry.record("groq", "llama-3.3-70b", 0, 0)
        snapshot = self.registry.snapshot()
        self.assertEqual(snapshot["tokens"], {})
        # cost_for() rounds 0 tokens to 0 cents → no cost entry either.
        self.assertEqual(snapshot["cost_cents"], {})

    def test_inc_alias_matches_record(self) -> None:
        # The .inc() alias mirrors the surface offered by RequestMetrics
        # and the earlier T-027 draft — exercise it so a typo in the
        # alias signature fails CI before downstream code regresses.
        self.registry.inc(
            provider="openai",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            eur_cents=42,
        )
        snapshot = self.registry.snapshot()
        self.assertEqual(snapshot["tokens"][("openai", "gpt-4o", "input")], 10)
        self.assertEqual(snapshot["cost_cents"][("openai", "gpt-4o")], 42)

    def test_render_text_emits_help_and_type_headers(self) -> None:
        self.registry.record("openai", "gpt-4o", 1_000_000, 100_000)
        text = self.registry.render_text()

        self.assertIn("# HELP lvcodex_ai_tokens_total", text)
        self.assertIn("# TYPE lvcodex_ai_tokens_total counter", text)
        self.assertIn("# HELP lvcodex_ai_cost_cents_total", text)
        self.assertIn("# TYPE lvcodex_ai_cost_cents_total counter", text)
        self.assertIn(
            'lvcodex_ai_tokens_total{provider="openai",model="gpt-4o",direction="input"}',
            text,
        )
        self.assertIn(
            'lvcodex_ai_cost_cents_total{provider="openai",model="gpt-4o"}',
            text,
        )

    def test_record_is_thread_safe(self) -> None:
        # 8 threads × 1000 increments at 1 token each — concurrent
        # mutations must not lose any increments.
        threads = []
        per_thread = 1000

        def hammer() -> None:
            for _ in range(per_thread):
                self.registry.record("groq", "llama-3.3-70b", 1, 0, eur_cents=1)

        for _ in range(8):
            t = threading.Thread(target=hammer)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        snapshot = self.registry.snapshot()
        self.assertEqual(
            snapshot["tokens"][("groq", "llama-3.3-70b", "input")],
            8 * per_thread,
        )
        self.assertEqual(
            snapshot["cost_cents"][("groq", "llama-3.3-70b")],
            8 * per_thread,
        )


# ---------------------------------------------------------------------------
# Module-level facade + singleton lifecycle
# ---------------------------------------------------------------------------


class CostRegistryFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_service.reset_cost_registry()

    def tearDown(self) -> None:
        cost_service.reset_cost_registry()

    def test_record_uses_singleton(self) -> None:
        cost_service.record("groq", "llama-3.3-70b", 100, 50, eur_cents=7)
        snapshot = cost_service.cost_registry().snapshot()
        self.assertEqual(snapshot["cost_cents"][("groq", "llama-3.3-70b")], 7)

    def test_reset_returns_fresh_instance(self) -> None:
        first = cost_service.cost_registry()
        first.record("groq", "llama-3.3-70b", 100, 50, eur_cents=7)
        second = cost_service.reset_cost_registry()
        self.assertIsNot(first, second)
        self.assertEqual(second.snapshot()["tokens"], {})

    def test_daily_budget_default_is_five_eur(self) -> None:
        os.environ.pop("LVCODEX_AI_DAILY_BUDGET_EUR", None)
        self.assertEqual(cost_service.daily_budget_eur(), 5.0)

    def test_daily_budget_env_override(self) -> None:
        with patch.dict(
            os.environ, {"LVCODEX_AI_DAILY_BUDGET_EUR": "12.5"}, clear=False
        ):
            self.assertEqual(cost_service.daily_budget_eur(), 12.5)

    def test_daily_budget_invalid_falls_back_to_default(self) -> None:
        with patch.dict(
            os.environ, {"LVCODEX_AI_DAILY_BUDGET_EUR": "not-a-number"}, clear=False
        ):
            self.assertEqual(cost_service.daily_budget_eur(), 5.0)


# ---------------------------------------------------------------------------
# Evaluator hook (services/evaluator.py)
# ---------------------------------------------------------------------------


class EvaluatorCostHookTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("LVCODEX_AI_COST_TABLE_JSON", None)
        os.environ["LVCODEX_AI_USD_TO_EUR_RATE"] = "0.92"
        cost_service.reset_cost_registry()

    def tearDown(self) -> None:
        cost_service.reset_cost_registry()
        os.environ.pop("LVCODEX_AI_USD_TO_EUR_RATE", None)

    def test_records_from_successful_response(self) -> None:
        payload = {
            "provider": "groq",
            "model": "llama-3.3-70b",
            "usage": {"prompt_tokens": 500_000, "completion_tokens": 50_000},
        }
        result = record_ai_cost_from_response(payload)
        self.assertIsNotNone(result)
        assert result is not None  # for type narrowing
        self.assertEqual(result["input_tokens"], 500_000)
        self.assertEqual(result["output_tokens"], 50_000)
        snapshot = cost_service.cost_registry().snapshot()
        self.assertGreater(
            snapshot["cost_cents"][("groq", "llama-3.3-70b")], 0
        )

    def test_skips_when_provider_missing(self) -> None:
        result = record_ai_cost_from_response({"model": "x", "usage": {}})
        self.assertIsNone(result)

    def test_skips_when_payload_is_not_dict(self) -> None:
        self.assertIsNone(record_ai_cost_from_response("not-a-dict"))  # type: ignore[arg-type]
        self.assertIsNone(record_ai_cost_from_response(None))  # type: ignore[arg-type]

    def test_records_even_when_usage_missing(self) -> None:
        # Provider+model are present but usage payload missing → record
        # still runs (zero tokens, zero cost) so we can see the request
        # was processed.
        payload = {"provider": "openai", "model": "gpt-4o"}
        result = record_ai_cost_from_response(payload)
        self.assertEqual(result, {"input_tokens": 0, "output_tokens": 0, "eur_cents": 0})


# ---------------------------------------------------------------------------
# Budget alert YAML — structural sanity
# ---------------------------------------------------------------------------


class CostBudgetAlertFileTests(unittest.TestCase):
    """Parse the rules file and confirm the budget gate it enforces.

    These tests intentionally avoid a hard dependency on PyYAML — Python's
    stdlib does not ship a YAML parser. Instead we assert on the literal
    expression so a typo in the threshold (e.g. ``50`` instead of ``500``)
    fails CI loudly.
    """

    rules_path = REPO_ROOT / "monitoring" / "alerts" / "cost-budget.yml"

    def test_file_exists(self) -> None:
        self.assertTrue(self.rules_path.is_file(), self.rules_path)

    def test_defines_daily_budget_alert(self) -> None:
        text = self.rules_path.read_text(encoding="utf-8")
        self.assertIn("alert: AIDailySpendOverBudget", text)
        # 500 cents = 5 EUR (default LVCODEX_AI_DAILY_BUDGET_EUR).
        self.assertIn("lvcodex_ai_cost_cents_total[24h]", text)
        self.assertIn("> 500", text)
        self.assertIn("severity: page", text)

    def test_defines_hourly_burn_alert(self) -> None:
        text = self.rules_path.read_text(encoding="utf-8")
        self.assertIn("alert: AIHourlySpendSurge", text)
        # Hourly projection threshold equals the daily budget so we page
        # if the burn rate would exhaust the budget in <24h.
        self.assertIn("rate(lvcodex_ai_cost_cents_total[15m])) * 3600", text)
        self.assertIn("> 500", text)


# ---------------------------------------------------------------------------
# Grafana dashboard — structural sanity
# ---------------------------------------------------------------------------


class AICostDashboardTests(unittest.TestCase):
    dashboard_path = REPO_ROOT / "monitoring" / "dashboards" / "ai-cost.json"

    def test_file_exists(self) -> None:
        self.assertTrue(self.dashboard_path.is_file(), self.dashboard_path)

    def test_dashboard_panels_reference_t027_metrics(self) -> None:
        import json

        data = json.loads(self.dashboard_path.read_text(encoding="utf-8"))
        self.assertEqual(data["uid"], "lvcodex-ai-cost")
        panel_titles = {panel["title"] for panel in data["panels"]}
        # Plan deliverable: cost/hour, tokens/min, top models.
        self.assertIn("AI cost (EUR/hour) by model", panel_titles)
        self.assertIn("AI tokens per minute by direction", panel_titles)
        self.assertIn("Top models by 24h spend (EUR)", panel_titles)

        flattened = json.dumps(data)
        self.assertIn("lvcodex_ai_cost_cents_total", flattened)
        self.assertIn("lvcodex_ai_tokens_total", flattened)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    unittest.main()
