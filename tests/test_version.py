"""One version, read by every surface that reports one.

The MCP server used to carry a literal 0.1.0a4 while pyproject declared
0.1.0a5. A client asking a server what it is got the wrong answer, and nothing
caught it because nothing compared them.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

import sfc
from sfc.mcp import handle

ROOT = Path(__file__).parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def declared_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, "pyproject.toml declares no version"
    return match.group(1)


class VersionTests(unittest.TestCase):
    def test_the_package_reports_the_declared_version(self) -> None:
        if sfc.__version__ == "0.0.0.dev0":
            self.skipTest("the package is not installed, so metadata is unavailable")
        self.assertEqual(sfc.__version__, declared_version())

    def test_the_mcp_server_reports_the_package_version(self) -> None:
        response = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["result"]["serverInfo"]["version"], sfc.__version__)

    def test_no_module_hardcodes_a_version_string(self) -> None:
        pattern = re.compile(r'"\d+\.\d+\.\d+(?:[ab]\d+)?"')
        offenders: dict[str, list[str]] = {}
        for path in sorted(Path(sfc.__path__[0]).glob("*.py")):
            found = [
                match
                for match in pattern.findall(path.read_text(encoding="utf-8"))
                # Protocol and schema versions are other people's identifiers,
                # not this package's version.
                if match not in {'"2023-06-01"', '"2025-06-18"'}
            ]
            if found:
                offenders[path.name] = found
        self.assertEqual(offenders, {}, f"hardcoded version strings: {offenders}")

    def test_the_version_is_exported(self) -> None:
        self.assertIn("__version__", sfc.__all__)


if __name__ == "__main__":
    unittest.main()
