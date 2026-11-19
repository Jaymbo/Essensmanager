# Planer: halbautomatische Mehrtages-Planung.
# Greedy-Strategie: wählt Rezeptkandidaten, die die Abweichung vom
# Zielbereich (kumulierter Tagesvektor) minimieren, mit Vorrats-Priorität.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import nutrient_space as ns
from .models import MealPlan, PantryItem, PlanEntry, Recipe


@dataclass
class PlanRequest:
    household_id: int
    start_date: date
    days: int = 3
    persons: dict[int, int] | None = None   # person_id -> is_eating (1/0)
    prefer_pantry: bool = True


def _target_arrays(session: Session, person_targets: dict[str, dict]) -> tuple[dict, dict]:
    from .models import NutrientDef
    defs = session.execute(select(NutrientDef)).scalars().all()
    minimum, maximum = {}, {}
    for d in defs:
        ov = (person_targets or {}).get(d.key) or {}
        lo = ov.get("min", d.daily_min)
        hi = ov.get("max", d.daily_max)
        if lo is not None:
            minimum[d.key] = float(lo)
        if hi is not None:
            maximum[d.key] = float(hi)
    return minimum, maximum


class GreedyPlanner:
    """Schlägt pro Tag+Mahlzeit ein Rezept vor. Nutzer bestätigt/passt an."""

    def __init__(self, session: Session):
        self.s = session

    def pantry_expiring_grams(self, household_id: int, until: date) -> dict[int, float]:
        """Ingredient-ID -> Gramm, das vor `until` abläuft (Priorität für Planer)."""
        rows = self.s.execute(select(PantryItem).where(
            PantryItem.household_id == household_id)).scalars().all()
        out: dict[int, float] = {}
        for p in rows:
            if p.expires_on and p.expires_on <= until:
                out[p.ingredient_id] = out.get(p.ingredient_id, 0.0) + p.grams
        return out

    def plan(self, req: PlanRequest, person_targets: dict[str, dict],
             meal_slots: list[str] | None = None) -> MealPlan:
        slots = meal_slots or ["breakfast", "lunch", "dinner"]
        candidates = list(self.s.execute(select(Recipe).where(
            Recipe.household_id == req.household_id)).scalars().all())
        if not candidates:
            raise ValueError("Keine Rezepte vorhanden – erst Rezepte anlegen.")

        from .recipe_engine import RecipeEngine
        eng = RecipeEngine(self.s)
        vectors = {r.id: eng.recipe_vector(r).get("per_serving", {}) for r in candidates}
        expiring = (self.pantry_expiring_grams(req.household_id,
                    req.start_date + timedelta(days=req.days))
                    if req.prefer_pantry else {})

        minimum, maximum = _target_arrays(self.s, person_targets)
        num_eaters = max(sum(1 for v in (req.persons or {}).values() if v), 1)

        plan = MealPlan(household_id=req.household_id,
                        start_date=req.start_date, days=req.days, status="draft")
        self.s.add(plan)

        for day in range(req.days):
            day_vec: dict[str, float] = {}
            for slot in slots:
                best, best_score = None, None
                for r in candidates:
                    v = vectors.get(r.id, {})
                    candidate_vec = ns.add(day_vec, ns.scale(v, num_eaters))
                    score = self._score(candidate_vec, minimum, maximum, r, expiring)
                    if best_score is None or score < best_score:
                        best, best_score = r, score
                if best is None:
                    continue
                used = ns.scale(vectors.get(best.id, {}), num_eaters)
                day_vec = ns.add(day_vec, used)
                self.s.add(PlanEntry(plan=plan, day_index=day, meal_slot=slot,
                                     recipe_id=best.id, persons=num_eaters))
        self.s.commit()
        return plan

    def _score(self, day_vec: dict[str, float], minimum: dict[str, float],
               maximum: dict[str, float], recipe: Recipe,
               expiring: dict[int, float]) -> float:
        """Kleiner = besser. Straft Zielbereichs-Verletzungen; belohnt
        Rezepte, die ablaufende Vorräte verwenden."""
        score = 0.0
        for k, lo in minimum.items():
            v = day_vec.get(k, 0.0)
            if v < lo:
                score += (lo - v) / max(lo, 1e-6)
        for k, hi in maximum.items():
            v = day_vec.get(k, 0.0)
            if v > hi:
                score += (v - hi) / max(hi, 1e-6)
        if expiring:
            recipe_ings = {ln.ingredient_id for ln in recipe.lines}
            hit = sum(g for iid, g in expiring.items() if iid in recipe_ings)
            score -= hit / 1000.0 * 0.1  # bis zu ~1 Punkt je kg ablaufender Ware
        return score
