"""A work unit is governed production work, not a task with a status field."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.activity import derive_tasks
from sfc.conformance import ConformanceError, validate_semantics
from sfc.control_plane import ControlPlane, ReplayError
from sfc.events import Event, EventLog
from sfc.lifecycle import WorkPackage
from sfc.quantities import Quantity
from sfc.work import (
    AcceptanceCriterion,
    AutonomyClass,
    ExecutorKind,
    ExecutorPolicy,
    ExpectedOutput,
    InputRef,
    WorkUnit,
    WorkUnitError,
    WorkUnitStatus,
)


def feeder_unit(unit_id: str = "WU-1", *, depends_on: tuple[str, ...] = (), **changes) -> WorkUnit:
    values = dict(
        work_unit_id=unit_id,
        title="Route L03 overhead feeders",
        capability="electrical.route.feeder",
        discipline="electrical",
        location="L03",
        inputs=(InputRef("E-301", "IFC"), InputRef("ASI-2", None)),
        obligation_ids=("OBL-1",),
        depends_on=depends_on,
        executor_policy=ExecutorPolicy((ExecutorKind.HUMAN, ExecutorKind.SOLVER), AutonomyClass.SUPERVISED),
        expected_outputs=(ExpectedOutput("revit_model", "Coordinated feeder conduit"),),
        acceptance_criteria=(AcceptanceCriterion("AC-1", "No hard clashes with structure", None),),
        estimated_effort=Quantity(12.0, "h"),
    )
    values.update(changes)
    return WorkUnit(**values)


def started(unit: WorkUnit) -> WorkUnit:
    return (
        unit.advance(WorkUnitStatus.READY, "lead-1")
        .assign(ExecutorKind.HUMAN, "modeler-1")
        .advance(WorkUnitStatus.IN_PROGRESS, "modeler-1")
    )


class WorkUnitLifecycleTests(unittest.TestCase):
    def test_the_happy_path_closes_with_a_separate_acceptor(self) -> None:
        unit = started(feeder_unit())
        self.assertEqual(unit.attempt, 1)
        unit = unit.advance(WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        unit = unit.advance(WorkUnitStatus.ACCEPTED, "reviewer-1")
        self.assertIs(unit.status, WorkUnitStatus.ACCEPTED)
        self.assertEqual((unit.submitted_by, unit.accepted_by), ("modeler-1", "reviewer-1"))
        self.assertEqual(list(validate_semantics_errors(unit)), [])

    def test_skipped_states_are_refused(self) -> None:
        with self.assertRaises(WorkUnitError):
            feeder_unit().advance(WorkUnitStatus.IN_PROGRESS, "lead-1")
        with self.assertRaises(WorkUnitError):
            feeder_unit().advance(WorkUnitStatus.ACCEPTED, "lead-1")

    def test_every_transition_names_its_actor(self) -> None:
        with self.assertRaises(WorkUnitError):
            feeder_unit().advance(WorkUnitStatus.READY, "")

    def test_work_cannot_start_unassigned(self) -> None:
        ready = feeder_unit().advance(WorkUnitStatus.READY, "lead-1")
        with self.assertRaisesRegex(WorkUnitError, "assigned executor"):
            ready.advance(WorkUnitStatus.IN_PROGRESS, "lead-1")

    def test_the_executor_policy_limits_who_may_be_assigned(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "not allowed"):
            feeder_unit().assign(ExecutorKind.LLM, "model-1")

    def test_an_executor_cannot_be_swapped_mid_attempt(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "cannot reassign"):
            started(feeder_unit()).assign(ExecutorKind.SOLVER, "router-1")

    def test_a_submission_must_name_its_outputs(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "outputs"):
            started(feeder_unit()).advance(WorkUnitStatus.SUBMITTED, "modeler-1")
        with self.assertRaisesRegex(WorkUnitError, "unique"):
            started(feeder_unit()).advance(WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("A", "A"))

    def test_outputs_are_recorded_only_on_submission(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "only on submission"):
            feeder_unit().advance(WorkUnitStatus.READY, "lead-1", output_ids=("OUT-1",))

    def test_the_submitter_cannot_accept_its_own_work(self) -> None:
        submitted = started(feeder_unit()).advance(WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        with self.assertRaisesRegex(WorkUnitError, "cannot accept"):
            submitted.advance(WorkUnitStatus.ACCEPTED, "modeler-1")

    def test_rejection_block_and_cancellation_must_say_why(self) -> None:
        submitted = started(feeder_unit()).advance(WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        for target, unit in (
            (WorkUnitStatus.REJECTED, submitted),
            (WorkUnitStatus.BLOCKED, feeder_unit()),
            (WorkUnitStatus.CANCELLED, feeder_unit()),
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(WorkUnitError, "reason"):
                    unit.advance(target, "reviewer-1")

    def test_rework_is_a_new_attempt_that_starts_clean(self) -> None:
        submitted = started(feeder_unit()).advance(WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        rejected = submitted.advance(WorkUnitStatus.REJECTED, "reviewer-1", reason="tray clashes with duct at grid C4")
        # The rejected unit still names what was refused.
        self.assertEqual(rejected.output_ids, ("OUT-1",))
        self.assertEqual(list(validate_semantics_errors(rejected)), [])
        reworked = rejected.advance(WorkUnitStatus.IN_PROGRESS, "modeler-1")
        self.assertEqual(reworked.attempt, 2)
        self.assertEqual(reworked.output_ids, ())
        self.assertIsNone(reworked.submitted_by)

    def test_a_blocked_unit_returns_through_ready(self) -> None:
        blocked = feeder_unit().advance(WorkUnitStatus.BLOCKED, "lead-1", reason="waiting on ASI-3")
        self.assertEqual(blocked.status_reason, "waiting on ASI-3")
        ready = blocked.advance(WorkUnitStatus.READY, "lead-1")
        self.assertIsNone(ready.status_reason)

    def test_the_contract_round_trips(self) -> None:
        unit = started(feeder_unit())
        self.assertEqual(WorkUnit.from_dict(unit.to_dict()).to_dict(), unit.to_dict())

    def test_an_unestimated_unit_is_not_a_zero_hour_unit(self) -> None:
        document = feeder_unit(estimated_effort=None).to_dict()
        self.assertIsNone(document["estimatedEffort"])
        self.assertIsNone(WorkUnit.from_dict(document).estimated_effort)


def validate_semantics_errors(unit: WorkUnit):
    try:
        validate_semantics("work-unit.schema.json", unit.to_dict())
    except ConformanceError as error:
        return error.violations
    return ()


class WorkUnitConformanceTests(unittest.TestCase):
    def violations(self, **overrides) -> tuple[str, ...]:
        document = feeder_unit().to_dict()
        document.update(overrides)
        try:
            validate_semantics("work-unit.schema.json", document)
        except ConformanceError as error:
            return error.violations
        return ()

    def test_a_valid_plan_has_no_violations(self) -> None:
        self.assertEqual(self.violations(), ())

    def test_each_invariant_is_enforced(self) -> None:
        cases = {
            "dotted identifier": {"capability": "RouteFeeder"},
            "depend on itself": {"dependsOn": ["WU-1"]},
            "repeats a work unit": {"dependsOn": ["WU-0", "WU-0"]},
            "criterion identifiers": {"acceptanceCriteria": [
                {"criterionId": "AC-1", "statement": "a", "obligationId": None},
                {"criterionId": "AC-1", "statement": "b", "obligationId": None},
            ]},
            "unit of time": {"estimatedEffort": {"value": 3, "unit": "m"}},
            "not a known unit": {"estimatedEffort": {"value": 3, "unit": "fortnight"}},
            "cannot be negative": {"estimatedEffort": {"value": -1, "unit": "h"}},
            "not allowed by the executor policy": {"assignee": {"kind": "llm", "executorId": "m-1"}},
            "assigned executor": {"status": "in_progress", "attempt": 1},
            "at least one attempt": {"status": "in_progress", "assignee": {"kind": "human", "executorId": "a"}},
            "must name its outputs": {"status": "submitted", "attempt": 1, "submittedBy": "a",
                                      "assignee": {"kind": "human", "executorId": "a"}},
            "who submitted it": {"status": "submitted", "attempt": 1, "outputIds": ["O-1"],
                                 "assignee": {"kind": "human", "executorId": "a"}},
            "has not submitted": {"outputIds": ["O-1"]},
            "repeats an output": {"status": "submitted", "attempt": 1, "outputIds": ["O", "O"], "submittedBy": "a",
                                  "assignee": {"kind": "human", "executorId": "a"}},
            "who accepted it": {"status": "accepted", "attempt": 1, "outputIds": ["O"], "submittedBy": "a",
                                "assignee": {"kind": "human", "executorId": "a"}},
            "actor who submitted": {"status": "accepted", "attempt": 1, "outputIds": ["O"], "submittedBy": "a",
                                    "acceptedBy": "a", "assignee": {"kind": "human", "executorId": "a"}},
            "cannot record an acceptance": {"acceptedBy": "r"},
            "state its reason": {"status": "blocked"},
        }
        for fragment, overrides in cases.items():
            with self.subTest(fragment):
                found = self.violations(**overrides)
                self.assertTrue(any(fragment in violation for violation in found), found)


class WorkGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = EventLog(Path(self.directory.name) / "events.jsonl")
        self.plane = ControlPlane(event_log=self.log)
        self.plane.add_work_package(WorkPackage("WP-L03", "L03 electrical overhead", ("OBL-1",)))

    def test_dependencies_must_already_be_planned(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "unplanned"):
            self.plane.add_work_unit(feeder_unit("WU-2", depends_on=("WU-1",)))

    def test_the_work_package_must_exist(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "unknown work package"):
            self.plane.add_work_unit(feeder_unit(work_package_id="WP-X"))

    def test_units_enter_planned_and_valid(self) -> None:
        with self.assertRaisesRegex(WorkUnitError, "enters the plane"):
            self.plane.add_work_unit(started(feeder_unit()))
        with self.assertRaisesRegex(WorkUnitError, "dotted identifier"):
            self.plane.add_work_unit(feeder_unit(capability="route"))
        self.plane.add_work_unit(feeder_unit())
        with self.assertRaisesRegex(WorkUnitError, "already exists"):
            self.plane.add_work_unit(feeder_unit())

    def test_a_unit_is_not_ready_until_its_dependencies_are_accepted(self) -> None:
        self.plane.add_work_unit(feeder_unit("WU-1", work_package_id="WP-L03"))
        self.plane.add_work_unit(feeder_unit("WU-2", depends_on=("WU-1",), capability="electrical.detail.hanger"))
        with self.assertRaisesRegex(WorkUnitError, "waiting on WU-1"):
            self.plane.advance_work_unit("WU-2", WorkUnitStatus.READY, "lead-1")
        self._deliver("WU-1")
        self.assertEqual(self.plane.unaccepted_dependencies("WU-2"), ())
        self.plane.advance_work_unit("WU-2", WorkUnitStatus.READY, "lead-1")

    def test_replay_reproduces_the_work_graph(self) -> None:
        self.plane.add_work_unit(feeder_unit("WU-1", work_package_id="WP-L03"))
        self.plane.add_work_unit(feeder_unit("WU-2", depends_on=("WU-1",)))
        self._deliver("WU-1", rejected_first=True)
        replayed = ControlPlane.from_events(self.log.read())
        self.assertEqual(replayed.state(), self.plane.state())
        self.assertEqual(replayed.work_units["WU-1"].attempt, 2)

    def test_replay_refuses_a_log_where_the_submitter_accepts(self) -> None:
        self.plane.add_work_unit(feeder_unit())
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.READY, "lead-1")
        self.plane.assign_work_unit("WU-1", ExecutorKind.HUMAN, "modeler-1", "lead-1")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.IN_PROGRESS, "modeler-1")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        self.log.append(Event("work_unit.transitioned", "WU-1", {"from": "submitted", "to": "accepted"}, actor_id="modeler-1"))
        with self.assertRaises(ReplayError):
            ControlPlane.from_events(self.log.read())

    def test_submitted_work_becomes_a_review_task(self) -> None:
        self.plane.add_work_unit(feeder_unit())
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.READY, "lead-1")
        self.plane.assign_work_unit("WU-1", ExecutorKind.HUMAN, "modeler-1", "lead-1")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.IN_PROGRESS, "modeler-1")
        self.plane.advance_work_unit("WU-1", WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=("OUT-1",))
        kinds = [task.kind for task in derive_tasks(self.log.read())]
        self.assertIn("work_unit_review", kinds)

    def _deliver(self, unit_id: str, *, rejected_first: bool = False) -> None:
        plane = self.plane
        plane.advance_work_unit(unit_id, WorkUnitStatus.READY, "lead-1")
        plane.assign_work_unit(unit_id, ExecutorKind.HUMAN, "modeler-1", "lead-1")
        plane.advance_work_unit(unit_id, WorkUnitStatus.IN_PROGRESS, "modeler-1")
        plane.advance_work_unit(unit_id, WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=(f"{unit_id}-OUT-1",))
        if rejected_first:
            plane.advance_work_unit(unit_id, WorkUnitStatus.REJECTED, "reviewer-1", reason="clash at grid C4")
            plane.advance_work_unit(unit_id, WorkUnitStatus.IN_PROGRESS, "modeler-1")
            plane.advance_work_unit(unit_id, WorkUnitStatus.SUBMITTED, "modeler-1", output_ids=(f"{unit_id}-OUT-2",))
        plane.advance_work_unit(unit_id, WorkUnitStatus.ACCEPTED, "reviewer-1")


if __name__ == "__main__":
    unittest.main()
