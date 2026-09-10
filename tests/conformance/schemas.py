"""Shared loader that turns the portable schemas in spec/ into a live validator.

SFC Core is stdlib-only by ADR 0001, so ``jsonschema`` is a development
dependency rather than a runtime one. These helpers keep the import optional and
let the conformance tests skip when it is absent — except in CI, where
``SFC_REQUIRE_CONFORMANCE=1`` turns a missing dependency into a failure so
schema drift can never pass unnoticed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import unittest

SPEC = Path(__file__).parents[2] / "spec"

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    AVAILABLE = True
    IMPORT_ERROR: Exception | None = None
except ImportError as error:  # pragma: no cover - exercised only without the extra
    AVAILABLE = False
    IMPORT_ERROR = error

REQUIRED = os.environ.get("SFC_REQUIRE_CONFORMANCE") == "1"


def schema_paths() -> list[Path]:
    return sorted(SPEC.glob("*.schema.json"))


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SPEC / name).read_text(encoding="utf-8"))


def _registry() -> "Registry":
    registry = Registry()
    for path in schema_paths():
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema)
        # Register under the declared $id so cross-file relative $refs resolve,
        # and under the bare filename so a schema without an $id still loads.
        registry = resource @ registry
        registry = registry.with_resource(path.name, resource)
    return registry


def validator(name: str) -> "Draft202012Validator":
    return Draft202012Validator(load_schema(name), registry=_registry())


def requires_schemas(test: unittest.TestCase) -> None:
    """Skip when jsonschema is missing, unless the release gate demands it."""
    if AVAILABLE:
        return
    message = f"jsonschema is not installed: {IMPORT_ERROR}. Install with: pip install -e '.[dev]'"
    if REQUIRED:
        test.fail(f"SFC_REQUIRE_CONFORMANCE=1 but {message}")
    test.skipTest(message)


def assert_valid(test: unittest.TestCase, name: str, instance: Any) -> None:
    """Assert one instance against a schema, reporting every violation."""
    errors = sorted(validator(name).iter_errors(instance), key=lambda error: list(error.path))
    if not errors:
        return
    detail = "\n".join(
        f"  {'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    )
    test.fail(f"{instance.__class__.__name__} does not conform to {name}:\n{detail}")


def assert_roundtrip(test: unittest.TestCase, name: str, value: Any, loader) -> None:
    """A contract holds only if it survives the full boundary crossing.

    python object -> JSON -> schema -> python object -> JSON, unchanged.
    """
    first = value.to_dict()
    assert_valid(test, name, first)
    encoded = json.loads(json.dumps(first, ensure_ascii=False))
    second = loader(encoded).to_dict()
    test.assertEqual(first, second, f"{name} does not round-trip through JSON")
    assert_valid(test, name, second)
