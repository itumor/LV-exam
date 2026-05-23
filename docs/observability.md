# Observability runbook (T-014)

> Source of truth: BUSINESS_REPORT.md §9.2 #3 and Appendix A #3.

This document covers the lvcodex API's observability stack: where metrics
come from, how dashboards and alerts are deployed, and how to wire
PagerDuty and Slack as notifiers. The structured-logging companion
(T-018) and rate-limiting metrics (T-015) plug into the same scrape
target and dashboards once those tasks ship.

## What the API exposes

The Python server publishes Prometheus text-format metrics from a
single in-process registry implemented in
[`server/metrics.py`](../server/metrics.py). The registry is wired
into `server.py` via a trailing `# T-014 metrics hook` block — there
is **no** code path that mutates metrics from the middle of
`server.py`, so merges with parallel feature work stay clean.

### Scrape target

```
GET /metrics
Content-Type: text/plain; version=0.0.4; charset=utf-8
```

The endpoint is unauthenticated by design so that Grafana Cloud's
agent (or any Prometheus) can scrape it without service-account
plumbing. The endpoint MUST stay behind the fly.io private network
or a CDN allowlist — do not expose it on the public origin.

### Metric families

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `http_requests_total` | counter | `route`, `status` | Total HTTP requests served. |
| `http_request_errors_total` | counter | `route` | Subset of requests with status ≥ 500. Convenience series so SLO burn-rate queries don't need a status regex. |
| `http_request_duration_seconds` | histogram | `route` | Request latency in seconds. Buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10`. |

Route labels are pre-sanitized in `server/metrics.py` so opaque ids
(UUIDs, long hex tokens, integer ids) collapse to `:id` and don't
explode cardinality.

## Dashboards

Dashboards are stored as JSON under
[`monitoring/dashboards/`](../monitoring/dashboards/) so they can be
diffed, code-reviewed, and recreated from scratch after a Grafana
outage.

| File | Audience | Highlights |
| --- | --- | --- |
| `api-overview.json` | SRE / on-call | RPS by route, 5xx ratio, p50/p95/p99 latency, 24h totals. |
| `attempts-funnel.json` | Product / growth | Attempts started → submitted → scored, with scoring p95 and 5xx ratio. |

### Importing into Grafana Cloud

1. In Grafana Cloud, open **Dashboards → New → Import**.
2. Paste the JSON contents of the file (or use the *Upload* button).
3. When prompted, map the `datasource` variable to your Prometheus
   data source. Both dashboards use a `$datasource` template variable
   so no JSON edit is required per environment.
4. Save with the same folder name (`lvcodex`) used in production so
   the alert annotations' `dashboard:` links resolve.

To round-trip changes back into the repo, use the dashboard's
**Settings → JSON Model** view, copy the JSON, and overwrite the
file. Avoid manually re-numbering panels — the diff stays readable
when panel ids stay stable.

## Alerts

Alert rules live in
[`monitoring/alerts/slo.yml`](../monitoring/alerts/slo.yml).
They cover three SLO classes:

| Rule | Trigger | SLO |
| --- | --- | --- |
| `ErrorBudgetBurn` | 5xx ratio > 1% for 5m | Availability |
| `LatencyHigh` | p95 latency > 2s for 5m | Latency |
| `SQLiteWriteStalled` | No 2xx on `/api/score` or `/api/attempts/submit` for 30m while serving traffic | Availability |

### Loading the rules

* **Grafana Cloud (managed Prometheus)**: in the Grafana UI go to
  **Alerts & IRM → Alert rules → New → From recording rule file**
  and upload `monitoring/alerts/slo.yml`. Set the evaluation group
  interval to `30s` to match the file header.
* **Self-managed Prometheus**: mount the file into
  `/etc/prometheus/rules/lvcodex-slo.yml` and add
  `rule_files: ['/etc/prometheus/rules/*.yml']` to `prometheus.yml`.
  Reload with `kill -HUP` or the admin API.

### Routing to Slack and PagerDuty

The recommended notifier graph in Grafana Cloud Alertmanager:

```yaml
route:
  receiver: lvcodex-slack
  group_by: [alertname, service]
  routes:
    - matchers: [severity = "page"]
      receiver: lvcodex-pagerduty
      continue: true

receivers:
  - name: lvcodex-slack
    slack_configs:
      - channel: "#lvcodex-oncall"
        api_url_file: /etc/secrets/slack-webhook
        send_resolved: true
        text: |-
          *{{ .CommonAnnotations.summary }}*
          {{ .CommonAnnotations.description }}
          Dashboard: {{ .CommonAnnotations.dashboard }}
          Runbook: {{ .CommonAnnotations.runbook }}
  - name: lvcodex-pagerduty
    pagerduty_configs:
      - service_key_file: /etc/secrets/pagerduty-key
        severity: critical
        details:
          dashboard: '{{ .CommonAnnotations.dashboard }}'
          runbook: '{{ .CommonAnnotations.runbook }}'
```

All three rules already emit `severity: page` plus `dashboard` and
`runbook` annotations, so the receivers above work without
per-alert tuning.

## Per-alert response

### `ErrorBudgetBurn`

1. Open the **lvcodex — API overview** dashboard, sort the 5xx panel
   by route.
2. Cross-reference Sentry for the leading exception type.
3. If a single route dominates, check the most recent deploy
   (`fly releases list`) and consider rolling back via
   `fly releases rollback`.
4. If 5xx is spread across routes, check upstream dependencies
   (Groq, Stripe) and the SQLite volume.

### `LatencyHigh`

1. Identify the slow route on the p95-by-route panel.
2. For `/api/score` regressions, check the LLM provider status
   page; switch `LLM_PROVIDER` to a healthy backend if needed.
3. For storage-heavy routes, inspect SQLite write contention
   (`PRAGMA busy_timeout`) and the fly.io volume IOPS panel.

### `SQLiteWriteStalled`

1. SSH into the fly machine: `fly ssh console`.
2. Check `df -h /data` and `ls -l data/*.db*` for journal locks.
3. Confirm the worker thread isn't wedged with
   `ps -ef | grep server.py`. Restart the machine if it is.
4. If the WAL is large, run `sqlite3 data/app.db 'PRAGMA wal_checkpoint(FULL);'`.

## Verifying locally

```bash
# 1. Start the server.
python3 server.py

# 2. Generate a little traffic.
curl -s http://localhost:4173/api/session > /dev/null
curl -s http://localhost:4173/api/exams/catalog > /dev/null

# 3. Inspect /metrics.
curl -s http://localhost:4173/metrics | head -40
```

The output MUST include `# HELP`/`# TYPE` headers for every metric
family, even before any request is observed.

## Future work

* T-015 (rate limiting) will add `http_rate_limited_total{route,bucket}`
  to the same registry.
* T-018 (structured logging) will emit a `request_id` field that we
  echo in Grafana annotations so traces and logs cross-link.
* Once cross-link IDs land, replace the `dashboard:`/`runbook:`
  annotations in `slo.yml` with the long-form Grafana Cloud
  permalinks (currently placeholders).
