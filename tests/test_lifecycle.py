import unittest

from sfc.lifecycle import (
    ObligationStatus,
    WorkPackage,
    WorkPackageStatus,
    transition,
    OBLIGATION_TRANSITIONS,
)


class LifecycleTests(unittest.TestCase):
    def test_work_package_cannot_skip_review_states(self) -> None:
        package = WorkPackage("wp-1", "Panel verification", ("obl-1",))
        with self.assertRaises(ValueError):
            package.advance(WorkPackageStatus.APPROVED)
        package = package.advance(WorkPackageStatus.IN_PROGRESS)
        self.assertEqual(package.status, WorkPackageStatus.IN_PROGRESS)

    def test_obligation_transition_graph_is_sequential(self) -> None:
        self.assertEqual(
            transition(ObligationStatus.DISCOVERED, ObligationStatus.CLASSIFIED, OBLIGATION_TRANSITIONS),
            ObligationStatus.CLASSIFIED,
        )
        with self.assertRaises(ValueError):
            transition(ObligationStatus.DISCOVERED, ObligationStatus.APPROVED, OBLIGATION_TRANSITIONS)

