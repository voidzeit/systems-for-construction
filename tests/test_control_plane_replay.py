"""An append-only log you cannot rebuild from is a log in name only."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.control_plane import ControlPlane, ReplayError
from sfc.events import Event, EventLog
from sfc.governance import Review, ReviewDecision, ValueRecord
from sfc.lifecycle import ObligationStatus, ValueStatus, WorkPackage, WorkPackageStatus


def _exercised(log: EventLog) -> ControlPlane:
    """Drive one plane through every transition the reference service supports."""
    plane = ControlPlane(event_log=log)
    plane.register_obligation("OBL-1")
    plane.advance_obligation("OBL-1", ObligationStatus.CLASSIFIED, "actor-1")
    plane.advance_obligation("OBL-1", ObligationStatus.ACCEPTED, "actor-1")
    plane.add_work_package(WorkPackage("WP-1", "Install boards", ("OBL-1",), evidence_ids=("E-1",)))
    plane.advance_work_package("WP-1", WorkPackageStatus.IN_PROGRESS, "actor-1")
    plane.advance_work_package("WP-1", WorkPackageStatus.EVIDENCE_CLAIMED, "actor-1")
    plane.add_review(Review("REV-1", "OBL-1", ReviewDecision.ACCEPTED, "reviewer-1", reason="checked on site"))
    plane.add_review(Review("REV-2", "OBL-1", ReviewDecision.REVOKED, "reviewer-2", supersedes_review_id="REV-1"))
    plane.add_value(ValueRecord("VAL-1", "WP-1", amount=1000.0, currency="USD"))
    plane.advance_value("VAL-1", ValueStatus.BUDGETED, actor_id="actor-1")
    plane.advance_value("VAL-1", ValueStatus.COMMITTED, actor_id="actor-1")
    plane.advance_value("VAL-1", ValueStatus.PLANNED, actor_id="actor-1")
    plane.advance_value("VAL-1", ValueStatus.EARNED, evidence_ids=("E-1",), actor_id="actor-1")
    return plane


class ReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")

    def test_replay_reproduces_the_derived_state(self) -> None:
        live = _exercised(self.log)
        replayed = ControlPlane.from_events(self.log.read())
        self.assertEqual(replayed.state(), live.state())
        self.assertTrue(live.replay_matches(self.log.read()))

    def test_replay_preserves_review_history_and_the_current_review(self) -> None:
        live = _exercised(self.log)
        replayed = ControlPlane.from_events(self.log.read())
        self.assertEqual(len(replayed.reviews), 2)
        # REV-1 was revoked by REV-2, so no review is current.
        self.assertIsNone(replayed.current_review("OBL-1"))
        self.assertEqual(replayed.current_review("OBL-1"), live.current_review("OBL-1"))

    def test_replay_preserves_value_evidence(self) -> None:
        _exercised(self.log)
        replayed = ControlPlane.from_events(self.log.read())
        value = replayed.values["VAL-1"]
        self.assertIs(value.status, ValueStatus.EARNED)
        self.assertEqual(value.evidence_ids, ("E-1",))
        self.assertEqual(value.amount, 1000.0)

    def test_replay_does_not_re_emit_what_it_reads(self) -> None:
        _exercised(self.log)
        before = len(self.log.read())
        ControlPlane.from_events(self.log.read(), event_log=self.log)
        self.assertEqual(len(self.log.read()), before)

    def test_a_replayed_plane_can_continue_recording(self) -> None:
        _exercised(self.log)
        replayed = ControlPlane.from_events(self.log.read(), event_log=self.log)
        replayed.advance_value("VAL-1", ValueStatus.CERTIFIED, actor_id="actor-2")
        self.assertIs(replayed.values["VAL-1"].status, ValueStatus.CERTIFIED)
        self.assertEqual(self.log.read()[-1]["eventType"], "value.transitioned")

    def test_replay_applies_the_same_rules_as_live_execution(self) -> None:
        # A log asserting a skipped transition must not reconstruct a state the
        # lifecycle graph forbids.
        self.log.append(Event("obligation.discovered", "OBL-1", {"status": "discovered"}))
        self.log.append(Event("obligation.transitioned", "OBL-1", {"from": "discovered", "to": "approved"}))
        with self.assertRaises(ReplayError) as raised:
            ControlPlane.from_events(self.log.read())
        self.assertIn("obligation.transitioned", str(raised.exception))

    def test_replay_refuses_value_recognition_without_evidence(self) -> None:
        self.log.append(Event("value.created", "VAL-1", ValueRecord("VAL-1", "WP-1").to_dict()))
        for previous, target in (("Unbudgeted", "Budgeted"), ("Budgeted", "Committed"), ("Committed", "Planned")):
            self.log.append(Event("value.transitioned", "VAL-1", {"from": previous, "to": target, "evidenceIds": []}))
        self.log.append(Event("value.transitioned", "VAL-1", {"from": "Planned", "to": "Earned", "evidenceIds": []}))
        with self.assertRaises(ReplayError) as raised:
            ControlPlane.from_events(self.log.read())
        self.assertIn("evidence", str(raised.exception))

    def test_an_unrecognized_event_is_recorded_rather_than_dropped(self) -> None:
        self.log.append(Event("evidence.added", "E-1", {"state": "pending_review"}))
        replayed = ControlPlane.from_events(self.log.read())
        self.assertEqual(len(replayed.unapplied_events), 1)
        self.assertEqual(replayed.unapplied_events[0]["eventType"], "evidence.added")

    def test_an_empty_log_replays_to_an_empty_plane(self) -> None:
        replayed = ControlPlane.from_events([])
        self.assertEqual(replayed.state(), ControlPlane().state())

    def test_replay_is_deterministic(self) -> None:
        _exercised(self.log)
        events = self.log.read()
        self.assertEqual(
            ControlPlane.from_events(events).state(),
            ControlPlane.from_events(events).state(),
        )


class DurabilityTests(unittest.TestCase):
    def test_the_reference_plane_is_documented_as_non_durable(self) -> None:
        from sfc import control_plane

        self.assertIn("not a durable service", control_plane.__doc__)
        self.assertIn("Not durable", ControlPlane.__doc__)

    def test_state_is_not_shared_between_instances(self) -> None:
        first, second = ControlPlane(), ControlPlane()
        first.register_obligation("OBL-1")
        self.assertEqual(second.obligation_states, {})


if __name__ == "__main__":
    unittest.main()
