from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.authority import EvidenceAuthority
from sfc.events import EventLog
from sfc.evidence_room import DocumentState, EvidenceRoom, EvidenceState
from sfc.models import Evidence, EvidenceSourceType


class EvidenceRoomTests(unittest.TestCase):
    def test_document_versions_hash_and_evidence_lifecycle_are_audited(self) -> None:
        with TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.jsonl")
            room = EvidenceRoom(log)
            first = room.add_document_version("drawing-E2.11", "E2.11.pdf", "revision one", uploaded_by="engineer")
            second = room.add_document_version("drawing-E2.11", "E2.11.pdf", "revision two", uploaded_by="engineer")
            self.assertNotEqual(first.content_hash, second.content_hash)
            self.assertEqual(room.all_versions("drawing-E2.11")[0].state, DocumentState.REPLACED)
            evidence = Evidence("EV-1", "drawing-E2.11", EvidenceSourceType.PDF_REGION, {"page": 12, "region": [1, 2, 3, 4]}, "panel is connected", .9, .95, (f"sha256:{second.content_hash}", "page:12"))
            room.add_evidence(evidence, version_id=second.version_id)
            room.submit_for_review("EV-1")
            admitted = room.admit("EV-1", EvidenceAuthority(.8), actor_id="reviewer")
            self.assertEqual(admitted.state, EvidenceState.ADMITTED)
            self.assertTrue(admitted.evidence.admitted)
            with self.assertRaises(ValueError):
                room.admit("EV-1")
            self.assertEqual(len(log.read("EV-1")), 3)
