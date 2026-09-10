"""The evidence room is rebuildable from the log, and refuses a log it cannot read.

Two properties are being asserted, and they are different:

    replay fidelity   reducing the log reproduces the state that was recorded
    fail closed       a log this build cannot fully read is refused, not
                      reduced into a state that silently omits part of it

The second matters more than it looks. A reducer that ignores event types it
does not recognise reports a successful replay either way, so a log written by
a newer build would rebuild into a state missing whatever those events said,
with nothing anywhere indicating it.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.authority import EvidenceAdmissionError, EvidenceAuthority
from sfc.events import Event, EventLog, ReplayError
from sfc.evidence_room import DocumentState, EvidenceRoom, EvidenceState
from sfc.models import Evidence, EvidenceSourceType


def _evidence(evidence_id: str, *, authority: float = 0.9) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id="ifc:model-1",
        source_type=EvidenceSourceType.MODEL_ELEMENT,
        locator={"elementId": "B-1", "property": "Spacing"},
        observed_value={"value": 0.74676, "unit": "m"},
        authority=authority,
        confidence=1.0,
        provenance=("project-world",),
    )


def _exercised(log: EventLog) -> EvidenceRoom:
    """A room taken through documents, admission, supersession and revocation."""
    room = EvidenceRoom(event_log=log)
    version = room.add_document_version("DOC-1", "spec.pdf", b"first revision", uploaded_by="author-1")
    room.add_document_version("DOC-1", "spec.pdf", b"second revision", uploaded_by="author-2")
    room.add_evidence(_evidence("E-1"), version_id=version.version_id)
    room.submit_for_review("E-1")
    room.admit("E-1", actor_id="reviewer-1")
    room.add_evidence(_evidence("E-2"))
    room.submit_for_review("E-2")
    room.transition("E-2", EvidenceState.REJECTED, actor_id="reviewer-1")
    room.add_evidence(_evidence("E-3"))
    room.submit_for_review("E-3")
    room.admit("E-3", actor_id="reviewer-1")
    room.transition("E-3", EvidenceState.STALE, actor_id="reviewer-2")
    return room


class ReplayFidelityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")

    def test_reducing_the_log_reproduces_the_room(self) -> None:
        live = _exercised(self.log)
        self.assertEqual(EvidenceRoom.from_events(self.log.read()).state(), live.state())
        self.assertTrue(live.replay_matches(self.log.read()))

    def test_document_supersession_is_reconstructed(self) -> None:
        _exercised(self.log)
        replayed = EvidenceRoom.from_events(self.log.read())
        versions = replayed.all_versions("DOC-1")
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].state, DocumentState.REPLACED)
        self.assertEqual(versions[1].state, DocumentState.OBSERVED)

    def test_evidence_states_and_admission_are_reconstructed(self) -> None:
        _exercised(self.log)
        replayed = EvidenceRoom.from_events(self.log.read())
        self.assertEqual(replayed.get("E-1").state, EvidenceState.ADMITTED)
        self.assertTrue(replayed.get("E-1").evidence.admitted)
        self.assertEqual(replayed.get("E-2").state, EvidenceState.REJECTED)
        self.assertFalse(replayed.get("E-2").evidence.admitted)
        self.assertEqual(replayed.get("E-3").state, EvidenceState.STALE)

    def test_the_link_from_evidence_to_its_document_version_survives(self) -> None:
        _exercised(self.log)
        replayed = EvidenceRoom.from_events(self.log.read())
        self.assertEqual(replayed.get("E-1").version_id, "DOC-1:" + _first_hash(self.log)[:12])

    def test_replay_does_not_re_emit_what_it_reads(self) -> None:
        _exercised(self.log)
        before = len(self.log.read())
        EvidenceRoom.from_events(self.log.read(), event_log=self.log)
        self.assertEqual(len(self.log.read()), before)

    def test_a_replayed_room_can_continue_recording(self) -> None:
        _exercised(self.log)
        replayed = EvidenceRoom.from_events(self.log.read(), event_log=self.log)
        replayed.transition("E-1", EvidenceState.REVOKED, supersedes_evidence_id="E-3", actor_id="reviewer-3")
        self.assertEqual(replayed.get("E-1").state, EvidenceState.REVOKED)
        self.assertEqual(self.log.read()[-1]["eventType"], "evidence.transitioned")

    def test_replay_is_deterministic(self) -> None:
        _exercised(self.log)
        events = self.log.read()
        self.assertEqual(EvidenceRoom.from_events(events).state(), EvidenceRoom.from_events(events).state())


class ReplayRuleTests(unittest.TestCase):
    """Replay applies the same domain rules as live execution."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")

    def test_a_log_asserting_a_forbidden_transition_fails_to_replay(self) -> None:
        room = EvidenceRoom(event_log=self.log)
        room.add_evidence(_evidence("E-1"))
        # candidate -> admitted skips review, which the graph forbids.
        self.log.append(Event("evidence.transitioned", "E-1", {
            "from": "candidate", "to": "admitted", "minimumAuthority": 0.6,
        }))
        with self.assertRaises(ReplayError) as raised:
            EvidenceRoom.from_events(self.log.read())
        self.assertIn("evidence.transitioned", str(raised.exception))

    def test_a_log_recording_an_inadmissible_admission_fails_to_replay(self) -> None:
        room = EvidenceRoom(event_log=self.log)
        room.add_evidence(_evidence("E-1", authority=0.2))
        room.submit_for_review("E-1")
        with self.assertRaises(EvidenceAdmissionError):
            room.admit("E-1")
        # The log now claims an admission that the rules never permitted.
        self.log.append(Event("evidence.transitioned", "E-1", {
            "from": "pending_review", "to": "admitted", "minimumAuthority": 0.6,
        }))
        with self.assertRaises(ReplayError) as raised:
            EvidenceRoom.from_events(self.log.read())
        self.assertIn("authority", str(raised.exception))

    def test_the_recorded_threshold_is_applied_not_this_build_default(self) -> None:
        # Admitted under a lowered threshold, which only the log can tell us.
        room = EvidenceRoom(event_log=self.log)
        room.add_evidence(_evidence("E-1", authority=0.3))
        room.submit_for_review("E-1")
        room.admit("E-1", EvidenceAuthority(minimum_authority=0.2))
        admission = self.log.read()[-1]
        self.assertEqual(admission["payload"]["minimumAuthority"], 0.2)

        replayed = EvidenceRoom.from_events(self.log.read())
        self.assertEqual(replayed.get("E-1").state, EvidenceState.ADMITTED)
        self.assertEqual(replayed.state(), room.state())

    def test_a_duplicated_evidence_event_fails_to_replay(self) -> None:
        room = EvidenceRoom(event_log=self.log)
        room.add_evidence(_evidence("E-1"))
        self.log.append(Event("evidence.added", "E-1", room.get("E-1").to_dict()))
        with self.assertRaises(ReplayError) as raised:
            EvidenceRoom.from_events(self.log.read())
        self.assertIn("already exists", str(raised.exception))

    def test_evidence_citing_an_unknown_document_version_fails_to_replay(self) -> None:
        envelope = EvidenceRoom().add_evidence(_evidence("E-1")).to_dict()
        self.log.append(Event("evidence.added", "E-1", {**envelope, "versionId": "DOC-9:deadbeef"}))
        with self.assertRaises(ReplayError) as raised:
            EvidenceRoom.from_events(self.log.read())
        self.assertIn("document version not found", str(raised.exception))


class FailClosedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")

    def test_an_event_type_no_projection_owns_is_refused(self) -> None:
        self.log.append(Event("evidence.added", "E-1", EvidenceRoom().add_evidence(_evidence("E-1")).to_dict()))
        self.log.append(Event("evidence.quantum.entangled", "E-1", {"state": "spooky"}))
        for projection in (EvidenceRoom, _control_plane()):
            with self.subTest(projection=projection.__name__):
                with self.assertRaises(ReplayError) as raised:
                    projection.from_events(self.log.read())
                self.assertIn("unrecognized event type", str(raised.exception))

    def test_a_caller_may_opt_into_inspecting_a_forward_version_log(self) -> None:
        self.log.append(Event("evidence.added", "E-1", EvidenceRoom().add_evidence(_evidence("E-1")).to_dict()))
        self.log.append(Event("evidence.quantum.entangled", "E-1", {"state": "spooky"}))
        room = EvidenceRoom.from_events(self.log.read(), strict=False)
        self.assertEqual(room.get("E-1").state, EvidenceState.CANDIDATE)
        self.assertEqual([event["eventType"] for event in room.unapplied_events], ["evidence.quantum.entangled"])

    def test_an_event_another_projection_owns_is_recorded_not_refused(self) -> None:
        # A single log carries both projections. Neither may read the other's
        # events as its own, and neither may treat them as unknown.
        from sfc.control_plane import ControlPlane

        plane = ControlPlane(event_log=self.log)
        plane.register_obligation("OBL-1")
        room = EvidenceRoom(event_log=self.log)
        room.add_evidence(_evidence("E-1"))

        events = self.log.read()
        replayed_room = EvidenceRoom.from_events(events)
        self.assertEqual(replayed_room.state(), room.state())
        self.assertEqual([event["eventType"] for event in replayed_room.unapplied_events], ["obligation.discovered"])

        replayed_plane = ControlPlane.from_events(events)
        self.assertEqual(replayed_plane.state(), plane.state())
        self.assertEqual([event["eventType"] for event in replayed_plane.unapplied_events], ["evidence.added"])

    def test_an_observational_event_is_owned_by_neither_but_known_to_both(self) -> None:
        from sfc.control_plane import ControlPlane

        self.log.append(Event("determination.produced", "OBL-1", {"status": "NOT_MET"}))
        for projection in (EvidenceRoom, ControlPlane):
            with self.subTest(projection=projection.__name__):
                replayed = projection.from_events(self.log.read())
                self.assertEqual(len(replayed.unapplied_events), 1)

    def test_every_emitted_event_type_is_declared_in_the_registry(self) -> None:
        # The registry is what makes fail-closed possible, so an event type
        # added without registering it must not slip through.
        from sfc.control_plane import ControlPlane
        from sfc.events import KNOWN_EVENT_TYPES

        plane = ControlPlane(event_log=self.log)
        plane.register_obligation("OBL-1")
        _exercised(self.log)
        emitted = {event["eventType"] for event in self.log.read()}
        self.assertTrue(emitted)
        self.assertEqual(emitted - KNOWN_EVENT_TYPES, set())


def _control_plane():
    from sfc.control_plane import ControlPlane

    return ControlPlane


def _first_hash(log: EventLog) -> str:
    versions = [event for event in log.read() if event["eventType"] == "document.version.added"]
    return versions[0]["payload"]["contentHash"]


if __name__ == "__main__":
    unittest.main()
