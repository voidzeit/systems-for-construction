import unittest

from sfc.work import WorkUnit

from . import schemas


class WorkUnitAndPluginSchemaTests(unittest.TestCase):
    def setUp(self):
        schemas.requires_schemas(self)

    def test_work_unit_round_trips(self):
        work = WorkUnit(
            "WU-1", "P-1", "WP-1", "electrical.route.feeder", "Route feeder F-204",
            discipline="electrical",
            requirement_ids=("R-1",),
            acceptance_criteria=("continuous route",),
            qa_criteria=("no critical clash",),
        )
        schemas.assert_roundtrip(self, "work-unit.schema.json", work, WorkUnit.from_dict)

    def test_blocked_schema_requires_reason(self):
        work = WorkUnit("WU-1", "P-1", "WP-1", "electrical.route.feeder", "Route feeder")
        document = work.to_dict()
        document["state"] = "blocked"
        self.assertFalse(schemas.validator("work-unit.schema.json").is_valid(document))
        document["blockedReason"] = "awaiting input"
        self.assertTrue(schemas.validator("work-unit.schema.json").is_valid(document))

    def test_plugin_manifest_contract(self):
        manifest = {
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
        schemas.assert_valid(self, "plugin.schema.json", manifest)


if __name__ == "__main__":
    unittest.main()
