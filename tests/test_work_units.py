from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.control_plane import ControlPlane
from sfc.events import EventLog
from sfc.lifecycle import WorkPackage
from sfc.work import WorkUnit, WorkUnitStatus


def unit(**changes):
    values = dict(
        work_unit_id="WU-1",
        project_id="P-1",
        work_package_id="WP-1",
        capability_id="electrical.route.feeder",
        scope="Route feeder F-204",
        discipline="electrical",
        location="L03",
        requirement_ids=("R-1",),
        input_ids=("MODEL-1",),
        dependency_ids=(),
        acceptance_criteria=("continuous route",),
        qa_criteria=("no critical clash",),
    )
    values.update(changes)
    return WorkUnit(**values)


class WorkUnitTests(unittest.TestCase):
    def test_round_trip_preserves_contract(self):
        original = unit(estimated_effort_hours=2.5, compute_cost=0.25)
        self.assertEqual(WorkUnit.from_dict(original.to_dict()), original)

    def test_cannot_skip_to_acceptance(self):
        with self.assertRaises(ValueError):
            unit().advance(WorkUnitStatus.ACCEPTED)

    def test_blocked_requires_reason_and_clears_when_ready(self):
        ready = unit().advance(WorkUnitStatus.READY)
        with self.assertRaises(ValueError):
            ready.advance(WorkUnitStatus.BLOCKED)
        blocked = ready.advance(WorkUnitStatus.BLOCKED, blocked_reason="awaiting structural model")
        self.assertEqual(blocked.blocked_reason, "awaiting structural model")
        resumed = blocked.advance(WorkUnitStatus.READY)
        self.assertIsNone(resumed.blocked_reason)

    def test_happy_path_reaches_learned(self):
        current = unit()
        for state in (
            WorkUnitStatus.READY,
            WorkUnitStatus.RUNNING,
            WorkUnitStatus.MACHINE_QA,
            WorkUnitStatus.HUMAN_REVIEW,
            WorkUnitStatus.ACCEPTED,
            WorkUnitStatus.DELIVERED,
            WorkUnitStatus.LEARNED,
        ):
            current = current.advance(state)
        self.assertEqual(current.state, WorkUnitStatus.LEARNED)
        with self.assertRaises(ValueError):
            current.advance(WorkUnitStatus.READY)

    def test_correction_returns_to_ready(self):
        current = unit().advance(WorkUnitStatus.READY).advance(WorkUnitStatus.RUNNING)
        current = current.advance(WorkUnitStatus.MACHINE_QA).advance(WorkUnitStatus.CORRECTION)
        self.assertEqual(current.advance(WorkUnitStatus.READY).state, WorkUnitStatus.READY)

    def test_escalation_can_return_to_human_review(self):
        current = unit().advance(WorkUnitStatus.READY).advance(WorkUnitStatus.RUNNING)
        current = current.advance(WorkUnitStatus.MACHINE_QA).advance(WorkUnitStatus.ESCALATED)
        self.assertEqual(current.advance(WorkUnitStatus.HUMAN_REVIEW).state, WorkUnitStatus.HUMAN_REVIEW)

    def test_retry_path(self):
        current = unit().advance(WorkUnitStatus.READY).advance(WorkUnitStatus.RUNNING)
        current = current.advance(WorkUnitStatus.RETRY)
        self.assertEqual(current.advance(WorkUnitStatus.RUNNING).state, WorkUnitStatus.RUNNING)


class WorkUnitControlPlaneTests(unittest.TestCase):
    def test_plane_requires_known_package(self):
        plane = ControlPlane()
        with self.assertRaises(ValueError):
            plane.add_work_unit(unit())

    def test_events_rebuild_work_unit_state(self):
        with TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.jsonl")
            plane = ControlPlane(event_log=log)
            plane.add_work_package(WorkPackage("WP-1", "L03 feeders", ()))
            plane.add_work_unit(unit())
            plane.advance_work_unit("WU-1", WorkUnitStatus.READY, "lead-1")
            plane.advance_work_unit("WU-1", WorkUnitStatus.RUNNING, "specialist-1")
            events = log.read()
            rebuilt = ControlPlane.from_events(events)
        self.assertEqual(rebuilt.work_units["WU-1"].state, WorkUnitStatus.RUNNING)
        self.assertEqual(rebuilt.state(), plane.state())


if __name__ == "__main__":
    unittest.main()
