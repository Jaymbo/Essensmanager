# Rezept-Engine: berechnet Nährstoffvektoren von Rezepten und Zutatenzeilen.
# Nutzt Domain (nutrient_space, processes) + DB-Modelle.

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import nutrient_space as ns
from .domain import processes as proc
from .models import Ingredient, NutrientDef, Process, Recipe


class RecipeEngine:
    def __init__(self, session: Session):
        self.s = session

    def _process_factors(self) -> dict[str, dict[str, float]]:
        rows = self.s.execute(select(Process)).scalars().all()
        return {p.key: dict(p.factors or {}) for p in rows}

    def _ingredients(self, ids: set[int]) -> dict[int, Ingredient]:
        if not ids:
            return {}
        rows = self.s.execute(
            select(Ingredient).where(Ingredient.id.in_(ids))).scalars().all()
        return {i.id: i for i in rows}

    def line_vector(self, line) -> dict[str, float]:
        """Vektor einer Rezeptzeile: per-100g * grams/100, dann Prozesskette."""
        ing = self.s.get(Ingredient, line.ingredient_id)
        if ing is None or not line.grams_raw:
            return {}
        v = ns.per_100g(ing.nutrients or {}, line.grams_raw)
        if line.process_chain:
            factors = self._process_factors()
            chain = [factors[p] for p in line.process_chain if p in factors]
            v = proc.apply_chain(v, chain)
        return v

    def recipe_vector(self, recipe: Recipe, recompute: bool = True) -> dict:
        """Gesamtvektor + pro-Portion-Vektor eines Rezepts."""
        if recipe.nutrient_cache and not recompute:
            return recipe.nutrient_cache
        total: dict[str, float] = {}
        for line in recipe.lines:
            total = ns.add(total, self.line_vector(line))
        servings = max(recipe.servings, 1)
        cache = {
            "total": total,
            "per_serving": ns.scale(total, 1.0 / servings),
        }
        recipe.nutrient_cache = cache
        self.s.commit()
        return cache

    def search(self, household_id: int, query: str = "",
               ingredient_ids: list[int] | None = None,
               process_keys: list[str] | None = None,
               max_carbs: float | None = None,
               min_protein: float | None = None) -> list[Recipe]:
        """Durchsucht Rezepte nach Name, Zutaten, Prozessen, Nährwertgrenzen."""
        stmt = select(Recipe).where(Recipe.household_id == household_id)
        recipes = list(self.s.execute(stmt).scalars().all())
        out = []
        q = (query or "").lower()
        for r in recipes:
            if q and q not in r.name.lower():
                continue
            if ingredient_ids:
                line_ing = {ln.ingredient_id for ln in r.lines}
                if not set(ingredient_ids) <= line_ing:
                    continue
            if process_keys:
                line_proc = {p for ln in r.lines for p in (ln.process_chain or [])}
                if not set(process_keys) <= line_proc:
                    continue
            if (max_carbs is not None or min_protein is not None) and not r.nutrient_cache:
                self.recipe_vector(r)
            cache = r.nutrient_cache or {}
            per = cache.get("per_serving", {})
            if max_carbs is not None and per.get("carbs_g", 0) > max_carbs:
                continue
            if min_protein is not None and per.get("protein_g", 0) < min_protein:
                continue
            out.append(r)
        return out


def compute_meal_vector(session: Session, recipe: Recipe,
                        persons: int) -> dict[str, float]:
    """Vektor, den `persons` Personen aus einem Rezept essen (Gesamtvektor)."""
    eng = RecipeEngine(session)
    cache = eng.recipe_vector(recipe)
    return ns.scale(cache.get("total", {}), persons)


def compute_ingredient_vector(session: Session, ingredient_id: int,
                              grams: float, process_chain: list[str]) -> dict[str, float]:
    ing = session.get(Ingredient, ingredient_id)
    if ing is None:
        return {}
    v = ns.per_100g(ing.nutrients or {}, grams)
    if process_chain:
        factors = {p.key: dict(p.factors or {})
                   for p in session.execute(select(Process)).scalars().all()}
        chain = [factors[p] for p in process_chain if p in factors]
        v = proc.apply_chain(v, chain)
    return v
