# Tests für den Rezept-Import (Mengen-Schätzung, Normalisierung, Matching).

import csv
import io
import os
import tempfile

os.environ.setdefault("EM_DB_PATH", tempfile.mktemp(suffix=".db"))

from app.recipe_importer import (build_lookup, estimate_grams,
                                 import_raw_recipes_csv,
                                 match_ingredient, normalize_ingredient,
                                 parse_quantity)


def _session_with_ingredients():
    from app.models import Base, Ingredient, make_engine, make_session_factory
    path = tempfile.mktemp(suffix=".db")
    engine = make_engine(path)
    Base.metadata.create_all(engine)
    Session = make_session_factory(engine)
    s = Session()
    s.add(Ingredient(household_id=None, name="flour", nutrients={}))
    s.add(Ingredient(household_id=None, name="eggs", nutrients={}))
    s.add(Ingredient(household_id=None, name="milk, whole", nutrients={}))
    s.add(Ingredient(household_id=None, name="butter, salted", nutrients={}))
    s.commit()
    return s


def test_parse_quantity_fractions():
    grams, qty, rest = parse_quantity("1 1/2 cups flour")
    assert abs(qty - 1.5) < 1e-9
    assert grams == 240.0
    assert rest == "flour"
    grams, qty, rest = parse_quantity("2 tbsp butter")
    assert abs(qty - 2.0) < 1e-9 and grams == 15.0


def test_parse_quantity_no_unit():
    grams, qty, rest = parse_quantity("3 eggs")
    assert grams is None and abs(qty - 3.0) < 1e-9


def test_estimate_grams_with_units():
    assert estimate_grams("2 cups milk") == 480.0
    assert estimate_grams("1 stick butter") == 113.0


def test_estimate_grams_items_and_defaults():
    assert estimate_grams("3 eggs") == 150.0   # 3 * 50
    assert estimate_grams("salt") == 3.0
    assert estimate_grams("unknown exotic fruit") == 100.0


def test_normalize_ingredient():
    assert normalize_ingredient("2 cups all-purpose flour") == "all purpose flour"
    assert normalize_ingredient("freshly ground black pepper") == "black pepper"
    assert normalize_ingredient("1 onion, diced") == "onion"


def test_match_ingredient_exact_and_substring():
    s = _session_with_ingredients()
    lookup, _ = build_lookup(s)
    assert match_ingredient(s, "eggs", lookup, {}) is not None
    # "whole milk" matcht auf "milk, whole" via Substring
    mid = match_ingredient(s, "whole milk", lookup, {})
    assert mid is not None


def _raw_csv() -> bytes:
    rows = [
        {"name": "Test Pancakes", "minutes": "20",
         "tags": "['breakfast']", "calories": "350.0",
         "steps": "['mix', 'fry']",
         "ingredients": "['2 cups flour', '2 eggs', '1 cup milk']"},
        {"name": "Unknown Stuff", "minutes": "30",
         "tags": "[]", "calories": "500.0",
         "steps": "['cook']",
         "ingredients": "['dragon fruit', 'kelp noodles', 'xanthan gum']"},
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def test_import_creates_recipe_and_skips_unmatched():
    s = _session_with_ingredients()
    n = import_raw_recipes_csv(s, household_id=1,
                               csv_bytes=_raw_csv(), limit=10)
    assert n == 1  # 'Unknown Stuff' hat 0 Matches -> übersprungen
    from sqlalchemy import select
    from app.models import Recipe, RecipeLine
    rec = s.execute(select(Recipe)).scalars().one()
    assert rec.name == "Test Pancakes"
    lines = s.execute(select(RecipeLine)).scalars().all()
    grams_by_ing = {l.ingredient_id: l.grams_raw for l in lines}
    assert len(lines) == 3
    assert any(abs(g - 480.0) < 1e-9 for g in grams_by_ing.values())  # 2 cups milk
    assert any(abs(g - 100.0) < 1e-9 for g in grams_by_ing.values())  # 2 eggs


def test_import_respects_limit_and_duplicates():
    s = _session_with_ingredients()
    n1 = import_raw_recipes_csv(s, household_id=1, csv_bytes=_raw_csv())
    n2 = import_raw_recipes_csv(s, household_id=1, csv_bytes=_raw_csv())
    assert n1 == 1 and n2 == 0  # Duplikat nach Name übersprungen
