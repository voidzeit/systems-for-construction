from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.activity import derive_tasks
from sfc.conformance import ConformanceError, validate_semantics
from sfc.control_plane import ControlPlane, ReplayError
from sfc.events import Event, EventLog
from sfc.lifecycle import WorkPackage
from sfc.work import WorkUnit, WorkUnitError, WorkUnitStatus


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
        executor_id="specialist-1",
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



class WorkUnitAuthorityTests(unittest.TestCase):
    """Rules that hold inside one unit, whoever produced it (ADR 0013)."""

    def test_work_cannot_start_unassigned(self):
        ready = unit(executor_id=None).advance(WorkUnitStatus.READY)
        with self.assertRaisesRegex(WorkUnitError, "assigned executor"):
            ready.advance(WorkUnitStatus.RUNNING)
        self.assertEqual(ready.assign("specialist-2").advance(WorkUnitStatus.RUNNING).executor_id, "specialist-2")

    def test_an_executor_cannot_be_swapped_mid_attempt(self):
        running = unit().advance(WorkUnitStatus.READY).advance(WorkUnitStatus.RUNNING)
        with self.assertRaisesRegex(WorkUnitError, "cannot reassign"):
            running.assign("specialist-2")
        with self.assertRaisesRegex(WorkUnitError, "identified"):
            unit().assign("")

    def test_correction_may_go_to_another_executor(self):
        current = unit().advance(WorkUnitStatus.READY).advance(WorkUnitStatus.RUNNING)
        current = current.advance(WorkUnitStatus.MACHINE_QA).advance(WorkUnitStatus.CORRECTION)
        self.assertEqual(current.assign("specialist-2").executor_id, "specialist-2")


def semantic_violations(document):
    try:
        validate_semantics("work-unit.schema.json", document)
    except ConformanceError as error:
        return error.violations
    return ()


class WorkUnitSemanticConformanceTests(unittest.TestCase):
    def test_a_valid_plan_has_no_violations(self):
        self.assertEqual(semantic_violations(unit().to_dict()), ())

    def test_each_invariant_is_enforced(self):
        cases = {
            "dotted identifier": {"capabilityId": "RouteFeeder"},
            "depend on itself": {"dependencyIds": ["WU-1"]},
            "assigned executor": {"state": "machine_qa", "executorId": None},
            "cannot carry a blockedReason": {"blockedReason": "stale"},
        }
        for fragment, overrides in cases.items():
            with self.subTest(fragment):
                document = unit().to_dict()
                document.update(overrides)
                found = semantic_violations(document)
                self.assertTrue(any(fragment in violation for violation in found), found)


class WorkGraphTests(unittest.TestCase):
    """Rules that need the graph or the log, held by the control plane."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")
        self.plane = ControlPlane(event_log=self.log)
        self.plane.add_work_package(WorkPackage("WP-1", "L03 feeders", ()))

    def test_dependencies_must_already_be_planned(self):
        with self.assertRaisesRegex(WorkUnitError, "unplanned"):
            self.plane.add_work_unit(unit(work_unit_id="WU-2", dependency_ids=("WU-1",)))

    def test_units_enter_created_and_valid(self):
        with self.assertRaisesRegex(WorkUnitError, "enters the plane"):
            self.plane.add_work_unit(unit().advance(WorkUnitStatus.READY))
        with self.assertRaisesRegex(WorkUnitError, "dotted identifier"):
            self.plane.add_work_unit(unit(capability_id="route"))
        self.plane.add_work_unit(unit())
        with self.assertRaisesRegex(WorkUnitError, "already exists"):
            self.plane.add_work_unit(unit())

    def test_a_unit_is_not_ready_until_its_dependencies_are_accepted(self):
        self.plane.add_work_unit(unit())
        self.plane.add_work_unit(unit(work_unit_id="WU-2", capability_id="electrical.detail.hanger", dependency_ids=("WU-1",)))
        with self.assertRaisesRegex(WorkUnitError, "waiting on WU-1"):
            self.plane.advance_work_unit("WU-2", WorkUnitStatus.READY, "lead-1")
        self._accept("WU-1")
        self.assertEqual(self.plane.unaccepted_dependencies("WU-2"), ())
        self.plane.advance_work_unit("WU-2", WorkUnitStatus.READY, "lead-1")

    def test_every_transition_and_assignment_names_its_actor(self):
        self.plane.add_work_unit(unit())
        with self.assertRaisesRegex(WorkUnitError, "actor"):
            self.plane.advance_work_unit("WU-1", WorkUnitStatus.READY, "")
        with self.assertRaisesRegex(WorkUnitError, "actor"):
            self.plane.assign_work_unit("WU-1", "specialist-2", "")

    def test_a_submission_must_name_its_outputs(self):
        self._run("WU-1")
        with self.assertRaisesRegex(WorkUnitError, "outputs"):
            self.plane.advance_work_unit("WU-1", WorkUnitStatus.MACHINE_QA, "specialist-1")
        with self.assertRaisesRegex(WorkUnitError, "unique"):
            self.plane.advance_work_unit("WU-1", WorkUnitStatus.MACHINE_QA, "specialist-1", output_ids=("A", "A"))
        with self.assertRaisesRegex(WorkUnitError, "only on submission"):
            self.plane.advance_work_unit("WU-1", WorkUnitStatus.RETRY, "specialist-1", output_ids=("A",))

    def test_the_submitter_or_executor_cannot_accept(self):
        self._submit("WU-1", submitter="lead-2")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.HUMAN_REVIEW, "qa-bot")
        for actor in ("lead-2", "specialist-1"):
            with self.subTest(actor=actor):
                with self.assertRaisesRegex(WorkUnitError, "cannot accept"):
                    self.plane.advance_work_unit("WU-1", WorkUnitStatus.ACCEPTED, actor)
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.ACCEPTED, "reviewer-1")

    def test_correction_escalation_and_cancellation_must_say_why(self):
        self._submit("WU-1")
        for target in (WorkUnitStatus.CORRECTION, WorkUnitStatus.ESCALATED):
            with self.subTest(target=target):
                with self.assertRaisesRegex(WorkUnitError, "reason"):
                    self.plane.advance_work_unit("WU-1", target, "qa-bot")
        self.plane.add_work_unit(unit(work_unit_id="WU-2"))
        with self.assertRaisesRegex(WorkUnitError, "reason"):
            self.plane.advance_work_unit("WU-2", WorkUnitStatus.CANCELLED, "lead-1")

    def test_replay_reproduces_the_work_graph(self):
        self.plane.add_work_unit(unit())
        self.plane.add_work_unit(unit(work_unit_id="WU-2", dependency_ids=("WU-1",)))
        self._accept("WU-1", corrected_first=True)
        replayed = ControlPlane.from_events(self.log.read())
        self.assertEqual(replayed.state(), self.plane.state())
        self.assertEqual(replayed.work_units["WU-1"].executor_id, "specialist-2")
        self.assertEqual(replayed.work_unit_submitters, self.plane.work_unit_submitters)

    def test_replay_refuses_a_log_where_the_submitter_accepts(self):
        self._submit("WU-1", submitter="lead-2")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.HUMAN_REVIEW, "qa-bot")
        self.log.append(Event("work_unit.transitioned", "WU-1", {"from": "human_review", "to": "accepted"}, actor_id="lead-2"))
        with self.assertRaises(ReplayError):
            ControlPlane.from_events(self.log.read())

    def test_review_and_escalation_become_tasks(self):
        self._submit("WU-1")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.HUMAN_REVIEW, "qa-bot")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.ESCALATED, "reviewer-1", reason="needs a structural engineer")
        kinds = [task.kind for task in derive_tasks(self.log.read())]
        self.assertIn("work_unit_review", kinds)
        self.assertIn("work_unit_escalation", kinds)

    def _run(self, unit_id):
        if unit_id not in self.plane.work_units:
            self.plane.add_work_unit(unit(work_unit_id=unit_id))
        self.plane.advance_work_unit(unit_id, WorkUnitStatus.READY, "lead-1")
        self.plane.advance_work_unit(unit_id, WorkUnitStatus.RUNNING, "specialist-1")

    def _submit(self, unit_id, *, submitter="specialist-1"):
        self._run(unit_id)
        self.plane.advance_work_unit(unit_id, WorkUnitStatus.MACHINE_QA, submitter, output_ids=(f"{unit_id}-OUT-1",))

    def _accept(self, unit_id, *, corrected_first=False):
        self._submit(unit_id)
        if corrected_first:
            self.plane.advance_work_unit(unit_id, WorkUnitStatus.CORRECTION, "qa-bot", reason="clash at grid C4")
            self.plane.assign_work_unit(unit_id, "specialist-2", "lead-1")
            self.plane.advance_work_unit(unit_id, WorkUnitStatus.READY, "lead-1")
            self.plane.advance_work_unit(unit_id, WorkUnitStatus.RUNNING, "specialist-2")
            self.plane.advance_work_unit(unit_id, WorkUnitStatus.MACHINE_QA, "specialist-2", output_ids=(f"{unit_id}-OUT-2",))
        self.plane.advance_work_unit(unit_id, WorkUnitStatus.HUMAN_REVIEW, "qa-bot")
        self.plane.advance_work_unit(unit_id, WorkUnitStatus.ACCEPTED, "reviewer-1")


if __name__ == "__main__":
    unittest.main()
