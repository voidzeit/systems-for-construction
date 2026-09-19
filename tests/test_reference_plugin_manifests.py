from pathlib import Path
import json
import unittest

from sfc.plugins import PluginManifest


ROOT = Path(__file__).parents[1]


class ReferencePluginManifestTests(unittest.TestCase):
    def test_reference_manifests_are_parseable_and_unique(self):
        paths = [
            ROOT / "connectors/revit/plugin.json",
            ROOT / "verticals/electrical/plugin.json",
            ROOT / "verticals/owner-requirements/plugin.json",
        ]
        manifests = [PluginManifest.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
        ids = [manifest.plugin_id for manifest in manifests]
        self.assertEqual(len(ids), len(set(ids)))

    def test_revit_contract_declares_model_write_side_effect(self):
        path = ROOT / "connectors/revit/plugin.json"
        manifest = PluginManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
        write = next(cap for cap in manifest.capabilities if cap.capability_id == "revit.element.set_parameter")
        self.assertIn("model.write", write.side_effects)
        self.assertIn("model.write", manifest.permissions)


if __name__ == "__main__":
    unittest.main()
