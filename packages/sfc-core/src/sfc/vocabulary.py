"""Injected term registry, so the kernel holds no domain knowledge.

The assurance kernel knows Population, Predicate, Observation, Quantity and
Evidence. It does not know what an electrical panel is. Discipline terms and the
spellings a connector may produce for them live in vocabulary packs, which
adapters load and pass in.

Without a pack the kernel still normalizes punctuation and case, because
``WorkingClearance`` and ``working_clearance`` are the same name written two
ways. It will not claim that ``electrical_panel`` and
``electricdistributionboard`` are the same thing, because that is a domain
assertion and belongs in data a reviewer can read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
import json
import os
import re

BUNDLED = Path(__file__).parent / "vocabularies"

#: Environment override for a customer or discipline pack directory or file.
PATH_VARIABLE = "SFC_VOCABULARY_PATH"


def normalize(token: str | None) -> str:
    """Strip syntactic noise. This is spelling, not a claim about meaning."""
    return "" if token is None else re.sub(r"[^a-z0-9]", "", str(token).lower())


@dataclass(frozen=True)
class Term:
    canonical: str
    aliases: tuple[str, ...] = ()
    dimension: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Term":
        return cls(
            canonical=value["canonical"],
            aliases=tuple(value.get("aliases", [])),
            dimension=value.get("dimension"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"canonical": self.canonical}
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        if self.dimension is not None:
            payload["dimension"] = self.dimension
        return payload

    def spellings(self) -> Iterable[str]:
        yield self.canonical
        yield from self.aliases


@dataclass(frozen=True)
class Vocabulary:
    vocabulary_id: str = "sfc.vocabulary.empty"
    version: str = "1"
    kinds: tuple[Term, ...] = ()
    properties: tuple[Term, ...] = ()
    _kind_index: dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    _property_index: dict[str, Term] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        for term in self.kinds:
            for spelling in term.spellings():
                self._kind_index.setdefault(normalize(spelling), term.canonical)
        for term in self.properties:
            for spelling in term.spellings():
                self._property_index.setdefault(normalize(spelling), term)

    @classmethod
    def empty(cls) -> "Vocabulary":
        return cls()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Vocabulary":
        return cls(
            vocabulary_id=value.get("vocabularyId", "sfc.vocabulary.unnamed"),
            version=str(value.get("version", "1")),
            kinds=tuple(Term.from_dict(item) for item in value.get("kinds", [])),
            properties=tuple(Term.from_dict(item) for item in value.get("properties", [])),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Vocabulary":
        source = Path(path)
        if source.is_dir():
            packs = [cls.load(item) for item in sorted(source.glob("*.json"))]
            if not packs:
                return cls.empty()
            merged = packs[0]
            for pack in packs[1:]:
                merged = merged.merge(pack)
            return merged
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "vocabularyId": self.vocabulary_id,
            "version": self.version,
            "kinds": [term.to_dict() for term in self.kinds],
            "properties": [term.to_dict() for term in self.properties],
        }

    def merge(self, other: "Vocabulary") -> "Vocabulary":
        """Combine packs. Earlier terms win, so a base pack is not overridden."""
        return Vocabulary(
            vocabulary_id=f"{self.vocabulary_id}+{other.vocabulary_id}",
            version=f"{self.version}+{other.version}",
            kinds=self.kinds + tuple(term for term in other.kinds if term.canonical not in {item.canonical for item in self.kinds}),
            properties=self.properties + tuple(term for term in other.properties if term.canonical not in {item.canonical for item in self.properties}),
        )

    def resolve_kind(self, token: str | None) -> str:
        """The canonical kind for a spelling, or its normalized form when unknown."""
        normalized = normalize(token)
        return self._kind_index.get(normalized, normalized)

    def resolve_property(self, token: str | None) -> str:
        normalized = normalize(token)
        term = self._property_index.get(normalized)
        return term.canonical if term else normalized

    def property_term(self, token: str | None) -> Term | None:
        return self._property_index.get(normalize(token))

    def declared_dimension(self, token: str | None) -> str | None:
        term = self.property_term(token)
        return term.dimension if term else None


@lru_cache(maxsize=None)
def _load_default(path: str | None) -> Vocabulary:
    return Vocabulary.load(path) if path else Vocabulary.load(BUNDLED)


def default_vocabulary() -> Vocabulary:
    """The pack adapters use unless a caller passes one explicitly.

    ``SFC_VOCABULARY_PATH`` replaces the bundled pack, so a project can supply
    its own discipline terms without a code change.
    """
    override = os.environ.get(PATH_VARIABLE)
    if override:
        return _load_default(override)
    if not BUNDLED.exists():
        return Vocabulary.empty()
    return _load_default(None)
