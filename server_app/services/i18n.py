"""i18n service (T-062, extended T-063).

Tiny, dependency-free internationalization layer used by the Lithuanian
A2 fork (T-062), the Estonian A2 fork (T-063), and any future locale
extension. Owns three concerns:

1. **Locale catalog** — discovers and loads the JSON locale files that
   ship next to this module under ``server_app/services/locales/*.json``.
   Each file is a flat ``{strings: {key: value}}`` mapping plus locale
   metadata (display name, direction).

2. **Locale resolution** — given a candidate (user preference, cookie,
   query string, ``Accept-Language`` header) returns the best supported
   locale code, falling back through a chain that ends at the default
   (``lv-LV``). The resolver is the single place that decides "which
   strings file do we load for this request?".

3. **String lookup with fallback** — :func:`translate` returns the
   string for ``key`` in ``locale``, falling back to the default locale
   and finally to the key itself so missing translations never throw or
   render empty in the UI.

The module is hot-reload-friendly in tests: every public helper takes
an optional ``catalog`` override that lets tests inject synthetic
locales without touching the on-disk catalog.

Design notes
------------
* No third-party deps. The repo already runs on Python 3.10+.
* Locale codes are normalized to ``xx-YY`` casing on read. Unsupported
  locales fall back rather than raising — a missing translation must
  never crash a learner-facing request.
* The default locale is ``lv-LV`` (the original platform language).
  Lithuanian (``lt-LT``) and English (``en-US``) are first-class
  alongside it as of T-062; Estonian (``et-EE``) was added in T-063.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "LOCALES_DIR",
    "available_locales",
    "load_catalog",
    "normalize_locale",
    "parse_accept_language",
    "resolve_locale",
    "translate",
    "describe_locale",
    "iter_strings",
]


_LOGGER = logging.getLogger("server_app.i18n")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Directory containing ``{locale}.json`` files. Resolved relative to this
#: module so test runs and packaged deploys agree on the layout.
LOCALES_DIR: Path = Path(__file__).resolve().parent / "locales"

#: Default locale used as the final fallback. Matches the original
#: platform language. Tests may override via :func:`resolve_locale`'s
#: ``default`` keyword.
DEFAULT_LOCALE: str = "lv-LV"

#: Locales the platform formally supports. The list is the union of
#: files that ship under :data:`LOCALES_DIR` and is recomputed from disk
#: by :func:`available_locales` — this tuple is just the declared
#: baseline so callers (and the frontend switcher) have a stable
#: ordering. T-062 added ``lt-LT``; T-063 added ``et-EE``.
SUPPORTED_LOCALES: tuple[str, ...] = ("lv-LV", "en-US", "lt-LT", "et-EE")


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


def normalize_locale(value: str | None) -> str | None:
    """Normalize a locale tag to ``xx-YY`` form.

    Returns ``None`` for empty or obviously malformed input rather than
    raising — callers feed this directly off user-controlled headers and
    cookies. Examples::

        normalize_locale("lv")     -> "lv"
        normalize_locale("LV-lv")  -> "lv-LV"
        normalize_locale("en_US")  -> "en-US"
        normalize_locale("xx")     -> "xx"
        normalize_locale("")       -> None
    """

    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("_", "-")
    if not cleaned:
        return None
    parts = cleaned.split("-", 1)
    lang = parts[0].lower()
    if not lang.isalpha() or not (2 <= len(lang) <= 3):
        return None
    if len(parts) == 1:
        return lang
    region = parts[1].upper()
    if not region.isalpha() or not (2 <= len(region) <= 3):
        return lang
    return f"{lang}-{region}"


@lru_cache(maxsize=8)
def _load_locale_file(path_str: str) -> Mapping[str, Any]:
    path = Path(path_str)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        _LOGGER.warning("locale file %s is not valid JSON: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        _LOGGER.warning("locale file %s did not parse to an object", path)
        return {}
    return data


def load_catalog(
    locales_dir: Path | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return ``{locale_code: locale_data}`` for every file under ``locales_dir``.

    Skips files that fail to parse — i18n must never take the app down.
    The result is keyed by the normalized locale code derived from the
    filename (so ``lv-LV.json`` -> ``"lv-LV"``).
    """

    base = locales_dir or LOCALES_DIR
    catalog: dict[str, Mapping[str, Any]] = {}
    if not base.is_dir():
        return catalog
    for entry in sorted(base.glob("*.json")):
        code = normalize_locale(entry.stem)
        if code is None:
            continue
        data = _load_locale_file(str(entry))
        if not data:
            continue
        # Allow the file to override its own locale code (e.g. an alias),
        # but normalize it through the same path the filename took.
        explicit = normalize_locale(str(data.get("locale") or ""))
        catalog[explicit or code] = data
    return catalog


def available_locales(
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return the supported locale codes in declared order.

    Locales declared in :data:`SUPPORTED_LOCALES` come first (preserving
    that order); any extra locales discovered on disk follow alphabetically.
    """

    cat = catalog if catalog is not None else load_catalog()
    declared = [code for code in SUPPORTED_LOCALES if code in cat]
    extras = sorted(code for code in cat.keys() if code not in declared)
    return declared + extras


def describe_locale(
    code: str,
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return ``{code, name, english_name, direction}`` for ``code``.

    Falls back to the default locale if ``code`` is unknown so the
    frontend language switcher always has something to render.
    """

    cat = catalog if catalog is not None else load_catalog()
    norm = normalize_locale(code) or DEFAULT_LOCALE
    data = cat.get(norm) or cat.get(DEFAULT_LOCALE) or {}
    return {
        "code": norm if norm in cat else DEFAULT_LOCALE,
        "name": str(data.get("name") or norm),
        "english_name": str(data.get("english_name") or norm),
        "direction": str(data.get("direction") or "ltr"),
    }


# ---------------------------------------------------------------------------
# Accept-Language parsing
# ---------------------------------------------------------------------------


def parse_accept_language(header: str | None) -> list[tuple[str, float]]:
    """Parse an HTTP ``Accept-Language`` header into ``(code, q)`` tuples.

    Returned tuples are sorted by descending quality (default ``q=1.0``)
    with ties broken by header order. Invalid items are silently
    skipped. Locale tags are normalized to ``xx-YY`` form.

    Examples::

        parse_accept_language("lt-LT,lt;q=0.9,en;q=0.8")
        -> [("lt-LT", 1.0), ("lt", 0.9), ("en", 0.8)]
    """

    if not header or not isinstance(header, str):
        return []
    items: list[tuple[int, float, str]] = []
    for index, raw in enumerate(header.split(",")):
        chunk = raw.strip()
        if not chunk:
            continue
        if ";" in chunk:
            tag, _, params = chunk.partition(";")
            tag = tag.strip()
            quality = 1.0
            for param in params.split(";"):
                key, _, value = param.partition("=")
                if key.strip().lower() == "q":
                    try:
                        quality = float(value.strip())
                    except ValueError:
                        quality = 0.0
        else:
            tag = chunk
            quality = 1.0
        normalized = normalize_locale(tag)
        if normalized is None:
            continue
        if quality <= 0:
            continue
        items.append((index, quality, normalized))
    # Highest quality first; stable on insertion order for equal qualities.
    items.sort(key=lambda item: (-item[1], item[0]))
    return [(code, q) for _, q, code in items]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_locale(
    *candidates: str | None,
    accept_language: str | None = None,
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
    default: str = DEFAULT_LOCALE,
) -> str:
    """Pick the best supported locale for this request.

    Resolution chain:

    1. Each positional ``candidates`` value in order (e.g. user setting,
       cookie, query string). The first one that matches a supported
       locale wins. ``xx-YY`` candidates also match the bare ``xx``
       family — ``"lt-LT"`` will match ``"lt-LT"`` directly; a candidate
       of just ``"lt"`` matches any ``lt-*`` supported locale.
    2. The ``Accept-Language`` header, walked highest-quality first.
    3. ``default`` (which must be a supported locale; if it isn't, the
       first available locale wins instead).

    Examples::

        resolve_locale("lt-LT")                       -> "lt-LT"
        resolve_locale("xx-YY", accept_language="en") -> "en-US"
        resolve_locale(None, accept_language=None)    -> "lv-LV"
    """

    cat = catalog if catalog is not None else load_catalog()
    supported = list(cat.keys())
    if not supported:
        return default

    def _match(code: str | None) -> str | None:
        norm = normalize_locale(code)
        if norm is None:
            return None
        # Exact match first.
        if norm in cat:
            return norm
        # Language-only candidate: pick first supported xx-YY in that family.
        if "-" not in norm:
            for sup in supported:
                if sup.split("-", 1)[0].lower() == norm:
                    return sup
            return None
        # xx-YY candidate that doesn't exact-match: try the bare language.
        lang = norm.split("-", 1)[0].lower()
        for sup in supported:
            if sup.split("-", 1)[0].lower() == lang:
                return sup
        return None

    for candidate in candidates:
        hit = _match(candidate)
        if hit is not None:
            return hit

    for code, _q in parse_accept_language(accept_language):
        hit = _match(code)
        if hit is not None:
            return hit

    default_hit = _match(default)
    if default_hit is not None:
        return default_hit
    return supported[0]


# ---------------------------------------------------------------------------
# String lookup
# ---------------------------------------------------------------------------


def translate(
    key: str,
    *,
    locale: str | None = None,
    default: str | None = None,
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
    placeholders: Mapping[str, Any] | None = None,
) -> str:
    """Return the translated string for ``key`` in ``locale``.

    Fallback chain: requested locale -> default locale (:data:`DEFAULT_LOCALE`)
    -> the ``default`` argument -> the key itself. The result is never
    ``None`` so callers can drop it straight into a UI string without
    a falsy check.

    ``placeholders`` performs ``str.format_map`` substitution. Missing
    keys are tolerated — they remain as literal ``{name}`` markers.
    """

    cat = catalog if catalog is not None else load_catalog()
    norm = normalize_locale(locale) or DEFAULT_LOCALE

    def _lookup(code: str) -> str | None:
        data = cat.get(code) or {}
        strings = data.get("strings") if isinstance(data, Mapping) else None
        if isinstance(strings, Mapping):
            value = strings.get(key)
            if isinstance(value, str):
                return value
        return None

    value = _lookup(norm)
    if value is None and norm != DEFAULT_LOCALE:
        value = _lookup(DEFAULT_LOCALE)
    if value is None:
        value = default if isinstance(default, str) else key

    if placeholders:
        try:
            return value.format_map(_SafeDict(placeholders))
        except Exception:  # noqa: BLE001 — never crash on bad placeholders
            return value
    return value


class _SafeDict(dict):
    """``str.format_map`` helper that leaves unknown placeholders intact."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def iter_strings(
    locale: str,
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> Iterable[tuple[str, str]]:
    """Yield ``(key, value)`` pairs for ``locale``, falling back to default.

    Useful for the ``/api/i18n/strings`` endpoint that hands the
    frontend a single JSON dictionary per locale.
    """

    cat = catalog if catalog is not None else load_catalog()
    norm = normalize_locale(locale) or DEFAULT_LOCALE
    base = cat.get(DEFAULT_LOCALE, {}).get("strings") or {}
    over = cat.get(norm, {}).get("strings") or {}
    merged: dict[str, str] = {}
    if isinstance(base, Mapping):
        for k, v in base.items():
            if isinstance(v, str):
                merged[k] = v
    if isinstance(over, Mapping):
        for k, v in over.items():
            if isinstance(v, str):
                merged[k] = v
    for k in sorted(merged.keys()):
        yield k, merged[k]
