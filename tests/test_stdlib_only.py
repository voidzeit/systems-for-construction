"""ADR 0001 as an executable invariant: the runtime imports only the stdlib.

Provider neutrality is not a preference documented in an ADR; it is a property
that has to hold on every import path. A vendor SDK, an HTTP client or a
validation library reaching the runtime would make SFC depend on someone else's
release cycle for a determination to be reproducible.

Optional connectors are the one permitted exception, and only in a specific
shape: the import is function-local and guarded, so a missing package fails
explicitly at the call site instead of at import time. ``sfc.pdf`` is the
reference for that pattern.
"""

from __future__ import annotations

from pathlib import Path
import ast
import importlib
import pkgutil
import sys
import unittest

import sfc

#: Test-only tooling. It may already be in sys.modules because the test runner
#: imported it, and must never get there because sfc imported it.
DEVELOPMENT_ONLY = frozenset({
    "jsonschema", "referencing", "pytest", "_pytest", "py", "attrs", "attr", "rpds",
    "coverage", "pyflakes", "yaml", "iniconfig", "pluggy", "packaging",
})

#: Importing this module runs the CLI, so it is exercised through the CLI tests.
NOT_IMPORTABLE_AS_A_MODULE = frozenset({"sfc.__main__"})


def _third_party(names: set[str]) -> set[str]:
    roots = {name.partition(".")[0] for name in names}
    return {
        root
        for root in roots
        if root and not root.startswith("_") and root != "sfc" and root not in sys.stdlib_module_names
    }


def _module_paths() -> list[Path]:
    return sorted(Path(sfc.__path__[0]).glob("*.py"))


def _guarded_import_nodes(tree: ast.Module) -> set[int]:
    """Line numbers of imports inside a try/except that handles ImportError."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handles_import_error = any(
            handler.type is not None
            and "ImportError" in ast.unparse(handler.type)
            for handler in node.handlers
        )
        if not handles_import_error:
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    guarded.add(inner.lineno)
    return guarded


class StdlibOnlyTests(unittest.TestCase):
    def test_every_runtime_module_imports_without_third_party_packages(self) -> None:
        names = [
            module.name
            for module in pkgutil.iter_modules(sfc.__path__, prefix="sfc.")
            if module.name not in NOT_IMPORTABLE_AS_A_MODULE
        ]
        self.assertGreater(len(names), 20, "sfc package looks empty; check the import path")
        before = set(sys.modules)
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(name)
        imported = _third_party(set(sys.modules) - before) - DEVELOPMENT_ONLY
        self.assertEqual(imported, set(), f"importing the SFC runtime pulled in: {sorted(imported)}")

    def test_no_module_level_third_party_import(self) -> None:
        # sys.modules can be pre-populated by the test runner, so read the
        # source too: the import statement itself is the thing under test.
        offenders: dict[str, list[str]] = {}
        for path in _module_paths():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            roots: set[str] = set()
            for node in tree.body:
                if isinstance(node, ast.Import):
                    roots.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots.add(node.module)
            external = _third_party(roots)
            if external:
                offenders[path.name] = sorted(external)
        self.assertEqual(offenders, {}, f"module-level third-party imports: {offenders}")

    def test_every_optional_import_fails_explicitly(self) -> None:
        """A function-local third-party import must be guarded, not hopeful."""
        unguarded: dict[str, list[str]] = {}
        for path in _module_paths():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            guarded = _guarded_import_nodes(tree)
            top_level = {id(node) for node in tree.body}
            found: list[str] = []
            for node in ast.walk(tree):
                if id(node) in top_level:
                    continue
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = {node.module}
                else:
                    continue
                external = _third_party(names)
                if external and node.lineno not in guarded:
                    found.extend(f"{name} (line {node.lineno})" for name in sorted(external))
            if found:
                unguarded[path.name] = found
        self.assertEqual(unguarded, {}, f"unguarded optional imports: {unguarded}")

    def test_the_optional_pdf_connector_fails_with_a_clear_message(self) -> None:
        from sfc.pdf import load_pdf

        try:
            import pypdf  # noqa: F401
        except ImportError:
            with self.assertRaises(RuntimeError) as raised:
                load_pdf(_module_paths()[0])
            self.assertIn("pypdf", str(raised.exception))
        else:
            self.skipTest("pypdf is installed, so the missing-dependency path cannot be exercised")


if __name__ == "__main__":
    unittest.main()
