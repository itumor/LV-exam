# K8s PoC manifests — T-072 (reference-only)

These manifests are **deliberately not applied**. They exist so that, when
we re-open the T-072 decision under one of the triggers in
`docs/k8s-evaluation.md` §6, we have a concrete, reviewed starting point
instead of a blank `kubectl apply -f`.

## What's here

| File | Resource | Notes |
|---|---|---|
| `namespace.yaml` | `Namespace` | `lvcodex` namespace; PodSecurityStandards labels (`restricted`). |
| `deployment.yaml` | `Deployment` | 2 replicas, `python:3.13-alpine` image hashed to current Dockerfile base; rolling update. |
| `service.yaml` | `Service` | ClusterIP on port 80 fronting the Deployment. |
| `ingress.yaml` | `Ingress` | NGINX ingress with TLS via cert-manager; host `latvian-a2-exam.example.com`. |
| `configmap.yaml` | `ConfigMap` | Non-secret env from `fly.toml` (`APP_ENV`, DB paths, etc.). |
| `secret.yaml` | `Secret` | Stub keys for `DATABASE_URL`, `STRIPE_*`, `GROQ_API_KEY`, etc. Values are placeholders — never store real secrets in git. |
| `hpa.yaml` | `HorizontalPodAutoscaler` | Scale 2 → 8 on 70 % CPU / 80 % memory. |
| `pvc.yaml` | `PersistentVolumeClaim` | 10 GiB RWO claim mirroring `/app/data` from Fly volume; only used if we keep SQLite. |

## Apply order (when/if we ever do this)

```
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml         # populate values first via SealedSecrets / SOPS / ESO
kubectl apply -f pvc.yaml            # skip if running Postgres-only
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f hpa.yaml
kubectl apply -f ingress.yaml
```

## What's intentionally **not** here

- **No Helm chart.** A chart only makes sense once we have a real consumer
  (a customer VPC or our own cluster). At that point we'd template these
  manifests with proper values.
- **No service account / IRSA / Workload Identity.** Platform-specific.
- **No network policies.** They depend on the CNI we end up choosing.
- **No backup / restore manifests.** R2 backup hooks live in the app
  image; the Velero install would belong to the cluster bootstrap layer,
  not the app chart.

## Image source

The Deployment refers to `ghcr.io/itumor/lvcodex:latest`. We do **not**
currently publish to GHCR (only Fly's internal registry). That's part of
the work that would have to happen during a real migration — see
`docs/k8s-evaluation.md` §6 trigger #3.

## Verification (without applying)

The manifests below pass `kubectl --dry-run=client -o yaml` and `kubeval`:

```bash
# From repo root:
for f in infra/k8s-poc/*.yaml; do
  kubectl --dry-run=client apply -f "$f" -o yaml >/dev/null
done
```

We will *not* run `kubectl --dry-run=server` because that requires an
actual cluster connection, which defeats the docs-only intent of T-072.
