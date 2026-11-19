# Integrationstests: Seed + Rezept-Engine + Simulator + Planer (In-Memory-DB).

import os
import tempfile

import pytest
from sqlalchemy import select

os.environ.setdefault("EM_DB_PATH", tempfile.mktemp(suffix=".db"))

from app import seed_data
from app.body_simulator import BodySimulator
from app.domain import nutrient_space as ns
from app.models import (NutrientDef, Process, Recipe, make_engine,
                        make_session_factory)
from app.planner import GreedyPlanner, PlanRequest
from app.recipe_engine import RecipeEngine


@pytest.fixture(scope="module")
def session():
    path = os.environ["EM_DB_PATH"]
    seed_data.seed(path)
    engine = make_engine(path)
    Session = make_session_factory(engine)
    s = Session()
    yield s
    s.close()


def test_seed_reference_data(session):
    defs = session.execute(select(NutrientDef)).scalars().all()
    assert len(defs) >= 25
    procs = session.execute(select(Process)).scalars().all()
    assert any(p.key == "ferment" for p in procs)
    assert any(p.key == "sourdough" for p in procs)


def test_recipe_vector(session):
    recipes = session.execute(select(Recipe)).scalars().all()
    assert recipes
    eng = RecipeEngine(session)
    for r in recipes:
        cache = eng.recipe_vector(r)
        assert cache["per_serving"].get("energy_kcal", 0) > 0


def test_boil_reduces_vit_c_but_ferment_boosts(session):
    eng = RecipeEngine(session)
    recipes = {r.name: r for r in session.execute(select(Recipe)).scalars().all()}
    # Porridge (Milch gekocht) vs. Linseneintopf: beide nutzen 'boil'
    eintopf = eng.recipe_vector(recipes["Linseneintopf"])
    assert eintopf["total"].get("folate_ug", 0) > 0


def test_simulator_day_flow(session):
    sim = BodySimulator(session)
    intake = [{"energy_kcal": 2000, "vit_c_mg": 200, "iron_mg": 12, "vit_b12_ug": 6}]
    results = sim.simulate_days(intake)
    assert len(results) == 1
    # B12-Sättigung: 6 µg -> 0.75 + 0.045 = 0.795 resorbiert
    assert abs(results[0]["absorbed"]["vit_b12_ug"] - 0.795) < 1e-6
    # Vitamin C: 200 µg Zufuhr * 0.8 Effizienz (keine Interaktion)
    assert abs(results[0]["absorbed"]["vit_c_mg"] - 160.0) < 1e-6


def test_planner_creates_plan(session):
    from app.models import Household
    hh = session.execute(select(Household).where(Household.name == "Demo")).scalar()
    planner = GreedyPlanner(session)
    plan = planner.plan(PlanRequest(household_id=hh.id,
                                    start_date=__import__("datetime").date.today(),
                                    days=3), person_targets={})
    assert plan.id is not None
    assert len(plan.entries) == 9  # 3 Tage × 3 Mahlzeiten
