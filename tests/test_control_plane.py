from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.control_plane import ControlPlane
from sfc.events import EventLog
from sfc.governance import Review, ReviewDecision, ValueRecord
from sfc.lifecycle import ObligationStatus, ValueStatus, WorkPackage


class ControlPlaneTests(unittest.TestCase):
    def test_application_service_enforces_transitions_and_records_events(self) -> None:
        with TemporaryDirectory() as directory:
            service = ControlPlane(EventLog(Path(directory) / "events.jsonl"))
            service.register_obligation("obl-1")
            service.advance_obligation("obl-1", ObligationStatus.CLASSIFIED, "agent")
            with self.assertRaises(ValueError):
                service.advance_obligation("obl-1", ObligationStatus.APPROVED, "agent")
            self.assertEqual(len(service.event_log.read("obl-1")), 2)

    def test_value_and_review_are_governed_by_service(self) -> None:
        service = ControlPlane()
        service.add_work_package(WorkPackage("wp-1", "Panel work", ("obl-1",)))
        service.add_value(ValueRecord("v-1", "wp-1"))
        service.advance_value("v-1", ValueStatus.BUDGETED)
        service.advance_value("v-1", ValueStatus.COMMITTED)
        service.advance_value("v-1", ValueStatus.PLANNED)
        with self.assertRaises(ValueError):
            service.advance_value("v-1", ValueStatus.EARNED)
        service.advance_value("v-1", ValueStatus.EARNED, evidence_ids=("e-1",))
        service.add_review(Review("rev-1", "v-1", ReviewDecision.ACCEPTED, "reviewer"))
        self.assertEqual(service.current_review("v-1").decision, ReviewDecision.ACCEPTED)
