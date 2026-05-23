# API Rate Limits (T-015)

The lvcodex backend enforces per-IP and per-session token-bucket limits on
every `/api/*` request via the middleware installed in `server.py`. The
limiter itself lives in `rate_limit.py` (importable as a standalone module
with no `server.py` dependency).

## Tiers

| Scope     | Applies to                          | Default sustained rate | Default burst |
| --------- | ----------------------------------- | ---------------------- | ------------- |
| `ip`      | All `/api/*` requests (per IP)      | 60 req/min             | 30            |
| `session` | Authenticated requests (per cookie) | 120 req/min            | 60            |
| `ip_auth` | `/api/auth/*` (per IP, stricter)    | 10 req/min             | 5             |

The client IP is resolved via `X-Forwarded-For` (first hop) since Fly.io
fronts the app with a proxy. When the header is missing the limiter falls
back to the TCP peer address.

The session id used as the bucket key is the value of the `a2_session`
cookie. If no cookie is present the limiter also accepts a
`Authorization: Bearer <token>` header. Anonymous requests are not session-
limited (only IP-limited).

## 429 response

A rejected request receives:

- HTTP status `429 Too Many Requests`
- `Retry-After: <integer seconds>` header (always present, minimum `1`)
- JSON body: `{"error":"rate_limited","retry_after":N}`

`/healthz` is intentionally excluded so Fly.io's load balancer can keep
routing during partial outages.

## Environment overrides

Set these before starting `server.py` to retune any tier:

| Variable                       | Default | Notes                                |
| ------------------------------ | ------- | ------------------------------------ |
| `RATE_LIMIT_IP_BURST`          | `30`    | `ip` bucket capacity                 |
| `RATE_LIMIT_IP_PER_MIN`        | `60`    | `ip` refill, requests per minute     |
| `RATE_LIMIT_SESSION_BURST`     | `60`    | `session` bucket capacity            |
| `RATE_LIMIT_SESSION_PER_MIN`   | `120`   | `session` refill, requests per minute|
| `RATE_LIMIT_AUTH_BURST`        | `5`     | `ip_auth` bucket capacity            |
| `RATE_LIMIT_AUTH_PER_MIN`      | `10`    | `ip_auth` refill, requests per minute|
| `RATE_LIMIT_BYPASS_ROLES`      | `admin,superadmin` | Comma-separated role allow-list |

Any non-positive or unparseable value falls back to the default. Refill is
specified as "requests per minute" for human readability; internally the
limiter converts to tokens-per-second.

## Admin bypass / whitelisting

Accounts with role `admin` or `superadmin` skip the bucket check entirely
(no token is consumed, no 429 is emitted). The bypass list is configurable
via `RATE_LIMIT_BYPASS_ROLES`. To temporarily allow a service account through
the limiter, promote it to `admin` (or add a custom role to the env var
override). The bypass intentionally short-circuits **before** the bucket
consume but **after** any metrics / logging the surrounding handler emits —
operator visibility into admin traffic is preserved.

## Operational notes

- The limiter is in-process (per Python worker). With Fly.io's single-VM
  default for lvcodex this is sufficient; if the deployment scales out to
  multiple instances behind the proxy, replace `RateLimiter` with a Redis-
  backed bucket. The module surface (`RateLimiter.check(scope, key)`) is the
  stable contract.
- Buckets are created lazily per unique key and never expire. Memory usage
  is bounded by the number of distinct IPs and active sessions in any given
  process lifetime; restart cycles (Fly health checks, deploys) clear state.
- The existing `check_rate_limit` helper in `server.py` (used by
  `/api/auth/register` and `/api/auth/login` for human-readable error
  messages) coexists with this middleware. The middleware's `ip_auth`
  bucket is the primary backstop; the legacy in-handler check remains as a
  more user-friendly second layer for the specific auth endpoints.
- See `tests/server/test_rate_limit.py` for the canonical behavioural
  contract (refill timing, threading, tier separation, admin bypass).
