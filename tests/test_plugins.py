from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from sfc.plugins import AutonomyLevel, PluginManifest, discover_plugin_manifests


def manifest(**changes):
    value = {
        "pluginId": "sfc.reference.electrical",
        "name": "Reference Electrical",
        "version": "0.1.0",
        "contractVersion": "1",
        "family": "domain_pack",
        "domain": "electrical",
        "capabilities": [{
            "capabilityId": "electrical.inspect",
            "riskClass": "low",
            "maximumAutonomy": "A1",
        }],
        "permissions": ["project.read"],
        "sideEffects": [],
        "autonomyCeiling": "A1",
    }
    value.update(changes)
    return value


class PluginManifestTests(unittest.TestCase):
    def test_round_trip(self):
        parsed = PluginManifest.from_dict(manifest())
        self.assertEqual(PluginManifest.from_dict(parsed.to_dict()), parsed)

    def test_capability_cannot_exceed_plugin_ceiling(self):
        value = manifest(autonomyCeiling="A1")
        value["capabilities"][0]["maximumAutonomy"] = "A5"
        with self.assertRaises(ValueError):
            PluginManifest.from_dict(value)

    def test_invalid_risk_is_rejected(self):
        value = manifest()
        value["capabilities"][0]["riskClass"] = "magic"
        with self.assertRaises(ValueError):
            PluginManifest.from_dict(value)

    def test_discovery_is_deterministic_and_rejects_duplicates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text(json.dumps(manifest()), encoding="utf-8")
            self.assertEqual(discover_plugin_manifests(root)[0].plugin_id, "sfc.reference.electrical")
            (root / "b.json").write_text(json.dumps(manifest(name="Duplicate")), encoding="utf-8")
            with self.assertRaises(ValueError):
                discover_plugin_manifests(root)

    def test_missing_directory_is_empty(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(discover_plugin_manifests(Path(directory) / "absent"), ())


if __name__ == "__main__":
    unittest.main()
