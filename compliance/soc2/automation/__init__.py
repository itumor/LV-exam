"""SOC 2 Type I evidence-automation package (T-070-final).

Collectors live as small, independently importable modules so a CI step
can run them individually and so the unit tests can mock out external
side-effects (``gh api``, the SQLite audit ledger, the R2 backup
listing) without standing up a real environment.

Each collector module exposes a ``collect(...)`` function that returns a
plain ``dict`` (JSON-serialisable). The orchestrator
:func:`compliance.soc2.automation.orchestrator.collect_all` writes those
dicts to ``compliance/soc2/evidence/YYYY-WW/<name>.json``.

Design rules:

* **Pure-stdlib only.** Avoid adding new pip deps to keep the audit
  surface (``pip-audit``) small. Use ``subprocess`` for ``gh`` because
  the GitHub Actions runner already has it.
* **Deterministic output.** Timestamps are sorted; floats are rounded;
  dicts use insertion order so a YAML diff between two weekly runs is
  human-readable.
* **No secrets in evidence.** Collectors must redact PII / tokens
  before serialising. The CSV / JSON files committed to
  ``compliance/soc2/evidence/`` are reviewed by an external auditor.
"""

from __future__ import annotations

__all__ = [
    "ci_runs",
    "backup_drills",
    "access_audit",
    "orchestrator",
]
