# Kubernetes vs Fly evaluation (T-072)

Status: **Decision-only** — this document captures the comparison between
Fly.io (our current platform) and the three Kubernetes options we evaluated.
**No infrastructure has been built or migrated.** The PoC manifests in
`infra/k8s-poc/` are reference-only and have never been applied to a cluster.

| Field | Value |
|---|---|
| **Decision** | **Stay on Fly.io** until one of the trigger conditions in §6 fires. |
| **Owner** | SRE Lead |
| **Effective date** | 2026-05-24 |
| **Next review** | 2026-11-24 (or on any §6 trigger) |
| **Dependencies** | T-028 multi-region (✓ merged) |

## 1. Why we evaluated K8s

Three drivers pushed us to evaluate Kubernetes ahead of the next budget
cycle:

1. **T-028 multi-region** is live (`fly.multi-region.toml`, `docs/multi-region.md`).
   The warm-standby topology works, but multi-region **writes** are not yet
   supported — only the LHR leader accepts writes; FRA serves reads from a
   streaming replica. A future need for active-active writes (e.g. EU + US)
   would force a re-platforming question.
2. **Compliance posture.** Some institutional pilots have asked whether we
   could self-host inside their VPC. Fly's machine-on-flycast model can do
   "bring your own cloud" only via Fly Macine private networking, which is
   not a self-hosted offering. Real self-hosting requires either Kubernetes
   or a Nomad/Compose cluster.
3. **Cost scaling.** The team wanted a written, defensible number for what
   each platform would cost at 1k / 5k / 10k MAU before we lock in another
   12 months on Fly. See `cost-model.csv`.

## 2. Workload profile (the thing we are evaluating *against*)

The numbers below come from production metrics on 2026-05-20 and the load
test in `docs/postgres-migration.md` §7.

| Dimension | Current value (2026-05) | Projection at 10k MAU |
|---|---|---|
| Container image | `python:3.13-alpine`, ~140 MB | Same |
| RSS per replica (p95) | ~190 MB | ~220 MB |
| CPU per replica (p95) | 0.15 vCPU | 0.4 vCPU |
| Concurrent connections (peak) | ~35 | ~350 |
| Replicas (today) | 1 in LHR + 1 in FRA warm | 4–6 in LHR + 2 in FRA |
| Stateful deps | Fly Postgres (`lvcodex-db`), Fly Volume (`/app/data`), Cloudflare R2 (backups) | Same |
| External deps | Groq, OpenAI, Stripe, Postmark | Same |
| Deploy cadence | 3–8 per week via `flyctl deploy` from CI | Same |
| Image build | `Dockerfile` (Alpine + Python deps) | Same |
| Healthcheck | `/healthz` (GET, 30 s, 5 s timeout) | Same |
| Concurrency limit per VM | soft 25 / hard 50 | soft 50 / hard 100 |

Key implication: the workload is small enough that the Kubernetes "control
plane overhead" — both in dollars and in ops time — would dominate the bill
for the next 18 months.

## 3. Comparison matrix

Headline summary; the full per-MAU dollar figures are in `cost-model.csv`.

| Dimension | Fly.io (current) | AWS EKS | GCP GKE Autopilot | DigitalOcean DOKS |
|---|---|---|---|---|
| **Control plane cost** | $0 (managed) | $73/mo per cluster | $73/mo (or $0 on Standard) | $0 on shared CP |
| **Compute pricing model** | Per-machine-second, idle-aware | EC2 on-demand + EBS + NAT | Per-pod-second (Autopilot) | Droplet-priced nodes |
| **NAT egress** | Included | ~$32.40/mo per NAT GW + $0.045/GB | ~$32.85/mo per Cloud NAT + $0.045/GB | $0 ingress, $0.01/GB egress over 1 TB |
| **Multi-region** | Native (regions list + `fly regions add`) | Two clusters + Route 53 latency records + cross-region VPC peering | Two clusters + Cloud DNS + VPC Network Peering | Two clusters + manual DNS + VPC Peering (Beta) |
| **Multi-region writes** | Not native (read replicas only) | Aurora Global / DSQL ($$$); or app-level sharding | Spanner ($$$); or Cloud SQL HA + manual app routing | Managed PG with read replicas only; writes through one region |
| **Persistent volumes** | Fly Volume (1× NVMe per machine) | EBS (`gp3`) | PD-balanced / PD-SSD | DO Block Storage |
| **Ops burden (operator-hours/month)** | ~2 h (deploys, secret rotation) | ~12 h (cluster upgrades q3mo, IRSA, addons, ALB controller, cert-manager) | ~6 h (Autopilot abstracts node mgmt) | ~8 h (manual node upgrades, registry tier-up) |
| **Observability** | Built-in metrics + LogQL via `fly logs`; Grafana Cloud via `monitoring/` | CloudWatch + Managed Prometheus + OTel Collector; or Datadog | Cloud Operations Suite + Managed Prometheus | DO Monitoring (basic) + 3rd-party stack |
| **Deployment velocity** | `flyctl deploy` ~80 s from CI; rolling per machine | `kubectl apply` + rolling update; image build + push to ECR + rollout ~3–4 min | Same as EKS pattern; ~3 min | Same; ~3 min |
| **Lock-in risk** | **High** (Fly-specific: machines, flycast, volumes, regions) | **Medium** (K8s API portable; IRSA/ALB/EBS are AWS-specific) | **Medium** (Autopilot is most opinionated; portability lost if you adopt Workload Identity & GKE-specific addons) | **Low** (DOKS is the closest to vanilla upstream K8s) |
| **Self-host inside customer VPC** | No | Yes (give Helm chart) | Yes (give Helm chart) | Less common in enterprise procurement |
| **GDPR data residency (EU)** | LHR + FRA + AMS regions | eu-west-1, eu-central-1, eu-west-2 | europe-west1, europe-west3 | FRA1, AMS3 |
| **Compliance certs** | SOC 2 Type II, HIPAA BAA, ISO 27001 | Largest in industry (SOC 2 / HIPAA / FedRAMP / PCI / etc.) | Same as AWS for top-tier certs | SOC 2, GDPR; smaller cert footprint |
| **Team K8s expertise required** | None | High (or pay a partner) | Medium | Medium |
| **Free egress allowance** | 100 GB/mo | 100 GB/mo from EC2 to internet (then $0.09/GB tiered) | 200 GB/mo from internet egress | 1 TB/droplet/mo (pooled) |

## 4. Ops burden — concrete failure modes

| Concern | Fly today | K8s (any flavour) |
|---|---|---|
| Patch the runtime (e.g. Python 3.13 CVE) | Rebuild Docker image, `flyctl deploy`. ~5 min. | Same image work, plus consider node AMI updates if using EKS managed node groups. Add ~30 min for upgrade testing. |
| Quarterly Kubernetes minor-version upgrade | n/a | 0.5–1 day per cluster, per cluster-team-member (control plane + nodepools + CRDs). |
| TLS cert rotation | Fly handles automatically (LE under the hood). | Need cert-manager + ClusterIssuer + DNS-01 webhook; ~1 day to bootstrap, ~1 h/year per cert. |
| Secret rotation | `fly secrets set` → automatic machine restart. | `kubectl create secret` + workload reload (Reloader / kustomize); or External Secrets Operator → AWS Secrets Manager / GCP SM. ~2 days to bootstrap. |
| Autoscaling event | Fly auto_start_machines fires within ~3 s. | HPA reacts in 15–30 s; cluster-autoscaler (or Karpenter) adds a node in 30–120 s. |
| Cross-region failover drill | `scripts/region-failover.sh` (T-028, ~5 min). | Needs Argo CD multi-cluster (or Flux) + DNS health checks + database promotion runbook. ~1 day to wire end-to-end. |

The K8s column adds **roughly 0.25 FTE of platform engineering** to keep the
plane spinning. With our current team (2.5 engineers) that is a 10 %
reduction in feature throughput — material at our stage.

## 5. Cost summary

Full breakdown in `cost-model.csv`. EUR conversions use the 30-day average
ECB rate as of 2026-05-22 (1 USD = 0.92 EUR). All numbers exclude the LLM
provider bill (same on any platform).

| Platform | 1k MAU | 5k MAU | 10k MAU |
|---|---|---|---|
| Fly.io (current topology) | **$42** | **$96** | **$184** |
| EKS (eu-west-1) | $173 | $237 | $352 |
| GKE Autopilot (europe-west1) | $109 | $178 | $298 |
| DOKS (FRA1) | $74 | $128 | $238 |

Notes:

- All four totals include compute + managed Postgres + block storage + a
  conservative egress allowance (300 GB/mo at 5k MAU; 600 GB at 10k MAU).
- EKS and GKE figures include the $73/mo control plane and one $32.40/mo
  NAT Gateway per cluster — both fixed costs that punish small workloads.
- DOKS shows the smallest delta versus Fly because DigitalOcean does not
  charge for the cluster control plane and bundles a generous egress pool.
- At 10k MAU Fly is still the cheapest by ~30 %. The cost curve does start
  to flatten around 50k MAU — see §6 trigger #3.

## 6. Decision and trigger conditions

**Decision: stay on Fly.io for the next 12 months.** Re-open this
evaluation when **any one** of the following triggers fires:

1. **Sustained 5k+ concurrent users.** Today the soft-cap is 25 connections
   per machine and we expect to peak around 350 concurrents at 10k MAU. If
   we materially exceed that — e.g. the gov-pilot we're scoping for Q4 2026
   ships and adds 10–20k concurrent learners — re-evaluate.
2. **Multi-region writes required.** If product asks for low-latency
   writes from a non-EU region (e.g. a US pilot with > 200 ms p95 expected),
   Fly's "single PG leader" architecture stops being good enough. K8s + a
   global Postgres (Aurora Global / Spanner / YugabyteDB) becomes the path
   of least resistance.
3. **Compliance self-hosting requirement.** If an enterprise pilot's
   procurement team mandates deployment inside their VPC — common with
   public-sector and finance customers — we ship a Helm chart and operate
   inside the customer cluster. The PoC in `infra/k8s-poc/` is the seed of
   that chart.
4. **Fly platform regression** that breaks an SLA we have publicly
   committed to (e.g. > 30 min outage in a single quarter, or repeated
   security incidents).
5. **Cost crossover.** When the projected 12-month Fly bill exceeds the
   projected DOKS or GKE bill by > 20 %. We will recompute every six months
   using the same model in `cost-model.csv`.

## 7. What's in this PR

| Deliverable | Path | Notes |
|---|---|---|
| Decision doc | `docs/k8s-evaluation.md` | This file. |
| PoC manifests | `infra/k8s-poc/` | Deployment, Service, Ingress, ConfigMap, Secret, HPA. Reference-only — never applied. |
| Cost model | `cost-model.csv` | Per-provider monthly cost at 1k / 5k / 10k MAU. |
| Risk-register update | `compliance/soc2/risk-register.md` | New row R-11: platform-lock-in residual risk. |

## 8. References

- T-028 multi-region: `docs/multi-region.md`, `fly.multi-region.toml`,
  `scripts/region-failover.sh`.
- T-021 Postgres migration: `docs/postgres-migration.md`.
- Fly pricing (machines): <https://fly.io/docs/about/pricing/>
- AWS EKS pricing: <https://aws.amazon.com/eks/pricing/>
- GKE Autopilot pricing: <https://cloud.google.com/kubernetes-engine/pricing>
- DOKS pricing: <https://www.digitalocean.com/pricing/kubernetes>
- Internal: `docs/cloud-hosting-and-improvement-architecture.md`,
  `compliance/soc2/risk-register.md`, `BUSINESS_REPORT.md`.

## 9. Revision history

| Date | Author | Change |
|---|---|---|
| 2026-05-24 | T-072 | Initial evaluation. |
