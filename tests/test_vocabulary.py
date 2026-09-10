import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.assurance import AssuranceError, evaluate_obligation, resolve_property, validate_obligation
from sfc.models import DeterminationReason, DeterminationStatus, Obligation, ProjectWorld, Quantifier, Requirement, WorldElement
from sfc.requirements import compile_requirement
from sfc.vocabulary import BUNDLED, Term, Vocabulary, default_vocabulary

ROOT = Path(__file__).parents[1]
KERNEL_SOURCE = ROOT / "packages/sfc-core/src/sfc/assurance.py"

PACK = Vocabulary.from_dict({
    "vocabularyId": "test.pack",
    "version": "1",
    "kinds": [{"canonical": "fire_damper", "aliases": ["damper", "IfcDamper", "fire_dampers"]}],
    "properties": [{"canonical": "clear_opening", "dimension": "length", "aliases": ["ClearOpening", "clear_opening_mm"]}],
})


class KernelPurityTests(unittest.TestCase):
    def test_the_kernel_source_names_no_discipline_terms(self) -> None:
        source = KERNEL_SOURCE.read_text(encoding="utf-8").lower()
        for term in ("electrical", "panel", "distributionboard", "clearance", "inches"):
            with self.subTest(term=term):
                self.assertNotIn(term, source, f"the assurance kernel still mentions {term!r}")

    def test_the_default_is_no_domain_vocabulary(self) -> None:
        obligation = Obligation(
            obligation_id="OBL-1",
            requirement=Requirement("REQ-1", "t", "s"),
            quantifier=Quantifier.ALL,
            population={"kind": "fire_damper"},
            predicate={"property": "clear_opening", "operator": ">=", "value": 500, "unit": "mm"},
        )
        world = ProjectWorld("p", (WorldElement("D-1", "damper", {"ClearOpening": {"value": 600, "unit": "mm"}}),))
        # Without a pack the kernel will not assert that damper and fire_damper
        # are the same equipment, so nothing matches and nothing closes.
        bare = evaluate_obligation(obligation, world)
        self.assertEqual(bare.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.EMPTY_POPULATION_UNRESOLVED.value, bare.reasons)
        # With the pack the alias is a declared fact and evaluation proceeds.
        informed = evaluate_obligation(obligation, world, vocabulary=PACK)
        self.assertEqual(informed.status, DeterminationStatus.MET)

    def test_spelling_still_resolves_without_a_pack(self) -> None:
        element = WorldElement("D-1", "damper", {"ClearOpening": 600})
        self.assertEqual(resolve_property(element, "clear_opening"), ("ClearOpening", 600))


class VocabularyTests(unittest.TestCase):
    def test_aliases_resolve_to_one_canonical_term(self) -> None:
        for spelling in ("damper", "IfcDamper", "fire dampers", "FIRE_DAMPER"):
            with self.subTest(spelling=spelling):
                self.assertEqual(PACK.resolve_kind(spelling), "fire_damper")

    def test_an_unknown_term_normalizes_rather_than_guessing(self) -> None:
        self.assertEqual(PACK.resolve_kind("air handling unit"), "airhandlingunit")
        self.assertIsNone(PACK.property_term("air_pressure"))

    def test_declared_dimension_is_available(self) -> None:
        self.assertEqual(PACK.declared_dimension("ClearOpening"), "length")
        self.assertIsNone(PACK.declared_dimension("unlisted"))

    def test_packs_merge_with_the_base_winning(self) -> None:
        other = Vocabulary("other.pack", "2", kinds=(Term("fire_damper", ("smoke_damper",)), Term("pipe", ("IfcPipeSegment",))))
        merged = PACK.merge(other)
        self.assertEqual(merged.resolve_kind("IfcPipeSegment"), "pipe")
        # The base definition of an already-known term is not replaced.
        self.assertEqual(merged.resolve_kind("smoke_damper"), "smokedamper")

    def test_a_pack_round_trips(self) -> None:
        self.assertEqual(Vocabulary.from_dict(PACK.to_dict()).to_dict(), PACK.to_dict())

    def test_a_directory_of_packs_loads_as_one(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text(json.dumps({"vocabularyId": "a", "version": "1", "kinds": [{"canonical": "beam", "aliases": ["IfcBeam"]}]}), encoding="utf-8")
            (root / "b.json").write_text(json.dumps({"vocabularyId": "b", "version": "1", "kinds": [{"canonical": "column", "aliases": ["IfcColumn"]}]}), encoding="utf-8")
            loaded = Vocabulary.load(root)
        self.assertEqual(loaded.resolve_kind("IfcBeam"), "beam")
        self.assertEqual(loaded.resolve_kind("IfcColumn"), "column")

    def test_an_empty_directory_loads_as_the_empty_vocabulary(self) -> None:
        with TemporaryDirectory() as directory:
            self.assertEqual(Vocabulary.load(directory).kinds, ())


class BundledPackTests(unittest.TestCase):
    def test_the_bundled_pack_ships_with_the_package(self) -> None:
        self.assertTrue(BUNDLED.is_dir(), "the vocabularies directory is missing from the package")
        self.assertTrue(sorted(BUNDLED.glob("*.json")), "no bundled vocabulary packs found")

    def test_the_bundled_pack_reconciles_the_two_example_sources(self) -> None:
        vocabulary = default_vocabulary()
        self.assertEqual(
            vocabulary.resolve_kind("electrical_panel"),
            vocabulary.resolve_kind("electricdistributionboard"),
        )
        self.assertEqual(
            vocabulary.resolve_property("working_clearance_inches"),
            vocabulary.resolve_property("WorkingClearance"),
        )

    def test_environment_override_replaces_the_bundled_pack(self) -> None:
        import os

        with TemporaryDirectory() as directory:
            path = Path(directory) / "pack.json"
            path.write_text(json.dumps(PACK.to_dict()), encoding="utf-8")
            previous = os.environ.get("SFC_VOCABULARY_PATH")
            os.environ["SFC_VOCABULARY_PATH"] = str(path)
            try:
                self.assertEqual(default_vocabulary().vocabulary_id, "test.pack")
            finally:
                if previous is None:
                    os.environ.pop("SFC_VOCABULARY_PATH", None)
                else:
                    os.environ["SFC_VOCABULARY_PATH"] = previous


class CompilerVocabularyTests(unittest.TestCase):
    def test_the_compiler_uses_the_injected_pack(self) -> None:
        obligation = compile_requirement("Every fire dampers must have clear opening >= 500 mm", vocabulary=PACK)
        self.assertEqual(obligation.population["kind"], "fire_damper")
        self.assertEqual(obligation.predicate["property"], "clear_opening")

    def test_the_compiler_without_a_pack_keeps_the_authors_words(self) -> None:
        obligation = compile_requirement("Every fire damper must have clear opening >= 500 mm")
        self.assertEqual(obligation.population["kind"], "fire_damper")
        self.assertEqual(obligation.predicate["property"], "clear_opening")

    def test_plural_handling_does_not_need_a_pack(self) -> None:
        obligation = compile_requirement("Every air handling units must have depth >= 500 mm")
        self.assertEqual(obligation.population["kind"], "air_handling_unit")


class ObligationValidationTests(unittest.TestCase):
    def _obligation(self, unit: str) -> Obligation:
        return Obligation(
            obligation_id="OBL-1",
            requirement=Requirement("REQ-1", "t", "s"),
            quantifier=Quantifier.ALL,
            population={"kind": "fire_damper"},
            predicate={"property": "clear_opening", "operator": ">=", "value": 500, "unit": unit},
        )

    def test_a_unit_matching_the_declared_dimension_is_accepted(self) -> None:
        validate_obligation(self._obligation("mm"), PACK)

    def test_a_unit_measuring_the_wrong_thing_is_an_authoring_error(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_obligation(self._obligation("kg"), PACK)
        self.assertIn("length", str(raised.exception))

    def test_without_a_declared_dimension_nothing_is_asserted(self) -> None:
        validate_obligation(self._obligation("kg"))


if __name__ == "__main__":
    unittest.main()
