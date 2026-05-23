#!/usr/bin/env python3
"""Validate ``schemas/openapi.yaml`` against the OpenAPI 3.1 spec.

T-029 — External pen-test prep: OpenAPI spec + scope-of-work doc.

This script is the CI gate that prevents broken OpenAPI revisions from
shipping to partners / pen-test vendors. It loads
``schemas/openapi.yaml`` and runs it through ``openapi-spec-validator``
(the maintained spec-validator from the python-openapi org).

The spec lives at ``schemas/openapi.yaml`` (not ``.json``) because YAML
is the form vendors expect to receive — see
``docs/pentest-scope-of-work.md``.

Exit codes
----------
0  Spec is valid OpenAPI 3.1.
1  Spec failed validation (one or more errors printed to stderr).
2  Unexpected runtime error (missing spec file, YAML parse error, missing
   dependency, etc.).

Usage
-----
    python3 scripts/validate_openapi.py                # validate default spec
    python3 scripts/validate_openapi.py --spec PATH    # validate alternate spec
    python3 scripts/validate_openapi.py --quiet        # only emit errors
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "schemas" / "openapi.yaml"


def _load_spec(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"OpenAPI spec not found: {path}")

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(
            "PyYAML is required. Install with: pip install 'PyYAML>=6.0'"
        ) from exc

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"OpenAPI spec is not valid YAML: {exc}") from exc


def _validate(spec: dict) -> list[str]:
    """Validate ``spec`` against the OpenAPI 3.1 schema.

    Returns a list of error messages; an empty list means the spec is
    valid.
    """

    try:
        # Modern API (openapi-spec-validator >= 0.7).
        from openapi_spec_validator import (  # type: ignore[import-not-found]
            OpenAPIV31SpecValidator,
        )
    except ImportError:
        OpenAPIV31SpecValidator = None  # type: ignore[assignment]

    errors: list[str] = []
    if OpenAPIV31SpecValidator is not None:
        try:
            for err in OpenAPIV31SpecValidator(spec).iter_errors():
                path = "/".join(str(p) for p in err.absolute_path) or "/"
                errors.append(f"{path}: {err.message}")
            return errors
        except Exception as exc:  # noqa: BLE001 - surface validator error
            errors.append(str(exc))
            return errors

    # Fall back to the single-shot ``validate`` for very old versions.
    try:
        from openapi_spec_validator import (  # type: ignore[import-not-found]
            validate as validate_spec,
        )
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(
            "openapi-spec-validator is required. Install with: "
            "pip install 'openapi-spec-validator>=0.7'"
        ) from exc

    try:
        validate_spec(spec)
    except Exception as exc:  # noqa: BLE001 - surface validator error
        errors.append(str(exc))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate schemas/openapi.yaml against OpenAPI 3.1."
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help=f"Path to the OpenAPI spec (default: {DEFAULT_SPEC.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only emit error lines; suppress the summary on success.",
    )
    args = parser.parse_args(argv)

    spec = _load_spec(args.spec)
    if not isinstance(spec, dict):
        print(
            f"validate_openapi: top-level of {args.spec} is not a mapping",
            file=sys.stderr,
        )
        return 1

    errors = _validate(spec)
    if errors:
        for msg in errors:
            print(f"[FAIL] {msg}", file=sys.stderr)
        print(
            f"validate_openapi: {len(errors)} error(s) in {args.spec.name}",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        paths = spec.get("paths") or {}
        version = (spec.get("info") or {}).get("version", "?")
        print(
            f"validate_openapi: ok — openapi={spec.get('openapi','?')} "
            f"info.version={version} paths={len(paths)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
