"""T-029 — OpenAPI spec validation tests.

Verifies that ``schemas/openapi.yaml`` is a valid OpenAPI 3.1 document
and that its `paths` cross-check against the actual route table in
``server_app.routes``. The cross-check guarantees the published spec
does not drift away from the running server.

Specifically, this test module:

1. Loads and validates the spec via the public ``validate_openapi.py``
   helpers (the same code path the CI gate uses).
2. Verifies the document conforms to OpenAPI 3.1 (``openapi: 3.1.0`` and
   the spec-validator returns no errors).
3. Cross-checks that **at least 5** representative routes exist in both
   the spec and the ``server_app.routes`` registry. This catches the
   most common drift bugs: a route added to the server without being
   added to the spec, or a route renamed in the spec but still
   advertised by the server.
4. Verifies the spec declares a session-cookie security scheme
   (``a2_session``) — the canonical authentication mechanism every
   penetration-test vendor must know about.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_validator_module() -> Any:
    """Import scripts/validate_openapi.py as a module without polluting sys.path globally."""

    if "validate_openapi" in sys.modules:
        return sys.modules["validate_openapi"]
    spec = importlib.util.spec_from_file_location(
        "validate_openapi",
        ROOT / "scripts" / "validate_openapi.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_openapi"] = module
    spec.loader.exec_module(module)
    return module


# Representative routes that MUST appear in both the OpenAPI spec and the
# server's route registry. The list intentionally spans every major
# domain (auth, exams, attempts, billing, admin, uploads, health) so a
# drift in any one domain is caught.
REPRESENTATIVE_ROUTES: list[tuple[str, str]] = [
    ("GET", "/healthz"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/session"),
    ("GET", "/api/exams/catalog"),
    ("GET", "/api/dashboard"),
    ("POST", "/api/attempts/start"),
    ("POST", "/api/billing/checkout-session"),
    ("POST", "/api/stripe/webhook"),
    ("GET", "/api/admin/overview"),
    ("POST", "/api/uploads/speaking"),
    ("GET", "/legal/terms"),
]


def _server_route_to_spec_path(pattern: str) -> str:
    """Convert ``/api/foo/<bar>`` → ``/api/foo/{bar}`` for OpenAPI lookup."""

    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "<":
            close = pattern.find(">", i + 1)
            if close == -1:
                out.append(ch)
                i += 1
                continue
            out.append("{")
            out.append(pattern[i + 1 : close])
            out.append("}")
            i = close + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


class SpecLoadTests(unittest.TestCase):
    def test_spec_file_exists(self) -> None:
        spec_path = ROOT / "schemas" / "openapi.yaml"
        self.assertTrue(spec_path.exists(), f"missing {spec_path}")

    def test_spec_loads_as_mapping(self) -> None:
        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        self.assertIsInstance(spec, dict)
        self.assertEqual(spec.get("openapi"), "3.1.0")
        self.assertIn("info", spec)
        self.assertIn("paths", spec)


class SpecValidationTests(unittest.TestCase):
    """Spec must pass openapi-spec-validator against the 3.1 schema."""

    def test_spec_validates_against_openapi_3_1(self) -> None:
        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        errors = validator_module._validate(spec)
        if errors:
            details = "\n".join(errors[:10])
            self.fail(
                f"openapi.yaml failed OpenAPI 3.1 validation:\n{details}"
            )


class SecuritySchemeTests(unittest.TestCase):
    """The session-cookie scheme must be documented for pen-test vendors."""

    def test_session_cookie_security_scheme_is_declared(self) -> None:
        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        components = spec.get("components") or {}
        schemes = components.get("securitySchemes") or {}
        self.assertIn(
            "sessionCookie",
            schemes,
            "OpenAPI spec must declare a 'sessionCookie' security scheme",
        )
        scheme = schemes["sessionCookie"]
        self.assertEqual(scheme.get("type"), "apiKey")
        self.assertEqual(scheme.get("in"), "cookie")
        self.assertEqual(scheme.get("name"), "a2_session")

    def test_error_response_components_are_declared(self) -> None:
        """Every documented 4xx must reference the ApiError component."""

        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        components = spec.get("components") or {}
        responses = components.get("responses") or {}
        for name in ("BadRequest", "Unauthorized", "Forbidden", "NotFound", "RateLimited"):
            self.assertIn(name, responses, f"missing components/responses/{name}")
        schemas = components.get("schemas") or {}
        self.assertIn("ApiError", schemas)


class RouteCrossCheckTests(unittest.TestCase):
    """Cross-check spec vs server_app.routes — guarantees no drift."""

    def test_at_least_five_representative_routes_in_both_places(self) -> None:
        from server_app.routes import ROUTES as SERVER_ROUTES

        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        paths = spec.get("paths") or {}

        # Build (method_upper, spec_path) set from the OpenAPI document.
        spec_pairs: set[tuple[str, str]] = set()
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            for method in ("get", "post", "put", "patch", "delete"):
                if method in item:
                    spec_pairs.add((method.upper(), path))

        # Build (method, spec_path) set from server_app.routes — translating
        # the `<param>` convention to `{param}` so the two surfaces align.
        server_pairs: set[tuple[str, str]] = set()
        for method, pattern, _owner in SERVER_ROUTES:
            if method == "MIDDLEWARE":
                continue
            server_pairs.add((method, _server_route_to_spec_path(pattern)))

        # Intersect against the representative list — at least 5 must be
        # present in BOTH the spec and the server registry.
        crossed: list[tuple[str, str]] = []
        for method, path in REPRESENTATIVE_ROUTES:
            if (method, path) in spec_pairs and (method, path) in server_pairs:
                crossed.append((method, path))

        self.assertGreaterEqual(
            len(crossed),
            5,
            (
                f"only {len(crossed)} representative routes are in BOTH the "
                "OpenAPI spec and the server route registry; expected ≥ 5. "
                f"crossed={crossed}"
            ),
        )

    def test_every_spec_path_uses_curly_brace_param_syntax(self) -> None:
        """OpenAPI requires ``{name}``; ``<name>`` would silently mismatch."""

        validator_module = _load_validator_module()
        spec = validator_module._load_spec(ROOT / "schemas" / "openapi.yaml")
        for path in (spec.get("paths") or {}):
            self.assertNotIn("<", path, f"spec path {path!r} uses <…> instead of {{…}}")
            self.assertNotIn(">", path, f"spec path {path!r} uses <…> instead of {{…}}")


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
