/**
 * Tenant theme composable (T-044).
 *
 * Loads the per-tenant brand palette + logo + support contact from the
 * Python backend's ``GET /api/tenant`` endpoint (resolved by the server
 * against the inbound ``Host:`` header) and applies the returned
 * ``css_variables`` block to ``document.documentElement.style`` so the
 * rest of the v2 SPA's stylesheet picks up the tenant colours.
 *
 * Design contract — must stay aligned with
 * ``server_app/services/tenant.py``:
 *
 *  * the wire format is exactly ``TenantConfig`` below,
 *  * the ``css_variables`` keys mirror the variables declared in
 *    ``src/styles.css``,
 *  * a network failure does NOT throw — the SPA falls back to the
 *    stylesheet defaults so the page still renders.
 */
import { reactive, readonly } from "vue";

export interface TenantConfig {
  id: string;
  name: string;
  primary_color: string;
  secondary_color: string;
  background_color: string;
  text_color: string;
  logo_url: string | null;
  favicon_url: string | null;
  support_email: string | null;
  custom_domain: string | null;
  host_aliases: string[];
  css_variables: Record<string, string>;
}

// Module-level singleton so every component that calls ``useTenant`` sees
// the same reactive object once it has been resolved.
const state = reactive<{
  tenant: TenantConfig | null;
  loading: boolean;
  error: string | null;
}>({
  tenant: null,
  loading: false,
  error: null,
});

// Fallback used when the network call fails. Keys/values must match the
// defaults declared in src/styles.css and tenants/example.json so a
// broken backend never renders a blank palette.
const FALLBACK_TENANT: TenantConfig = {
  id: "default",
  name: "lvcodex",
  primary_color: "#38bdf8",
  secondary_color: "#0ea5e9",
  background_color: "#0f172a",
  text_color: "#f1f5f9",
  logo_url: null,
  favicon_url: null,
  support_email: null,
  custom_domain: null,
  host_aliases: [],
  css_variables: {
    "--color-accent": "#38bdf8",
    "--color-accent-hover": "#0ea5e9",
    "--color-bg": "#0f172a",
    "--color-text": "#f1f5f9",
    "--tenant-id": "default",
    "--tenant-name": "lvcodex",
  },
};

/**
 * Apply ``cssVariables`` to ``document.documentElement.style``.
 *
 * Exported for unit testing; production callers go through ``loadTenant``.
 */
export function applyCssVariables(
  variables: Record<string, string>,
  element: HTMLElement = document.documentElement,
): void {
  for (const [key, value] of Object.entries(variables)) {
    // ``setProperty`` accepts only ``--`` prefixed names; defensively skip
    // anything else so a malformed backend response cannot poison the style
    // attribute.
    if (!key.startsWith("--")) continue;
    element.style.setProperty(key, value);
  }
}

/**
 * Fetch ``/api/tenant`` and apply the returned theme.
 *
 * Idempotent — calling this twice is harmless. Returns the resolved
 * tenant (or the fallback on error) so callers that want to display the
 * tenant name can ``await`` it.
 */
export async function loadTenant(): Promise<TenantConfig> {
  state.loading = true;
  state.error = null;
  try {
    const response = await fetch("/api/tenant", {
      headers: { Accept: "application/json" },
      // Don't cache; tenant theme is per-request resolved by Host header
      // so a SW cache could serve stale theme during local previews.
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`tenant fetch failed: HTTP ${response.status}`);
    }
    const data = (await response.json()) as TenantConfig;
    if (data && data.css_variables) {
      applyCssVariables(data.css_variables);
    }
    state.tenant = data;
    return data;
  } catch (err) {
    state.error = err instanceof Error ? err.message : String(err);
    // Apply the fallback so the page still renders the documented defaults.
    applyCssVariables(FALLBACK_TENANT.css_variables);
    state.tenant = FALLBACK_TENANT;
    return FALLBACK_TENANT;
  } finally {
    state.loading = false;
  }
}

/** Reactive accessor used by components — read-only by design. */
export function useTenant() {
  return readonly(state);
}

export const __TEST__ = { FALLBACK_TENANT, state };
