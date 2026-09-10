"""Measurements as domain objects: value, unit and dimension travel together.

A number without a unit is not a measurement. This module keeps the unit
attached to the value through parsing, conversion and comparison, so a
determination can never compare 29.4 against 36 without knowing what either
number measures. Unresolved units are surfaced as errors rather than silently
treated as compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
import math
import re


class Dimension(StrEnum):
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"
    ANGLE = "angle"
    MASS = "mass"
    TIME = "time"


#: Canonical symbol -> (dimension, factor to the dimension's base unit).
UNITS: dict[str, tuple[Dimension, float]] = {
    "m": (Dimension.LENGTH, 1.0),
    "mm": (Dimension.LENGTH, 1e-3),
    "cm": (Dimension.LENGTH, 1e-2),
    "dm": (Dimension.LENGTH, 1e-1),
    "km": (Dimension.LENGTH, 1e3),
    "in": (Dimension.LENGTH, 0.0254),
    "ft": (Dimension.LENGTH, 0.3048),
    "yd": (Dimension.LENGTH, 0.9144),
    "mi": (Dimension.LENGTH, 1609.344),
    "m2": (Dimension.AREA, 1.0),
    "mm2": (Dimension.AREA, 1e-6),
    "cm2": (Dimension.AREA, 1e-4),
    "km2": (Dimension.AREA, 1e6),
    "in2": (Dimension.AREA, 0.00064516),
    "ft2": (Dimension.AREA, 0.09290304),
    "yd2": (Dimension.AREA, 0.83612736),
    "m3": (Dimension.VOLUME, 1.0),
    "mm3": (Dimension.VOLUME, 1e-9),
    "cm3": (Dimension.VOLUME, 1e-6),
    "l": (Dimension.VOLUME, 1e-3),
    "ml": (Dimension.VOLUME, 1e-6),
    "in3": (Dimension.VOLUME, 1.6387064e-5),
    "ft3": (Dimension.VOLUME, 0.028316846592),
    "rad": (Dimension.ANGLE, 1.0),
    "deg": (Dimension.ANGLE, math.pi / 180),
    "grad": (Dimension.ANGLE, math.pi / 200),
    "kg": (Dimension.MASS, 1.0),
    "g": (Dimension.MASS, 1e-3),
    "mg": (Dimension.MASS, 1e-6),
    "t": (Dimension.MASS, 1e3),
    "lb": (Dimension.MASS, 0.45359237),
    "oz": (Dimension.MASS, 0.028349523125),
    "s": (Dimension.TIME, 1.0),
    "min": (Dimension.TIME, 60.0),
    "h": (Dimension.TIME, 3600.0),
    "d": (Dimension.TIME, 86400.0),
}

#: Spellings that resolve to a canonical symbol, including IFC SI unit names.
ALIASES: dict[str, str] = {
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm", "milli metre": "mm",
    "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm", "centi metre": "cm",
    "decimeter": "dm", "decimetre": "dm", "deci metre": "dm",
    "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km", "kilo metre": "km",
    "inch": "in", "inches": "in", '"': "in", "''": "in",
    "foot": "ft", "feet": "ft", "'": "ft",
    "yard": "yd", "yards": "yd",
    "mile": "mi", "miles": "mi",
    "sqm": "m2", "square meter": "m2", "square meters": "m2", "square metre": "m2", "square metres": "m2",
    "square millimeter": "mm2", "square millimetre": "mm2",
    "square inch": "in2", "square inches": "in2", "sqin": "in2",
    "square foot": "ft2", "square feet": "ft2", "sqft": "ft2",
    "cubic meter": "m3", "cubic metre": "m3", "cubic metres": "m3", "cbm": "m3",
    "cubic inch": "in3", "cubic inches": "in3",
    "cubic foot": "ft3", "cubic feet": "ft3",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "milliliter": "ml", "millilitre": "ml",
    "radian": "rad", "radians": "rad",
    "degree": "deg", "degrees": "deg",
    "gradian": "grad", "gradians": "grad",
    "kilogram": "kg", "kilograms": "kg", "kilogramme": "kg",
    "gram": "g", "grams": "g", "gramme": "g",
    "milligram": "mg", "milligrams": "mg",
    "tonne": "t", "tonnes": "t", "metric ton": "t",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    "ounce": "oz", "ounces": "oz",
    "second": "s", "seconds": "s", "sec": "s",
    "minute": "min", "minutes": "min",
    "hour": "h", "hours": "h", "hr": "h",
    "day": "d", "days": "d",
}

_SUPERSCRIPTS = {"²": "2", "³": "3"}
_QUANTITY_RE = re.compile(r"^\s*(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?)\s*(?P<unit>.*?)\s*$")


class MeasurementError(ValueError):
    """Base class for comparisons that must not be decided numerically."""

    reason = "PREDICATE_NOT_EVALUABLE"


class UnknownUnitError(MeasurementError):
    reason = "UNKNOWN_MEASUREMENT_UNIT"


class UnresolvedUnitError(MeasurementError):
    reason = "UNRESOLVED_MEASUREMENT_UNIT"


class IncompatibleDimensionError(MeasurementError):
    reason = "INCOMPATIBLE_MEASUREMENT_DIMENSION"


def normalize_unit_token(token: str) -> str:
    text = str(token).strip().lower().rstrip(".")
    for superscript, digit in _SUPERSCRIPTS.items():
        text = text.replace(superscript, digit)
    text = re.sub(r"\s*\^\s*", "", text)
    text = re.sub(r"[\s_-]+", " ", text).strip()
    return text


def resolve_unit(token: str | None) -> str | None:
    """Return the canonical symbol for a unit token, or None when none was declared.

    A token that is present but not in the registry raises rather than
    degrading to dimensionless, because an unrecognized unit is a gap in the
    measurement model and not an absence of one.
    """
    if token is None:
        return None
    text = normalize_unit_token(token)
    if not text:
        return None
    if text in UNITS:
        return text
    collapsed = text.replace(" ", "")
    if collapsed in UNITS:
        return collapsed
    if text in ALIASES:
        return ALIASES[text]
    if collapsed in ALIASES:
        return ALIASES[collapsed]
    raise UnknownUnitError(f"unrecognized measurement unit: {token!r}")


def dimension_of(unit: str) -> Dimension:
    try:
        return UNITS[unit][0]
    except KeyError as error:
        raise UnknownUnitError(f"unrecognized measurement unit: {unit!r}") from error


@dataclass(frozen=True)
class Quantity:
    """A numeric value with the unit it was measured in.

    ``unit`` is None when the source declared no unit. Such a quantity is
    *unresolved*, not dimensionless: it may only be compared against another
    unresolved quantity, and never against one carrying a real unit.
    """

    value: float
    unit: str | None = None
    provenance: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise MeasurementError(f"a quantity value must be numeric, got {self.value!r}")
        if self.unit is not None and self.unit not in UNITS:
            raise UnknownUnitError(f"unrecognized measurement unit: {self.unit!r}")

    @property
    def resolved(self) -> bool:
        return self.unit is not None

    @property
    def dimension(self) -> Dimension | None:
        return None if self.unit is None else dimension_of(self.unit)

    @classmethod
    def parse(cls, value: Any, unit: str | None = None, *, provenance: str | None = None) -> "Quantity | None":
        """Build a Quantity from a scalar, a ``{value, unit}`` mapping or a string.

        Returns None when the value is not a measurement at all — a boolean, a
        label, a missing value — so callers can compare those directly.
        """
        declared = resolve_unit(unit)
        if isinstance(value, Quantity):
            return value if declared is None else value.to(declared)
        if isinstance(value, dict):
            if "value" not in value:
                return None
            inner = value["value"]
            if isinstance(inner, bool) or not isinstance(inner, (int, float)):
                return None
            return cls(float(inner), resolve_unit(value.get("unit")) or declared, value.get("provenance") or provenance)
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return cls(float(value), declared, provenance)
        if isinstance(value, str):
            match = _QUANTITY_RE.match(value)
            if not match:
                return None
            parsed_unit = resolve_unit(match.group("unit")) or declared
            return cls(float(match.group("value")), parsed_unit, provenance)
        return None

    def to(self, unit: str) -> "Quantity":
        target = resolve_unit(unit)
        if target is None:
            raise UnresolvedUnitError("cannot convert to an undeclared unit")
        if self.unit is None:
            raise UnresolvedUnitError(f"cannot convert an undeclared unit to {target}")
        if self.unit == target:
            return self
        source_dimension, source_factor = UNITS[self.unit]
        target_dimension, target_factor = UNITS[target]
        if source_dimension is not target_dimension:
            raise IncompatibleDimensionError(f"cannot convert {source_dimension.value} to {target_dimension.value}")
        return Quantity(self.value * source_factor / target_factor, target, self.provenance)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": self.value, "unit": self.unit}
        dimension = self.dimension
        payload["dimension"] = None if dimension is None else dimension.value
        if self.provenance is not None:
            payload["provenance"] = self.provenance
        return payload

    def __str__(self) -> str:
        formatted = f"{self.value:g}"
        return formatted if self.unit is None else f"{formatted} {self.unit}"


@dataclass(frozen=True)
class Conversion:
    """The audit trail of a single normalization, from raw source to comparison."""

    raw: Quantity
    normalized: Quantity

    @property
    def factor(self) -> float | None:
        if self.raw.value == 0 or not self.raw.resolved:
            return None
        return self.normalized.value / self.raw.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawValue": self.raw.value,
            "rawUnit": self.raw.unit,
            "normalizedValue": self.normalized.value,
            "normalizedUnit": self.normalized.unit,
            "dimension": None if self.normalized.dimension is None else self.normalized.dimension.value,
            "conversion": self.factor,
            "source": self.raw.provenance,
        }


def normalize_for_comparison(observed: Quantity, expected: Quantity) -> Conversion:
    """Bring an observation into the unit the requirement is written in.

    Raises when the two sides cannot be compared: exactly one side carries a
    unit, or the units measure different dimensions.
    """
    if observed.resolved != expected.resolved:
        undeclared = "observation" if not observed.resolved else "requirement"
        raise UnresolvedUnitError(
            f"cannot compare {observed} against {expected}: the {undeclared} declares no unit"
        )
    if not observed.resolved:
        return Conversion(observed, observed)
    if observed.dimension is not expected.dimension:
        raise IncompatibleDimensionError(
            f"cannot compare {observed.dimension.value} against {expected.dimension.value}"
        )
    return Conversion(observed, observed.to(expected.unit))


#: Relative tolerance applied to converted measurements. Unit conversion is not
#: exact in binary floating point: 36 in normalized to metres and back does not
#: land on 36.0, so a strict comparison would reject a value that is equal in
#: the engineering sense.
DEFAULT_RELATIVE_TOLERANCE = 1e-9


def compare_values(observed: float, operator: str, expected: float, *, relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE) -> bool:
    """Compare two measurements in the same unit, tolerant of conversion noise."""
    equal = math.isclose(observed, expected, rel_tol=relative_tolerance, abs_tol=0.0)
    if operator == "==":
        return equal
    if operator == "!=":
        return not equal
    if operator == ">=":
        return equal or observed > expected
    if operator == "<=":
        return equal or observed < expected
    if operator == ">":
        return not equal and observed > expected
    if operator == "<":
        return not equal and observed < expected
    raise ValueError(f"unsupported predicate operator: {operator}")
