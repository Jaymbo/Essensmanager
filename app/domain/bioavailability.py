# Domain-Kern: Bioverfügbarkeit.
# Drei Stufen: Interaktions-Matrix -> Sättigungskinetik -> Speicher-Pools.
# Pure Python, kein I/O. Formeln mit Quellenangaben (siehe seed_data).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# Stoffe, die mit der gesamten Mahlzeit ankommen und Interaktionen steuern.
COMPOUND_KEYS = ("phytate_g", "oxalate_g", "tannin_g",
                 "animal_protein_g", "vit_c_mg", "fat_g", "calcium_mg")


@dataclass
class InteractionRule:
    """EineInteraktionsregel: modifiers einer Nährstoff-Aufnahme.

    target: Nährstoff-Key, dessen Aufnahme modifiziert wird.
    kind: 'enhancer' | 'inhibitor'
    compound: Stoff-Key (aus COMPOUND_KEYS), der die Wirkung steuert.
    effect: max. relativer Effekt (0.9 = bis zu +90 %, -0.55 = bis zu -55 %).
    half_saturation: compound-Menge, bei der die halbe Maximalwirkung eintritt.
    source: Literaturangabe.
    """
    target: str
    kind: str
    compound: str
    effect: float
    half_saturation: float
    source: str


def _sigmoid_factor(amount: float, half: float) -> float:
    """Sättigungskurve: 0 bei amount=0, -> 1 für große Mengen.
    Faktor min(amount/half, 1) mit weichem Übergang."""
    if amount <= 0 or half <= 0:
        return 0.0
    x = amount / half
    return x / (1.0 + x) * 2.0  # 0.5 bei x=1, -> 2 asymptotisch? Nein: siehe unten


def _sat(amount: float, half: float) -> float:
    """Michaelis-Menten-artig, normiert auf 1: min-Wert 0, asymptotisch 1."""
    if amount <= 0 or half <= 0:
        return 0.0
    return amount / (amount + half) * 2.0


def interaction_factor(rules: Sequence[InteractionRule],
                       nutrient_key: str,
                       meal: Mapping[str, float]) -> float:
    """Gesamtfaktor (multiplikativ) aller Regeln, die `nutrient_key` betreffen."""
    f = 1.0
    for r in rules:
        if r.target != nutrient_key:
            continue
        amount = meal.get(r.compound, 0.0)
        s = _sat(amount, r.half_saturation)  # 0..1
        if r.kind == "inhibitor":
            f *= 1.0 + r.effect * s      # effect negativ
        else:
            f *= 1.0 + r.effect * s      # effect positiv
    return f


def b12_absorbed(intake_ug: float) -> float:
    """B12: aktiver IF-Transport gesättigt bei ~1.5 µg/Mahlzeit (Aufnahme ~50 %),
    darüber passiv ~1 %.
    Quelle: NIH Office of Dietary Supplements; Berlin et al. 2004."""
    if intake_ug <= 0:
        return 0.0
    active = min(intake_ug, 1.5) * 0.50
    passive = max(intake_ug - 1.5, 0.0) * 0.01
    return active + passive


def absorb(nutrient_key: str, intake: float,
           base_efficiency: float,
           rules: Sequence[InteractionRule],
           meal: Mapping[str, float]) -> float:
    """Resorbierte Menge eines Nährstoffs aus einer Mahlzeit."""
    if intake <= 0:
        return 0.0
    f = interaction_factor(rules, nutrient_key, meal)
    if nutrient_key == "vit_b12_ug":
        # Sättigungskinetik (IF-Transport) überschreibt lineare Resorption.
        return b12_absorbed(intake * base_efficiency)
    return intake * base_efficiency * f


@dataclass
class PoolState:
    """Speicher-Pool eines Nährstoffs im Körper."""
    amounts: dict[str, float] = field(default_factory=dict)

    def step(self, absorbed: Mapping[str, float],
             half_lives: Mapping[str, float | None],
             capacities: Mapping[str, float | None]) -> dict[str, float]:
        """Ein Tag: Zerfall nach Halbwertszeit (für ALLE vorhandenen Pools)
        + Zufuhr. Gibt Poolstände zurück."""
        keys = set(self.amounts) | set(absorbed)
        for k in keys:
            hl = half_lives.get(k)
            cur = self.amounts.get(k, 0.0)
            if hl:
                cur *= 0.5 ** (1.0 / hl)
            cur += absorbed.get(k, 0.0)
            cap = capacities.get(k)
            if cap:
                cur = min(cur, cap)
            self.amounts[k] = cur
        return dict(self.amounts)
