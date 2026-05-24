# Data residency & government-tier compliance posture (T-065)

Status: **planning** — service code, tenant config, and tests are merged
ahead of the first government tenant onboarding. No `lv-only` machines
have been provisioned in `waw` yet; that work happens in the operator
runbook hand-off once the Latvian DPA (Data Processing Agreement) is
counter-signed.

This document is the **operator + auditor reference** for:

1. What residency guarantees lvcodex makes to a tenant.
2. How those guarantees are enforced at the request hot path.
3. How an auditor can verify the guarantees from primary sources
   (tenant JSON, env vars, audit log).
4. Failure modes and the corresponding rollback procedure.

> See also: `docs/multi-region.md` (T-028 Fly warm-standby runbook),
> `docs/architecture.md` (overall service topology), and
> `server_app/services/residency.py` (the enforcement code reviewed
> below).

## 1. Tenant residency contract

Every tenant config (`tenants/<id>.json`) declares a `data_region` tag.
The set is closed:

| Tag         | Audience                             | Fly regions  | Storage                              | Database                                  |
| ----------- | ------------------------------------ | ------------ | ------------------------------------ | ----------------------------------------- |
| `eu`        | Default — EU/EEA commercial tenants  | `fra`, `lhr` | `data/eu/<tenant>/` (or R2 EU)       | `DATABASE_URL` (Fly PG, `fra`)            |
| `us`        | North-American white-label tenants   | `iad`, `sjc` | `data/us/<tenant>/` (or R2 ENAM)     | `LVCODEX_DB_URL_US`                       |
| `lv-only`   | Latvian government tier (T-065)      | `waw`        | `data/lv-only/<tenant>/`             | `LVCODEX_DB_URL_LV_ONLY`                  |

A tenant cannot opt into more than one tag and the platform must not
silently widen the set. Adding a new region requires a code change to
`server_app/services/tenant.py::ALLOWED_DATA_REGIONS` and a fresh PR
review — there is no run-time admin path that grants this.

### What "residency" means in practice

For a tenant configured with `data_region: lv-only`, lvcodex guarantees:

1. **Storage isolation.** All filesystem blobs and object-store keys
   live under the `lv-only/<tenant_id>/` prefix. No cross-region
   replication is configured for that prefix.
2. **DB isolation.** Reads + writes to tenant-scoped rows go through
   `LVCODEX_DB_URL_LV_ONLY`. The fallback chain stops there — we never
   silently inherit `DATABASE_URL` (which points at `fra`), even if the
   pinned URL is empty (the route handler will surface an error rather
   than degrade).
3. **Request routing.** A request that resolves to an `lv-only` tenant
   must be served from a Fly machine in `waw`. The
   `resolve_residency_for_request` helper raises `DataResidencyError`
   when the current `FLY_REGION` is not in the tenant's allowed pool
   and the route layer translates that into HTTP 502 with an audit-log
   entry tagged `residency.cross_region_reject`.
4. **No cross-tenant pivots.** A platform superadmin operating from
   the EU console cannot access an `lv-only` tenant's data without
   going through a separate, audited cross-region transfer flow (which
   is intentionally **not** part of T-065 — it requires a counter-signed
   DPA per export and is tracked in a separate roadmap item).

For a tenant configured with `data_region: eu` (the default), all four
guarantees hold within the EU region pool. Commercial tenants do not
need a DPA signed for routine operations.

## 2. Enforcement architecture

### 2.1 Tenant config

Tenant JSON files in `tenants/<id>.json` are checked into git, so an
auditor can read the residency tag from the source of truth:

```json
{
  "id": "gov-lv",
  "name": "Latvijas Valdības Eksāmenu Portāls",
  "data_region": "lv-only",
  "portal_subdomain": "gov-lv",
  "custom_domain": "eksameni.valoda.gov.lv",
  ...
}
```

The `TenantConfig` constructor coerces an unknown `data_region` to
`eu` — a fail-CLOSED choice. We never collapse to `lv-only` so a typo
in a non-government tenant's JSON cannot accidentally pull that tenant
into the regulated tier.

### 2.2 Residency service (`server_app/services/residency.py`)

This module is the single chokepoint that maps a tenant's tag onto the
infrastructure to use. The public API surface is intentionally small:

| Symbol                              | Purpose                                                                                                                |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `storage_root(region)`              | Absolute filesystem root for blob storage in a region, honouring `LVCODEX_STORAGE_ROOT_<REGION>` env overrides.        |
| `tenant_storage_root(tenant)`       | `<storage_root>/<tenant_id>/` — created on demand. Use this for every tenant-scoped write.                              |
| `tenant_db_url(tenant)`             | The DB URL a tenant's region should use. Returns `None` only for non-EU tenants whose pinned URL is unset.              |
| `fly_region_allowed(tenant, region)`| True when the current Fly region is in the tenant's allowed pool. Permissive when `FLY_REGION` is unset (dev / tests). |
| `assert_same_region(req, target)`   | Raises `DataResidencyError` if two tenants disagree on region. Use whenever a session crosses tenant boundaries.       |
| `resolve_residency_for_request(...)`| Resolve a tenant via `Host:` header (T-044) and enforce the Fly-region guard in one call.                              |

### 2.3 Branded portal subdomain

Each tenant may optionally declare a `portal_subdomain`. When set, the
tenant claims every host of the form `<subdomain>.<parent>` where
`<parent>` is a host alias of the default tenant. Examples:

* `gov-lv.lvcodex.com` -> resolves to `gov-lv` tenant.
* `acme.localhost` -> resolves to `acme-school` tenant (local preview).
* `gov-lv.evil.example` -> **does not** resolve to `gov-lv` (parent is
  not a platform host); falls through to the default tenant.

The subdomain rule runs AFTER explicit `host_aliases` / `custom_domain`
in the resolution chain so operators can override the auto-mapping
with an explicit entry. The DNS-label regex is strict
(RFC 1123, lower-cased, 1-63 chars) so a tenant config cannot inject
extra dots that would steer traffic to a parent domain.

### 2.4 Configuration matrix

Operators control the per-region targets without touching code by
setting the following env vars on the Fly application:

```
LVCODEX_STORAGE_ROOT_EU=/data/eu          # or R2 mount point
LVCODEX_STORAGE_ROOT_US=/data/us
LVCODEX_STORAGE_ROOT_LV_ONLY=/data/lv-only

LVCODEX_DB_URL_EU=postgres://...fra...    # optional override; default = DATABASE_URL
LVCODEX_DB_URL_US=postgres://...iad...
LVCODEX_DB_URL_LV_ONLY=postgres://...lv... # MUST be set before onboarding the first gov tenant
```

For the dev box and the test suite the env vars are intentionally
unset; storage falls back to `<repo>/data/<region>/` and the DB
fallback returns `None`, which the route layer interprets as "use the
local SQLite". The same fallback chain is used in CI so the
residency tests run without any external infrastructure.

## 3. Auditor verification checklist

Anything below can be verified from primary sources without operator
intervention.

- [ ] **Tenant tag.** Read `tenants/<id>.json` — `data_region` is the
      contractual tag. Diff against the DPA appendix.
- [ ] **Storage isolation.** `find data/ -maxdepth 2 -type d` shows
      separate roots per region. The `lv-only` subtree must not
      contain any non-`lv-only` tenant directories.
- [ ] **DB isolation.** `fly secrets list` shows `LVCODEX_DB_URL_LV_ONLY`
      set on the LV-only app, and **not** set on the EU app (or set to
      the LV DB's read-only replica only).
- [ ] **Fly region pinning.** `fly regions list --app <lv-only-app>`
      returns `waw` only. The `allowed_fly_regions` table in
      `server_app/services/residency.py::REGION_FLY_REGIONS` matches.
- [ ] **Routing guard at request time.** `GET /api/tenant` against
      `gov-lv.lvcodex.com` on an EU machine logs a
      `residency.cross_region_reject` audit event. (Reproducible via
      the integration test `test_resolve_residency_rejects_gov_lv_in_fra`.)
- [ ] **Cross-tenant guard.** `assert_same_region("acme-school",
      "gov-lv")` raises `DataResidencyError`. (Reproducible via
      `test_eu_admin_cannot_touch_lv_only_tenant`.)
- [ ] **Audit-log surface.** Every rejection emits an `audit_events`
      row visible through the T-043 `GET /api/admin/audit-export`
      endpoint. The CSV column `event` carries the
      `residency.cross_region_reject` tag.

## 4. Failure modes and rollback

### 4.1 `LVCODEX_DB_URL_LV_ONLY` is unset

Symptom: an `lv-only` tenant request reaches the route layer but
`tenant_db_url(tenant)` returns `None`. The route handler refuses to
fall back to the EU DB and responds 503.

Action: set the secret on the LV-only Fly app; redeploy. No data is
written or replicated cross-border during the outage — the route
handler refused to open the EU connection in the first place.

### 4.2 Request lands on the wrong Fly region

Symptom: `DataResidencyError` raised with `reason="unsupported_fly_region"`,
HTTP 502 emitted, `residency.cross_region_reject` audit row written.

Action: this is the intended fail-closed posture. Investigate Cloudflare
/ Fly anycast routing for the affected tenant. The data layer was
never touched.

### 4.3 Cross-tenant access attempt by a superadmin

Symptom: `DataResidencyError` raised with `reason="cross_region_access"`.

Action: a superadmin tried to inspect an `lv-only` tenant from an EU
session. The platform refuses. If the access is legitimate (e.g. an
on-prem operator at the LV side requested help), the operator must
re-establish the session against the LV-only portal and re-issue the
request from a `waw` Fly machine.

## 5. Roadmap

* **Cross-region transfer flow.** Out of scope for T-065. A future
  ticket will design the counter-signed-DPA workflow that allows a
  one-shot export from `lv-only` to a controlled EU bucket for legal
  hold or e-discovery purposes. Until that ships, the only path off
  the `lv-only` plane is a manual operator-attested backup.
* **Latvian sovereign cloud.** If Latvia opens a sovereign cloud
  before our next renewal we will drop `waw` from
  `REGION_FLY_REGIONS["lv-only"]` in the same PR. This document and
  the DPA must both be revisited at that point.
* **Audit dashboard.** The `residency.cross_region_reject` rows feed
  the institutional admin dashboard (T-043). A follow-up ticket will
  expose a "Last 30 days residency incidents" tile.
