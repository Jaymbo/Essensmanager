# Tests für den USDA FDC CSV-Import (USDA_MAP, Divisoren, Bugfix-Regressionen).

import io

from app.importer import USDA_MAP, _compound_guess, import_usda_fdc_csv


def _make_session():
    from app.models import Base, make_engine, make_session_factory
    import os
    import tempfile
    path = tempfile.mktemp(suffix=".db")
    engine = make_engine(path)
    Base.metadata.create_all(engine)
    Session = make_session_factory(engine)
    return Session()


def test_usda_map_known_bugs_fixed():
    # 1096 ist CHROMIUM (µg), NICHT Kupfer
    assert USDA_MAP[1096][0] == "chromium_ug"
    assert USDA_MAP[1098][0] == "copper_mg"
    # 1170 ist PANTOTHENSÄURE, NICHT B6
    assert USDA_MAP[1170][0] == "pantothenic_mg"
    assert USDA_MAP[1175][0] == "vit_b6_mg"
    # Antinutrients mit mg->g-Divisor
    assert USDA_MAP[1041] == ("oxalate_g", 1000.0)
    assert USDA_MAP[1042] == ("phytate_g", 1000.0)


def test_import_applies_divisor_and_maps_nutrients():
    session = _make_session()
    food_csv = io.BytesIO(
        b'fdc_id,description,food_category_id\n'
        b'11111,"Spinach, raw",vegetable\n'
        b'22222,Beef chuck,animal\n')
    nutrient_csv = io.BytesIO(
        b"fdc_id,nutrient_id,amount\n"
        b"11111,1041,750.0\n"      # Oxalsäure in mg -> 0.75 g
        b"11111,1003,2.9\n"        # Protein
        b"11111,1098,0.5\n"        # Kupfer (echt, 1098)
        b"22222,1178,2.5\n"        # B12
        b"22222,1042,120.0\n")     # Phytinsäure in mg -> 0.12 g
    n = import_usda_fdc_csv(session, None, food_csv.getvalue(),
                            nutrient_csv.getvalue())
    assert n == 2
    from sqlalchemy import select
    from app.models import Ingredient
    ings = {i.name: i for i in session.execute(select(Ingredient)).scalars()}
    spinach = ings["Spinach, raw"]
    assert spinach.nutrients["oxalate_g"] == 0.75  # 750 mg / 1000
    assert spinach.nutrients["copper_mg"] == 0.5
    beef = ings["Beef chuck"]
    assert beef.nutrients["vit_b12_ug"] == 2.5
    assert beef.nutrients["phytate_g"] == 0.12     # 120 mg / 1000


def test_fallback_estimate_not_overriding_measured():
    # Spinach-Fallback wäre oxalate_g=0.75; USDA-Messwert 0.4 muss gewinnen.
    session = _make_session()
    food_csv = io.BytesIO(b"fdc_id,description\n11111,Spinach,raw\n")
    nutrient_csv = io.BytesIO(b"fdc_id,nutrient_id,amount\n11111,1041,400.0\n")
    import_usda_fdc_csv(session, None, food_csv.getvalue(),
                        nutrient_csv.getvalue())
    from sqlalchemy import select
    from app.models import Ingredient
    ing = session.execute(select(Ingredient)).scalars().one()
    assert ing.nutrients["oxalate_g"] == 0.4


def test_unknown_nutrient_ids_ignored():
    session = _make_session()
    food_csv = io.BytesIO(b"fdc_id,description\n99999,Test food\n")
    nutrient_csv = io.BytesIO(
        b"fdc_id,nutrient_id,amount\n"
        b"99999,1234,5.0\n"     # nicht gemappt -> ignorieren
        b"99999,1008,100.0\n")  # Energie -> importieren
    n = import_usda_fdc_csv(session, None, food_csv.getvalue(),
                            nutrient_csv.getvalue())
    assert n == 1
    from sqlalchemy import select
    from app.models import Ingredient
    ing = session.execute(select(Ingredient)).scalars().one()
    assert ing.nutrients == {"energy_kcal": 100.0}


def test_compound_guess_categories():
    assert _compound_guess("Bohnen, weisse", "legume")["phytate_g"] == 1.0
    assert _compound_guess("Haferflocken", "grain")["phytate_g"] == 0.6
