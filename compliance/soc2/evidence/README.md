# SOC 2 evidence snapshots

This directory holds the weekly snapshots produced by
[`.github/workflows/soc2-evidence.yml`](../../../.github/workflows/soc2-evidence.yml)
and the orchestrator at
[`compliance/soc2/automation/orchestrator.py`](../automation/orchestrator.py).

Layout:

```
compliance/soc2/evidence/
  2026-W21/
    ci_runs.json
    backup_drills.json
    access_audit.json
    manifest.json
  2026-W22/
    ...
```

Each `YYYY-Www` directory is one ISO-week worth of evidence. The
`manifest.json` lists which collectors succeeded and points at the
JSON files. Files are intentionally JSON (not CSV) so the auditor can
diff week-over-week with a structural diff tool.

See [`compliance/soc2/evidence-matrix.md`](../evidence-matrix.md) §G
for the control mapping.
