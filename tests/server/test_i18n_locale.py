"""Unit tests for T-062 — i18n locale resolution and fallback.

Covers the deliverables in the T-062 plan:

* (1) The locale catalog loads lv-LV, en-US and lt-LT from
      ``server_app/services/locales/``.
* (2) ``resolve_locale`` honors the candidate chain (cookie/query/header)
      and falls back to ``lv-LV`` when nothing matches.
* (3) ``Accept-Language`` parsing returns highest-quality first and
      tolerates malformed input.
* (4) ``translate`` falls back to the default locale, then to the key,
      so a missing translation never crashes a request.
* (5) String fallback works across languages — Lithuanian inherits any
      key it does not explicitly override from ``lv-LV``.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_i18n():
    """Load ``server_app/services/i18n.py`` by path.

    Bypassing the package ``__init__`` keeps these tests hermetic — they
    do not depend on the rest of the import graph (db, sentry, ...).
    """

    if "i18n_under_test" in sys.modules:
        return sys.modules["i18n_under_test"]
    spec = importlib.util.spec_from_file_location(
        "i18n_under_test",
        ROOT / "server_app" / "services" / "i18n.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["i18n_under_test"] = module
    spec.loader.exec_module(module)
    return module


class LocaleCatalogTests(unittest.TestCase):
    """T-062 (1): the three shipped locale files load cleanly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.i18n = _load_i18n()

    def test_three_locales_shipped(self) -> None:
        catalog = self.i18n.load_catalog()
        for expected in ("lv-LV", "en-US", "lt-LT"):
            self.assertIn(expected, catalog, f"missing locale: {expected}")

    def test_available_locales_orders_declared_first(self) -> None:
        available = self.i18n.available_locales()
        # lv-LV must come first — it is the default locale.
        self.assertEqual(available[0], "lv-LV")
        # All three declared locales must appear, in declared order.
        for code in ("lv-LV", "en-US", "lt-LT"):
            self.assertIn(code, available)

    def test_locale_metadata_present(self) -> None:
        meta = self.i18n.describe_locale("lt-LT")
        self.assertEqual(meta["code"], "lt-LT")
        self.assertEqual(meta["english_name"], "Lithuanian")
        self.assertEqual(meta["direction"], "ltr")

    def test_describe_locale_unknown_falls_back(self) -> None:
        meta = self.i18n.describe_locale("xx-YY")
        # Unknown locales must fall back to the default — never raise.
        self.assertEqual(meta["code"], "lv-LV")


class NormalizeAndAcceptLanguageTests(unittest.TestCase):
    """T-062 (3): locale-tag normalization and Accept-Language parsing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.i18n = _load_i18n()

    def test_normalize_canonicalizes_casing(self) -> None:
        self.assertEqual(self.i18n.normalize_locale("LV-lv"), "lv-LV")
        self.assertEqual(self.i18n.normalize_locale("en_us"), "en-US")
        self.assertEqual(self.i18n.normalize_locale("lt"), "lt")

    def test_normalize_rejects_garbage(self) -> None:
        self.assertIsNone(self.i18n.normalize_locale(""))
        self.assertIsNone(self.i18n.normalize_locale(None))
        self.assertIsNone(self.i18n.normalize_locale("1"))

    def test_accept_language_sorted_by_quality(self) -> None:
        parsed = self.i18n.parse_accept_language(
            "lt-LT,lt;q=0.9,en;q=0.8,*;q=0.1"
        )
        codes = [code for code, _q in parsed]
        # Highest quality first.
        self.assertEqual(codes[0], "lt-LT")
        self.assertEqual(codes[1], "lt")
        self.assertEqual(codes[2], "en")

    def test_accept_language_zero_q_dropped(self) -> None:
        parsed = self.i18n.parse_accept_language("en;q=0,lt-LT;q=0.5")
        codes = [code for code, _q in parsed]
        self.assertNotIn("en", codes)
        self.assertIn("lt-LT", codes)

    def test_accept_language_malformed_q(self) -> None:
        # Bad q values fall to zero (and are therefore dropped).
        parsed = self.i18n.parse_accept_language("en;q=notanumber,lt-LT")
        codes = [code for code, _q in parsed]
        self.assertEqual(codes, ["lt-LT"])

    def test_accept_language_empty_string(self) -> None:
        self.assertEqual(self.i18n.parse_accept_language(""), [])
        self.assertEqual(self.i18n.parse_accept_language(None), [])


class LocaleResolutionTests(unittest.TestCase):
    """T-062 (2): the candidate → header → default chain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.i18n = _load_i18n()

    def test_explicit_candidate_wins(self) -> None:
        result = self.i18n.resolve_locale("lt-LT")
        self.assertEqual(result, "lt-LT")

    def test_first_supported_candidate_wins(self) -> None:
        result = self.i18n.resolve_locale("xx-YY", "en-US", "lt-LT")
        self.assertEqual(result, "en-US")

    def test_language_only_candidate_matches_family(self) -> None:
        # ``"lt"`` should resolve to lt-LT (the only supported lt-* locale).
        result = self.i18n.resolve_locale("lt")
        self.assertEqual(result, "lt-LT")

    def test_falls_back_to_accept_language(self) -> None:
        result = self.i18n.resolve_locale(
            None,
            accept_language="lt-LT;q=0.9,en-US;q=0.5",
        )
        self.assertEqual(result, "lt-LT")

    def test_falls_back_to_default_when_nothing_matches(self) -> None:
        result = self.i18n.resolve_locale(
            "xx-YY",
            "qq-ZZ",
            accept_language="fr-FR,de-DE",
        )
        self.assertEqual(result, "lv-LV")

    def test_no_inputs_returns_default(self) -> None:
        result = self.i18n.resolve_locale()
        self.assertEqual(result, "lv-LV")

    def test_unsupported_xx_yy_falls_back_to_family(self) -> None:
        # ``"lt-XX"`` should still resolve to lt-LT (xx-YY can't match,
        # but the language family ``lt`` can).
        result = self.i18n.resolve_locale("lt-XX")
        self.assertEqual(result, "lt-LT")


class TranslationFallbackTests(unittest.TestCase):
    """T-062 (4)+(5): translate() never returns None and falls back."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.i18n = _load_i18n()

    def test_known_key_returns_translated_string(self) -> None:
        # lv-LV has a translation for app.title.
        self.assertEqual(
            self.i18n.translate("app.title", locale="lv-LV"),
            "Latviešu valodas A2 eksāmens",
        )

    def test_lithuanian_translation_is_used(self) -> None:
        self.assertEqual(
            self.i18n.translate("header.signin", locale="lt-LT"),
            "Prisijungti",
        )

    def test_unknown_key_returns_the_key(self) -> None:
        # Missing translation must never return None or empty.
        result = self.i18n.translate("nonexistent.key", locale="lt-LT")
        self.assertEqual(result, "nonexistent.key")

    def test_unknown_key_default_is_used(self) -> None:
        result = self.i18n.translate(
            "still.nonexistent",
            locale="en-US",
            default="My fallback",
        )
        self.assertEqual(result, "My fallback")

    def test_missing_locale_falls_back_to_default(self) -> None:
        # ``xx-YY`` is not in the catalog. We must fall back to lv-LV's
        # translation, not blow up.
        result = self.i18n.translate("app.title", locale="xx-YY")
        self.assertEqual(result, "Latviešu valodas A2 eksāmens")

    def test_placeholders_substituted(self) -> None:
        result = self.i18n.translate(
            "header.hello",
            locale="en-US",
            placeholders={"name": "Anna"},
        )
        self.assertEqual(result, "Hi, Anna")

    def test_missing_placeholder_left_intact(self) -> None:
        # If the caller forgets a placeholder, we keep the literal ``{name}``
        # marker rather than crashing.
        result = self.i18n.translate(
            "header.hello",
            locale="en-US",
            placeholders={},
        )
        self.assertEqual(result, "Hi, {name}")

    def test_iter_strings_inherits_from_default(self) -> None:
        """T-062 (5): lt-LT strings inherit any key it does not override."""

        pairs = dict(self.i18n.iter_strings("lt-LT"))
        # A key that exists in both lv-LV and lt-LT must take the lt-LT value.
        self.assertEqual(pairs["header.signin"], "Prisijungti")
        # Every key in the default catalog must be present in the merged
        # output for lt-LT (fallback inheritance).
        lv_pairs = dict(self.i18n.iter_strings("lv-LV"))
        for key in lv_pairs:
            self.assertIn(key, pairs, f"missing fallback key: {key}")


if __name__ == "__main__":
    unittest.main()
