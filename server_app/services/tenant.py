"""White-label tenant resolution service (T-044).

Provides three pieces of functionality:

1. Load tenant config files from ``tenants/<id>.json`` on disk.
2. Resolve an inbound ``Host:`` header to a tenant config — first via the
   ``custom_domains`` mapping table (sqlite + postgres), then via the
   ``host_aliases`` field in each tenant JSON, finally falling back to
   the ``default`` tenant (``tenants/example.json``).
3. Render the tenant's brand palette as a small CSS-variable block that
   the v2 frontend (``apps/web-v2``) injects into the document so the
   primary colour, surface tones, logo URL, and font choices switch
   on a per-domain basis.

Design choices
--------------

* **File-on-disk config, not DB.** Tenant theme JSON is checked into git
  under ``tenants/`` so a reviewer can spot a malicious palette change in
  a PR. Operators add a new tenant by dropping a JSON file and (for a
  custom domain) inserting a row in ``custom_domains``.
* **One table, one purpose.** ``custom_domains`` is intentionally just
  ``(host, tenant_id)`` — it does not duplicate the theme. This keeps PR
  review focused on which host belongs to which tenant.
* **Read-only at request time.** ``resolve_tenant`` never writes to the
  DB; it reads. Inserts happen via the admin-only ``register_custom_domain``
  helper used by the institutional onboarding flow (T-041) and by tests.
* **Defensive fallback.** Any error — missing config file, malformed JSON,
  DB outage — degrades to the default tenant rather than 500-ing the
  request. Branding is a presentation concern; learners must keep being
  able to log in.

This module is intentionally small and import-light so it can be wired
into the request hot path without measurable overhead.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

__all__ = [
    "ALLOWED_DATA_REGIONS",
    "DEFAULT_DATA_REGION",
    "DEFAULT_TENANT_ID",
    "TENANT_DIR",
    "TenantConfig",
    "build_css_variables",
    "get_tenant",
    "init_custom_domains_table",
    "list_tenants",
    "load_tenant_file",
    "register_custom_domain",
    "remove_custom_domain",
    "resolve_tenant",
    "resolve_tenant_by_subdomain",
    "tenant_to_dict",
]


# Repository root: server_app/services/tenant.py -> server_app/services
# -> server_app -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
TENANT_DIR = _REPO_ROOT / "tenants"

DEFAULT_TENANT_ID = "default"

# A tenant id must be safe for use in URLs, filenames, and CSS class
# names. Lowercase letters, digits, hyphens, max 64 chars. This matches
# the slug pattern used by the institutional licensing flow (T-041).
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# A primary_color value must be a CSS hex colour (#rgb / #rrggbb /
# #rrggbbaa). We deliberately do not accept named colours or rgb() —
# the v2 stylesheet needs a single canonical form to mix into the
# accent shades.
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# Fallback palette — must match apps/web-v2/src/styles.css so that the
# default tenant config and the bundled stylesheet stay in sync if the
# JSON file is ever missing.
_DEFAULT_PALETTE: dict[str, str] = {
    "primary_color": "#38bdf8",
    "secondary_color": "#0ea5e9",
    "background_color": "#0f172a",
    "text_color": "#f1f5f9",
}


# ---------------------------------------------------------------------------
# T-065 — Data residency + portal subdomain
# ---------------------------------------------------------------------------
#
# Data-residency tags. The set is intentionally small and closed:
#
# * ``eu``       — EU/EEA region pool. Default for commercial tenants.
#                  Storage + DB pinned to ``fra`` (Fly Frankfurt) per the
#                  multi-region runbook (``docs/multi-region.md``).
# * ``us``       — US region pool. Reserved for North-American
#                  white-label deployments. Storage pinned to ``iad`` /
#                  Cloudflare R2 ``ENAM`` jurisdiction.
# * ``lv-only``  — Latvia-only government tier. Storage + DB pinned to
#                  ``waw`` / on-prem Latvian operator with a DPA in
#                  place. No cross-border replication is allowed.
#
# Any tenant JSON that declares a value outside this set is coerced to
# ``eu`` (the safe public-cloud default) at load time. The enforcement
# helper that PINS storage + DB selection per tenant lives in
# :mod:`server_app.services.residency` and is what callers should go
# through whenever they need to read or write tenant data.

ALLOWED_DATA_REGIONS: frozenset[str] = frozenset({"eu", "us", "lv-only"})
DEFAULT_DATA_REGION: str = "eu"

# A portal_subdomain value must be a DNS-safe label (RFC 1123): letters,
# digits, hyphens; 1-63 chars; cannot start or end with a hyphen. The
# server needs a single canonical form because it renders the subdomain
# back into a fully-qualified host without ambiguity.
_PORTAL_SUBDOMAIN_RE = re.compile(
    r"^(?!-)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


# ---------------------------------------------------------------------------
# Config dataclass (lightweight — no pydantic to keep import budget tiny)
# ---------------------------------------------------------------------------


class TenantConfig:
    """In-memory representation of a tenant's theme + identity.

    Constructed by :func:`load_tenant_file`. Attribute access is the
    public surface — the route layer reads ``primary_color``,
    ``logo_url``, etc., directly.
    """

    __slots__ = (
        "id",
        "name",
        "primary_color",
        "secondary_color",
        "background_color",
        "text_color",
        "logo_url",
        "favicon_url",
        "support_email",
        "custom_domain",
        "host_aliases",
        "data_region",
        "portal_subdomain",
    )

    def __init__(
        self,
        *,
        id: str,
        name: str,
        primary_color: str,
        secondary_color: str | None = None,
        background_color: str | None = None,
        text_color: str | None = None,
        logo_url: str | None = None,
        favicon_url: str | None = None,
        support_email: str | None = None,
        custom_domain: str | None = None,
        host_aliases: list[str] | None = None,
        data_region: str | None = None,
        portal_subdomain: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.primary_color = primary_color
        self.secondary_color = secondary_color or _DEFAULT_PALETTE["secondary_color"]
        self.background_color = background_color or _DEFAULT_PALETTE["background_color"]
        self.text_color = text_color or _DEFAULT_PALETTE["text_color"]
        self.logo_url = logo_url
        self.favicon_url = favicon_url
        self.support_email = support_email
        self.custom_domain = custom_domain
        self.host_aliases = list(host_aliases or [])
        # T-065 — residency tag is closed-set. Unknown / missing values
        # collapse to ``eu`` (safe public-cloud default). We never coerce
        # to ``lv-only`` because that would be a fail-OPEN posture (the
        # gov tier must be opted into explicitly via the tenant JSON).
        if isinstance(data_region, str) and data_region in ALLOWED_DATA_REGIONS:
            self.data_region = data_region
        else:
            self.data_region = DEFAULT_DATA_REGION
        # T-065 — portal subdomain is optional. Validation happens at
        # load time, so an unset / malformed value lands here as ``None``.
        self.portal_subdomain = portal_subdomain

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"TenantConfig(id={self.id!r}, name={self.name!r}, "
            f"primary_color={self.primary_color!r})"
        )


def tenant_to_dict(tenant: TenantConfig) -> dict[str, Any]:
    """Serialise a :class:`TenantConfig` for the JSON response.

    Kept separate from a hypothetical ``__dict__`` so the wire format is
    decoupled from the in-memory slot names and so future fields can be
    added without breaking older clients.
    """

    return {
        "id": tenant.id,
        "name": tenant.name,
        "primary_color": tenant.primary_color,
        "secondary_color": tenant.secondary_color,
        "background_color": tenant.background_color,
        "text_color": tenant.text_color,
        "logo_url": tenant.logo_url,
        "favicon_url": tenant.favicon_url,
        "support_email": tenant.support_email,
        "custom_domain": tenant.custom_domain,
        "host_aliases": list(tenant.host_aliases),
        "data_region": tenant.data_region,
        "portal_subdomain": tenant.portal_subdomain,
        "css_variables": build_css_variables(tenant),
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_valid_tenant_id(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_TENANT_ID_RE.match(value))


def _is_valid_hex_color(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_HEX_COLOR_RE.match(value))


def _coerce_color(value: Any, fallback: str) -> str:
    if isinstance(value, str) and _is_valid_hex_color(value):
        return value
    return fallback


def _is_valid_portal_subdomain(value: str | None) -> bool:
    """Return True when ``value`` is a DNS-safe single-label subdomain.

    The check is intentionally strict: the subdomain is used to build a
    canonical fully-qualified host (``<sub>.lvcodex.com`` by default) and
    we never want a tenant config to inject extra dots or unusual
    characters that would land traffic on a parent domain.
    """

    if not isinstance(value, str):
        return False
    return bool(_PORTAL_SUBDOMAIN_RE.match(value.strip().lower()))


def _coerce_portal_subdomain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if not _is_valid_portal_subdomain(candidate):
        return None
    return candidate


def _coerce_data_region(value: Any) -> str:
    if isinstance(value, str) and value in ALLOWED_DATA_REGIONS:
        return value
    return DEFAULT_DATA_REGION


def _normalise_host(host: str | None) -> str:
    """Strip the optional ``:port`` suffix and lower-case the host.

    The wire format of an HTTP ``Host`` header is ``host[:port]`` and the
    casing is not significant per RFC 7230 §5.4. We normalise both away
    so a custom-domain lookup behaves the same whether the client sent
    ``Acme.example.com:443`` or ``acme.example.com``.
    """

    if not host:
        return ""
    raw = host.strip()
    if not raw:
        return ""
    # Strip ``:port`` — but be defensive about IPv6 literals which embed
    # colons inside ``[...]``. We just split on the rightmost ``:`` when
    # the trailing chunk is all digits.
    if "]" not in raw and ":" in raw:
        host_part, _, port_part = raw.rpartition(":")
        if port_part.isdigit():
            raw = host_part
    return raw.lower()


# ---------------------------------------------------------------------------
# Loading tenant config from disk
# ---------------------------------------------------------------------------


# Process-wide cache of (path, mtime_ns) → TenantConfig. The values are
# immutable enough that we don't bother with a TTL — the file mtime
# already invalidates stale entries.
_TENANT_CACHE: dict[str, tuple[float, TenantConfig]] = {}
_TENANT_CACHE_LOCK = Lock()


def _tenant_file_path(tenant_id: str) -> Path:
    if not _is_valid_tenant_id(tenant_id):
        # The default tenant is allowed as a special-case literal; any
        # other invalid id is a programmer error.
        if tenant_id == DEFAULT_TENANT_ID:
            return TENANT_DIR / "example.json"
        raise ValueError(f"invalid tenant id: {tenant_id!r}")
    if tenant_id == DEFAULT_TENANT_ID:
        return TENANT_DIR / "example.json"
    return TENANT_DIR / f"{tenant_id}.json"


def load_tenant_file(tenant_id: str) -> TenantConfig | None:
    """Load and validate a tenant JSON file by id.

    Returns ``None`` when the file does not exist OR when the JSON is
    malformed — never raises on bad input, because branding must
    degrade gracefully to the default theme.
    """

    try:
        path = _tenant_file_path(tenant_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        stat = path.stat()
    except OSError:
        return None

    cache_key = str(path)
    cached = _TENANT_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat.st_mtime:
        return cached[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    file_id = raw.get("id")
    # The on-disk id must match the filename to prevent confusing
    # situations where ``tenants/acme.json`` declares ``"id": "globex"``.
    expected_id = DEFAULT_TENANT_ID if tenant_id == DEFAULT_TENANT_ID else tenant_id
    if file_id != expected_id:
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    primary = _coerce_color(raw.get("primary_color"), _DEFAULT_PALETTE["primary_color"])

    aliases_raw = raw.get("host_aliases") or []
    if not isinstance(aliases_raw, list):
        aliases_raw = []
    aliases = [_normalise_host(str(h)) for h in aliases_raw if isinstance(h, str)]
    aliases = [h for h in aliases if h]

    config = TenantConfig(
        id=str(file_id),
        name=name.strip(),
        primary_color=primary,
        secondary_color=_coerce_color(
            raw.get("secondary_color"), _DEFAULT_PALETTE["secondary_color"]
        ),
        background_color=_coerce_color(
            raw.get("background_color"), _DEFAULT_PALETTE["background_color"]
        ),
        text_color=_coerce_color(
            raw.get("text_color"), _DEFAULT_PALETTE["text_color"]
        ),
        logo_url=_as_str_or_none(raw.get("logo_url")),
        favicon_url=_as_str_or_none(raw.get("favicon_url")),
        support_email=_as_str_or_none(raw.get("support_email")),
        custom_domain=_as_str_or_none(raw.get("custom_domain")),
        host_aliases=aliases,
        data_region=_coerce_data_region(raw.get("data_region")),
        portal_subdomain=_coerce_portal_subdomain(raw.get("portal_subdomain")),
    )

    with _TENANT_CACHE_LOCK:
        _TENANT_CACHE[cache_key] = (stat.st_mtime, config)
    return config


def _as_str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _default_tenant() -> TenantConfig:
    config = load_tenant_file(DEFAULT_TENANT_ID)
    if config is not None:
        return config
    # Last-ditch fallback if tenants/example.json is missing.
    return TenantConfig(
        id=DEFAULT_TENANT_ID,
        name="lvcodex",
        primary_color=_DEFAULT_PALETTE["primary_color"],
        secondary_color=_DEFAULT_PALETTE["secondary_color"],
        background_color=_DEFAULT_PALETTE["background_color"],
        text_color=_DEFAULT_PALETTE["text_color"],
    )


def get_tenant(tenant_id: str) -> TenantConfig:
    """Return the named tenant or the default when missing/invalid."""

    config = load_tenant_file(tenant_id)
    if config is None:
        return _default_tenant()
    return config


def list_tenants() -> list[TenantConfig]:
    """Return every tenant config currently on disk under ``tenants/``.

    Used by the admin console to show the white-label catalogue and by
    the smoke test that asserts the bundled examples parse cleanly.
    """

    out: list[TenantConfig] = []
    if not TENANT_DIR.is_dir():
        return out
    seen: set[str] = set()
    for path in sorted(TENANT_DIR.iterdir()):
        if path.suffix.lower() != ".json":
            continue
        # ``tenants/example.json`` represents the default tenant.
        if path.name == "example.json":
            cfg = load_tenant_file(DEFAULT_TENANT_ID)
        else:
            cfg = load_tenant_file(path.stem)
        if cfg is None or cfg.id in seen:
            continue
        seen.add(cfg.id)
        out.append(cfg)
    return out


# ---------------------------------------------------------------------------
# custom_domains table (sqlite + pg)
# ---------------------------------------------------------------------------


_CREATE_TABLE_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS custom_domains (
    host TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL_SQLITE = (
    "CREATE INDEX IF NOT EXISTS idx_custom_domains_tenant "
    "ON custom_domains (tenant_id)"
)


def init_custom_domains_table(conn: sqlite3.Connection) -> None:
    """Create the ``custom_domains`` table on first use.

    Idempotent. The Postgres mirror lives in
    ``migrations/postgres/004_custom_domains.sql`` and is applied by the
    standard ``apply_postgres_migrations`` runner — this helper is the
    SQLite-side equivalent so the test harness does not need to invoke
    the migration runner.
    """

    conn.execute(_CREATE_TABLE_SQL_SQLITE)
    conn.execute(_CREATE_INDEX_SQL_SQLITE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def register_custom_domain(
    conn: sqlite3.Connection,
    host: str,
    tenant_id: str,
    *,
    verified: bool = False,
) -> dict[str, Any]:
    """Insert or update a host → tenant assignment.

    Hosts are stored in lower-case, port-stripped form so lookups during
    request handling can use the same normalisation. The function does
    not validate that ``tenant_id`` resolves to an on-disk config — that
    decoupling lets operators stage a domain ahead of uploading the
    tenant JSON.
    """

    init_custom_domains_table(conn)
    normalised = _normalise_host(host)
    if not normalised:
        raise ValueError("host must be a non-empty string")
    if not _is_valid_tenant_id(tenant_id) and tenant_id != DEFAULT_TENANT_ID:
        raise ValueError(f"invalid tenant id: {tenant_id!r}")
    now = _now_iso()
    verified_int = 1 if verified else 0
    existing = conn.execute(
        "SELECT host FROM custom_domains WHERE host = ?", (normalised,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO custom_domains "
            "(host, tenant_id, verified, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (normalised, tenant_id, verified_int, now, now),
        )
    else:
        conn.execute(
            "UPDATE custom_domains SET tenant_id = ?, verified = ?, updated_at = ? "
            "WHERE host = ?",
            (tenant_id, verified_int, now, normalised),
        )
    return {
        "host": normalised,
        "tenant_id": tenant_id,
        "verified": bool(verified_int),
    }


def remove_custom_domain(conn: sqlite3.Connection, host: str) -> bool:
    """Delete a host → tenant row; returns True if a row was removed."""

    init_custom_domains_table(conn)
    normalised = _normalise_host(host)
    if not normalised:
        return False
    cursor = conn.execute(
        "DELETE FROM custom_domains WHERE host = ?", (normalised,)
    )
    return cursor.rowcount > 0


def _lookup_tenant_id_in_db(conn: sqlite3.Connection, host: str) -> str | None:
    """Return the tenant id mapped to ``host`` in ``custom_domains``.

    Returns ``None`` when the host is unmapped OR the table does not yet
    exist (the lazy-init path is best-effort: a missing table on a fresh
    DB must not block the request, it just falls through to host-alias
    matching and finally to the default tenant).
    """

    try:
        init_custom_domains_table(conn)
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(
            "SELECT tenant_id FROM custom_domains WHERE host = ?", (host,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return str(row["tenant_id"]) if "tenant_id" in row.keys() else str(row[0])


# ---------------------------------------------------------------------------
# Public resolve_tenant API
# ---------------------------------------------------------------------------


def resolve_tenant(
    host_header: str | None,
    *,
    conn: sqlite3.Connection | None = None,
) -> TenantConfig:
    """Return the tenant config for the given ``Host:`` header.

    Resolution order:

    1. **Per-process override.** If ``LVCODEX_FORCE_TENANT`` is set to a
       valid tenant id, that tenant is always returned. Used by the
       admin console previewer and by smoke tests.
    2. **Custom-domain table.** Exact match on the lower-cased,
       port-stripped host. Only honoured when ``conn`` is provided
       (route handlers pass a real connection; library callers that just
       want the default behaviour can omit it).
    3. **host_aliases in tenant JSON.** Linear scan over the bundled
       tenant files. The default tenant's aliases are checked LAST so a
       sample tenant can claim ``localhost`` for local previews.
    4. **Fallback to default.** Returns ``tenants/example.json`` so the
       UI always has *some* palette to render.
    """

    forced = os.getenv("LVCODEX_FORCE_TENANT")
    if forced and _is_valid_tenant_id(forced):
        forced_cfg = load_tenant_file(forced)
        if forced_cfg is not None:
            return forced_cfg

    host = _normalise_host(host_header)

    # Step 2 — custom_domains lookup.
    if conn is not None and host:
        tenant_id = _lookup_tenant_id_in_db(conn, host)
        if tenant_id:
            cfg = load_tenant_file(tenant_id)
            if cfg is not None:
                return cfg

    # Step 3 — host_aliases. Walk every tenant on disk EXCEPT the
    # default first, so a non-default tenant that opted into ``localhost``
    # wins. The default tenant is checked at the very end.
    if host:
        non_default: list[TenantConfig] = []
        default_cfg: TenantConfig | None = None
        for cfg in list_tenants():
            if cfg.id == DEFAULT_TENANT_ID:
                default_cfg = cfg
                continue
            non_default.append(cfg)
        for cfg in non_default:
            if host in cfg.host_aliases or host == _normalise_host(cfg.custom_domain or ""):
                return cfg
        # T-065 — branded portal subdomain resolution. A tenant that
        # declares ``portal_subdomain: gov-lv`` claims every host of the
        # form ``gov-lv.<parent>`` where ``<parent>`` is one of the
        # default tenant's host aliases (the platform's base domain).
        # Checked AFTER explicit host_aliases / custom_domain so
        # operators can override the subdomain mapping with an explicit
        # entry, but BEFORE the default fallback so the branded portal
        # route works without an operator action.
        sub_match = _match_portal_subdomain(host, non_default, default_cfg)
        if sub_match is not None:
            return sub_match
        if default_cfg is not None and host in default_cfg.host_aliases:
            return default_cfg

    # Step 4 — default.
    return _default_tenant()


def _match_portal_subdomain(
    host: str,
    non_default: list["TenantConfig"],
    default_cfg: "TenantConfig | None",
) -> "TenantConfig | None":
    """Resolve a tenant via its declared ``portal_subdomain``.

    Algorithm: take the inbound host, split it on the first dot, and
    treat the left-most label as a candidate portal subdomain. If any
    non-default tenant declares that exact subdomain AND the right-hand
    parent host appears in the default tenant's host_aliases (the
    platform's base domain — ``lvcodex.com``, ``localhost``, etc.), the
    tenant wins.

    Returns ``None`` when no tenant matches; the caller then continues
    with the default-alias check + default fallback.
    """

    if "." not in host:
        return None
    sublabel, _, parent = host.partition(".")
    if not sublabel or not parent:
        return None
    if default_cfg is None:
        # Without the default tenant we cannot decide what a "platform"
        # domain even is, so we don't attempt the match.
        return None
    parent_ok = (
        parent in default_cfg.host_aliases
        or parent == _normalise_host(default_cfg.custom_domain or "")
    )
    if not parent_ok:
        return None
    for cfg in non_default:
        if cfg.portal_subdomain and cfg.portal_subdomain == sublabel:
            return cfg
    return None


def resolve_tenant_by_subdomain(subdomain: str | None) -> TenantConfig | None:
    """Look up a tenant by its declared ``portal_subdomain`` value.

    Returns ``None`` when no tenant claims that subdomain. The default
    tenant is never returned from this helper — by definition it does
    not have a branded subdomain. Used by the admin previewer and by
    onboarding tooling that needs to test a portal URL before DNS is
    cut over.
    """

    candidate = _coerce_portal_subdomain(subdomain)
    if candidate is None:
        return None
    for cfg in list_tenants():
        if cfg.id == DEFAULT_TENANT_ID:
            continue
        if cfg.portal_subdomain == candidate:
            return cfg
    return None


# ---------------------------------------------------------------------------
# CSS variable rendering
# ---------------------------------------------------------------------------


def build_css_variables(tenant: TenantConfig) -> dict[str, str]:
    """Return the CSS-custom-property names + values for a tenant.

    The keys mirror the variables declared in
    ``apps/web-v2/src/styles.css`` so the frontend can apply them to
    ``document.documentElement.style`` without any name remapping. The
    intent is that the v2 SPA fetches ``/api/tenant`` on boot, applies
    every entry from ``css_variables`` via ``setProperty``, and the rest
    of the stylesheet "just works".
    """

    return {
        "--color-accent": tenant.primary_color,
        "--color-accent-hover": tenant.secondary_color,
        "--color-bg": tenant.background_color,
        "--color-text": tenant.text_color,
        "--tenant-id": tenant.id,
        "--tenant-name": tenant.name,
    }
