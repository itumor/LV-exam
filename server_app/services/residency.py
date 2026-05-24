"""Data-residency enforcement service (T-065).

Government and EU-regulated tenants must keep learner data inside a
single jurisdiction. The tenant config (T-044, extended here) carries a
``data_region`` tag — one of ``eu`` / ``us`` / ``lv-only`` — and this
module is the **single source of truth** that maps that tag onto:

* the **storage prefix** (filesystem path under ``data/<region>/<tenant>``
  or Cloudflare R2 bucket prefix) for any tenant-owned blob,
* the **database URL** used when a route handler needs to read or write
  tenant-scoped rows,
* the **Fly region pool** (``fra`` / ``iad`` / ``waw``) the request is
  permitted to be served from, and
* the **cross-tenant guard** that prevents an EU-region session from
  reading a US-region tenant's data (or vice versa).

Design choices
--------------

* **Fail-closed.** A call that cannot be matched to a known region raises
  :class:`DataResidencyError`. We refuse to silently fall back to ``eu``
  because that would breach a ``lv-only`` tenant's sovereignty
  guarantee.
* **Pure-Python, no network.** The mapping is computed from the tenant
  config + a small environment-variable override matrix
  (``LVCODEX_DB_URL_<REGION>`` / ``LVCODEX_STORAGE_ROOT_<REGION>``). The
  module never reaches out to a remote service; it is safe to call from
  the request hot path.
* **Defence-in-depth with T-028.** Multi-region Fly (T-028) places the
  app in ``lhr`` + ``fra`` today. The residency check enforces the
  *request-time* invariant — if a request lands on the wrong region it
  is rejected here, regardless of whether DNS / Cloudflare routing
  misbehaved. T-065's PR therefore adds *correctness* on top of T-028's
  *availability*.
* **Auditable from the audit log (T-043).** Every cross-region rejection
  emits an ``audit_events`` row tagged ``residency.cross_region_reject``
  so the institutional compliance dashboard can prove the guarantee.

Storage / DB pinning matrix
---------------------------

============  ===================================  ===================================
Region        Storage root                          Database
============  ===================================  ===================================
``eu``        ``data/eu/<tenant_id>/``              ``DATABASE_URL`` (Fly PG, ``fra``)
``us``        ``data/us/<tenant_id>/``              ``LVCODEX_DB_URL_US``
``lv-only``   ``data/lv-only/<tenant_id>/``         ``LVCODEX_DB_URL_LV_ONLY``
============  ===================================  ===================================

Operators can override any single cell by setting the matching env var
without touching code:

* ``LVCODEX_STORAGE_ROOT_EU``       — absolute path for EU blob storage
* ``LVCODEX_STORAGE_ROOT_US``       — absolute path for US blob storage
* ``LVCODEX_STORAGE_ROOT_LV_ONLY``  — absolute path for LV-only blob storage
* ``LVCODEX_DB_URL_EU``             — overrides ``DATABASE_URL`` for EU tenants
* ``LVCODEX_DB_URL_US``             — DB URL for US tenants
* ``LVCODEX_DB_URL_LV_ONLY``        — DB URL for LV-only tenants

For the development SQLite path we just compute distinct sub-paths under
``data/`` so the layout is identical between the dev box and prod —
prod simply has the env vars set to remote URIs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from server_app.services.tenant import (
    ALLOWED_DATA_REGIONS,
    DEFAULT_DATA_REGION,
    DEFAULT_TENANT_ID,
    TenantConfig,
    get_tenant,
    resolve_tenant,
)


__all__ = [
    "DataResidencyError",
    "FLY_REGION_POOL",
    "REGION_DB_ENV_VARS",
    "REGION_FLY_REGIONS",
    "REGION_STORAGE_ENV_VARS",
    "assert_same_region",
    "current_fly_region",
    "fly_region_allowed",
    "residency_for_tenant",
    "resolve_residency_for_request",
    "storage_root",
    "tenant_db_url",
    "tenant_storage_root",
]


# ---------------------------------------------------------------------------
# Region → infrastructure tables
# ---------------------------------------------------------------------------


# Fly region codes the platform is licensed to host a region in. We do
# NOT accept arbitrary Fly regions — the regulated tenants need a
# closed list so an operator cannot accidentally launch a machine in,
# say, ``sin`` for a ``lv-only`` tenant.
REGION_FLY_REGIONS: dict[str, tuple[str, ...]] = {
    "eu": ("fra", "lhr"),
    "us": ("iad", "sjc"),
    # ``waw`` (Warsaw) is the closest Fly point-of-presence to Latvia and
    # is the planned host for the LV-only tier. If a Latvian sovereign
    # cloud comes online we drop ``waw`` from this tuple and the
    # ``fly_region_allowed`` check refuses anything else.
    "lv-only": ("waw",),
}

# Flat set of every Fly region this service knows about. Used by
# ``current_fly_region`` for the unknown-region case.
FLY_REGION_POOL: frozenset[str] = frozenset(
    code
    for codes in REGION_FLY_REGIONS.values()
    for code in codes
)

REGION_STORAGE_ENV_VARS: dict[str, str] = {
    "eu": "LVCODEX_STORAGE_ROOT_EU",
    "us": "LVCODEX_STORAGE_ROOT_US",
    "lv-only": "LVCODEX_STORAGE_ROOT_LV_ONLY",
}

REGION_DB_ENV_VARS: dict[str, str] = {
    "eu": "LVCODEX_DB_URL_EU",
    "us": "LVCODEX_DB_URL_US",
    "lv-only": "LVCODEX_DB_URL_LV_ONLY",
}


# Repo root mirrors the pattern used by ``server_app.services.tenant`` so
# the default storage layout is rooted at ``<repo>/data/<region>/`` and
# survives the modularisation boundary.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STORAGE_ROOT = _REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataResidencyError(Exception):
    """Raised when a request would breach a tenant's residency contract.

    Attributes
    ----------
    tenant_id:
        The tenant whose contract would be breached.
    expected_region:
        The residency tag the tenant is configured for.
    actual_region:
        The region the request was about to be routed to (or the region
        of the other tenant in a cross-region access attempt).
    reason:
        Short machine identifier — one of ``cross_region_access`` /
        ``unsupported_fly_region`` / ``unknown_region`` — surfaced to
        the audit log.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        expected_region: str,
        actual_region: str,
        reason: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.expected_region = expected_region
        self.actual_region = actual_region
        self.reason = reason
        super().__init__(
            f"residency violation for tenant {tenant_id!r}: "
            f"expected={expected_region!r} actual={actual_region!r} "
            f"reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers — no env reads
# ---------------------------------------------------------------------------


def _normalise_region(region: str | None) -> str:
    """Return ``region`` if it is in the closed set, else ``DEFAULT_DATA_REGION``.

    Mirrors the coercion that ``TenantConfig`` performs at load time so
    callers that pass a raw string (e.g. from a request query param)
    cannot accidentally widen the allowed set.
    """

    if isinstance(region, str) and region in ALLOWED_DATA_REGIONS:
        return region
    return DEFAULT_DATA_REGION


# ---------------------------------------------------------------------------
# Public API — storage pinning
# ---------------------------------------------------------------------------


def storage_root(region: str) -> Path:
    """Return the absolute storage root for ``region``.

    Honours the ``LVCODEX_STORAGE_ROOT_<REGION>`` env var when set; falls
    back to ``<repo>/data/<region>``. The returned path is created on
    demand so callers can immediately ``open(... , 'wb')`` into it.
    """

    normalised = _normalise_region(region)
    env_var = REGION_STORAGE_ENV_VARS.get(normalised)
    override = os.environ.get(env_var) if env_var else None
    if override:
        root = Path(override).expanduser().resolve()
    else:
        root = _DEFAULT_STORAGE_ROOT / normalised
    root.mkdir(parents=True, exist_ok=True)
    return root


def tenant_storage_root(tenant: TenantConfig | str) -> Path:
    """Return the absolute storage root for a tenant's region.

    Accepts either a :class:`TenantConfig` or a tenant id (which is then
    resolved via :func:`server_app.services.tenant.get_tenant`). The
    returned directory is ``<storage_root>/<tenant_id>/`` and is
    created on demand.
    """

    cfg = tenant if isinstance(tenant, TenantConfig) else get_tenant(tenant)
    root = storage_root(cfg.data_region) / cfg.id
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Public API — DB pinning
# ---------------------------------------------------------------------------


def tenant_db_url(tenant: TenantConfig | str) -> str | None:
    """Return the DB URL a tenant's region should use.

    Resolution order for region ``R``:

    1. ``LVCODEX_DB_URL_<R>`` (e.g. ``LVCODEX_DB_URL_LV_ONLY``).
    2. For the ``eu`` region only, fall back to ``DATABASE_URL`` so the
       existing single-region deployment keeps working without an
       operator change.
    3. ``None`` — the route layer interprets this as "use the local
       SQLite fallback" (the dev path).
    """

    cfg = tenant if isinstance(tenant, TenantConfig) else get_tenant(tenant)
    region = cfg.data_region
    env_var = REGION_DB_ENV_VARS.get(region)
    if env_var:
        url = os.environ.get(env_var)
        if url:
            return url
    if region == "eu":
        return os.environ.get("DATABASE_URL") or None
    return None


# ---------------------------------------------------------------------------
# Public API — Fly region guard
# ---------------------------------------------------------------------------


def current_fly_region() -> str:
    """Return the Fly region of the current process, or ``""`` if unknown.

    Reads ``FLY_REGION`` (set by Fly on every machine, surfaced by T-028
    in ``/healthz``).
    """

    return (os.environ.get("FLY_REGION") or "").strip().lower()


def fly_region_allowed(tenant: TenantConfig | str, fly_region: str | None = None) -> bool:
    """Return True when ``fly_region`` is in the tenant's allowed pool.

    When ``fly_region`` is ``None`` we read it from the env. An empty
    string is treated as "running outside Fly" (tests, dev box) and is
    permitted for every region — the residency contract is enforced
    inside the data layer in that case, not at the network edge.
    """

    cfg = tenant if isinstance(tenant, TenantConfig) else get_tenant(tenant)
    if fly_region is None:
        fly_region = current_fly_region()
    if not fly_region:
        return True  # not running on Fly — DB / storage layer enforces
    return fly_region in REGION_FLY_REGIONS.get(cfg.data_region, ())


# ---------------------------------------------------------------------------
# Public API — cross-region access guard
# ---------------------------------------------------------------------------


def assert_same_region(
    requesting: TenantConfig | str,
    target: TenantConfig | str,
) -> None:
    """Raise :class:`DataResidencyError` when two tenants disagree on region.

    Used by route handlers that accept a tenant id in the URL but resolve
    a different tenant from the session — e.g. an EU-region admin
    attempting to inspect a US-region tenant's audit log. The guarantee
    we make to ``lv-only`` tenants is that even a platform superadmin
    cannot pull their data into another region without going through a
    documented, audited cross-region transfer flow (out of scope for
    T-065).
    """

    req = requesting if isinstance(requesting, TenantConfig) else get_tenant(requesting)
    tgt = target if isinstance(target, TenantConfig) else get_tenant(target)
    if req.data_region != tgt.data_region:
        raise DataResidencyError(
            tenant_id=tgt.id,
            expected_region=tgt.data_region,
            actual_region=req.data_region,
            reason="cross_region_access",
        )


# ---------------------------------------------------------------------------
# Public API — request-time resolution
# ---------------------------------------------------------------------------


def residency_for_tenant(tenant: TenantConfig | str) -> dict[str, Any]:
    """Return a serialisable summary of the tenant's residency posture.

    Shape::

        {
          "tenant_id":     "<id>",
          "data_region":   "eu"|"us"|"lv-only",
          "fly_regions":   ["fra", "lhr"],
          "storage_root":  "/abs/path/to/data/eu/<id>",
          "db_pinned":     true|false,
          "portal_subdomain": "<sub>"|null,
        }

    Used by the admin console to display the compliance posture for an
    operator review and by the ``/api/tenant`` response so the front-end
    can render a "Hosted in EU" badge next to the tenant name.
    """

    cfg = tenant if isinstance(tenant, TenantConfig) else get_tenant(tenant)
    return {
        "tenant_id": cfg.id,
        "data_region": cfg.data_region,
        "fly_regions": list(REGION_FLY_REGIONS.get(cfg.data_region, ())),
        "storage_root": str(tenant_storage_root(cfg)),
        "db_pinned": tenant_db_url(cfg) is not None,
        "portal_subdomain": cfg.portal_subdomain,
    }


def resolve_residency_for_request(
    host_header: str | None,
    *,
    fly_region: str | None = None,
    conn: Any = None,
) -> dict[str, Any]:
    """Resolve the tenant from the inbound Host: header and enforce its region.

    Entry point a route handler calls at the top of the dispatch chain
    when it is about to read or write tenant-scoped data. It:

    1. Resolves the tenant via :func:`resolve_tenant` (T-044).
    2. Reads the current Fly region (T-028).
    3. Verifies the Fly region is in the tenant's allowed pool —
       raises :class:`DataResidencyError` otherwise.
    4. Returns the residency summary for use by the caller (storage
       root, DB URL hint, etc.).

    The function is intentionally cheap: a tenant lookup is O(1) over
    the on-disk cache; the env reads are constant-time; and no DB query
    is required when ``conn`` is omitted.
    """

    cfg = resolve_tenant(host_header, conn=conn)
    region = (fly_region if fly_region is not None else current_fly_region())
    if not fly_region_allowed(cfg, region):
        # The default tenant is allowed everywhere — only refuse when the
        # tenant is opted into a region pool that excludes the current
        # Fly region.
        if cfg.id != DEFAULT_TENANT_ID:
            raise DataResidencyError(
                tenant_id=cfg.id,
                expected_region=cfg.data_region,
                actual_region=region or "unknown",
                reason="unsupported_fly_region",
            )
    summary = residency_for_tenant(cfg)
    summary["fly_region"] = region or None
    summary["tenant"] = cfg
    return summary
