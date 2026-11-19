# Domain-Kern: Kochprozesse als Retentionsfaktor-Transformationen.
# Pure Python, kein I/O.

from __future__ import annotations

from typing import Mapping

from .nutrient_space import NutrientVector

# process_key -> {nutrient_key: Retentionsfaktor}
# Fehlende Keys bleiben unverändert (Faktor 1.0). Faktoren > 1 sind erlaubt
# (z.B. Fermentieren erzeugt B-Vitamine).
ProcessTable = dict[str, dict[str, float]]


def apply_process(v: Mapping[str, float], factors: Mapping[str, float]) -> NutrientVector:
    """Wendet einen Prozess (Faktor-Map) komponentenweise an."""
    return {k: val * factors.get(k, 1.0) for k, val in v.items()}


def apply_chain(v: Mapping[str, float], chain: list[Mapping[str, float]]) -> NutrientVector:
    """Wendet eine Prozesskette in Reihenfolge an (raw -> fry -> bake)."""
    cur: NutrientVector = dict(v)
    for factors in chain:
        cur = apply_process(cur, factors)
    return cur
