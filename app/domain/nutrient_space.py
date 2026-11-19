# Domain-Kern: Nährstoffvektoren und ihre Aggregation.
# Pure Python, kein I/O – wiederverwendbar und testbar.

from __future__ import annotations

from typing import Iterable, Mapping

# Ein Nährstoffvektor ist ein Mapping von nutrient_key -> Wert in der
# Nährstoff-Einheit (mg, µg, g, kcal ...). Fehlende Keys = 0.
NutrientVector = dict[str, float]


def add(*vectors: Mapping[str, float]) -> NutrientVector:
    """Summiert beliebig viele Vektoren komponentenweise."""
    out: NutrientVector = {}
    for v in vectors:
        for k, val in v.items():
            out[k] = out.get(k, 0.0) + val
    return out


def scale(v: Mapping[str, float], factor: float) -> NutrientVector:
    """Skaliert einen Vektor (z.B. Portionierung)."""
    return {k: val * factor for k, val in v.items()}


def per_100g(v: Mapping[str, float], grams: float) -> NutrientVector:
    """Nährwerte von `grams` Gramm einer per-100g-Angabe."""
    if grams <= 0:
        return {}
    return scale(v, grams / 100.0)


def diff_status(actual: Mapping[str, float], minimum: Mapping[str, float],
                maximum: Mapping[str, float]) -> dict[str, str]:
    """Bewertet je Dimension: 'under' / 'in_range' / 'over' / 'no_target'."""
    keys = set(actual) | set(minimum) | set(maximum)
    status: dict[str, str] = {}
    for k in keys:
        lo = minimum.get(k)
        hi = maximum.get(k)
        val = actual.get(k, 0.0)
        if lo is None and hi is None:
            status[k] = "no_target"
        elif lo is not None and val < lo:
            status[k] = "under"
        elif hi is not None and val > hi:
            status[k] = "over"
        else:
            status[k] = "in_range"
    return status


def merge_with_defaults(vectors: Iterable[Mapping[str, float]],
                        defaults: Mapping[str, float] | None = None) -> NutrientVector:
    """Füllt fehlende Dimensionen mit 0 (defaults = alle bekannten Keys)."""
    out: NutrientVector = dict(defaults or {})
    for v in vectors:
        for k, val in v.items():
            out[k] = out.get(k, 0.0) + val
    return out
