# USDA FoodData Central Import: Full-Export CSV (Food_Nutrient / Food Tabelle)
# oder vereinfachte SR-Legacy-CSV. Mappt USDA-Nutrient-IDs auf unsere Keys.

from __future__ import annotations

import csv
import io
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ingredient

# USDA FDC Nutrient-IDs (FoodData Central) -> unsere Nährstoff-Keys
USDA_MAP: dict[int, str] = {
    1008: "energy_kcal",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1087: "calcium_mg",
    1089: "iron_mg",
    1090: "magnesium_mg",
    1091: "phosphorus_mg",
    1092: "potassium_mg",
    1093: "sodium_mg",
    1095: "zinc_mg",
    1096: "copper_mg",
    1101: "manganese_mg",
    1106: "vit_a_rae_ug",
    1162: "vit_c_mg",
    1114: "vit_d_ug",
    1109: "vit_e_mg",
    1185: "vit_k_ug",
    1165: "thiamin_mg",
    1166: "riboflavin_mg",
    1167: "niacin_mg",
    1170: "vit_b6_mg",
    1177: "folate_ug",
    1178: "vit_b12_ug",
}

# Phytat/Oxalat/Tannin sind in USDA nicht enthalten -> Default-Schätzwerte
# nach Lebensmittelkategorie (grob, manuell korrigierbar).
CATEGORY_COMPOUNDS: dict[str, dict[str, float]] = {
    "legume":  {"phytate_g": 1.0, "tannin_g": 0.1},
    "grain":   {"phytate_g": 0.6},
    "nut":     {"phytate_g": 0.9},
    "vegetable": {"oxalate_g": 0.2},
    "spinach": {"oxalate_g": 0.75},
}


def _compound_guess(name: str, category: str) -> dict[str, float]:
    n = name.lower()
    if "spinat" in n or "spinach" in n:
        return CATEGORY_COMPOUNDS["spinach"]
    if any(w in n for w in ("bohne", "linse", "lentil", "bean", "kicher", "chickpea", "soja", "soy")):
        return CATEGORY_COMPOUNDS["legume"]
    if any(w in n for w in ("hafer", "oat", "weizen", "wheat", "reis", "rice", "roggen", "rye", "mehl", "flour")):
        return CATEGORY_COMPOUNDS["grain"]
    if any(w in n for w in ("nuss", "nut", "mandel", "almond", "walnuss", "walnut")):
        return CATEGORY_COMPOUNDS["nut"]
    return CATEGORY_COMPOUNDS.get(category, {})


def import_usda_fdc_csv(session: Session, household_id: int | None,
                        food_csv_bytes: bytes, nutrient_csv_bytes: bytes,
                        limit: int | None = None) -> int:
    """Import aus USDA FDC 'food.csv' + 'food_nutrient.csv' (Full Export oder SR Legacy).
    Erzeugt/aktualisiert Ingredient-Zeilen mit per-100g-Vektoren."""
    foods: dict[str, dict] = {}
    rdr = csv.DictReader(io.StringIO(food_csv_bytes.decode("utf-8", "replace")))
    for row in rdr:
        fdc_id = row.get("fdc_id") or row.get("id")
        if not fdc_id:
            continue
        foods[fdc_id] = {
            "name": (row.get("description") or row.get("name") or "").strip(),
            "category": (row.get("food_category_id") or row.get("category") or ""),
        }
        if limit and len(foods) >= limit:
            break

    nutrients: dict[str, dict[str, float]] = defaultdict(dict)
    rdr = csv.DictReader(io.StringIO(nutrient_csv_bytes.decode("utf-8", "replace")))
    for row in rdr:
        fdc_id = row.get("fdc_id") or row.get("food_id")
        nid = row.get("nutrient_id") or row.get("nutrient_nbr")
        amount = row.get("amount") or row.get("nutrient_value") or row.get("data_value")
        if not fdc_id or not nid or amount in (None, ""):
            continue
        key = USDA_MAP.get(int(float(nid)))
        if key:
            nutrients[fdc_id][key] = float(amount)

    count = 0
    for fdc_id, meta in foods.items():
        vec = nutrients.get(fdc_id)
        if not vec or not meta["name"]:
            continue
        vec = dict(vec)
        vec.update(_compound_guess(meta["name"], meta["category"]))
        name = meta["name"][:160]
        existing = session.execute(
            select(Ingredient).where(
                Ingredient.household_id == household_id,
                Ingredient.name == name)).scalar_one_or_none()
        if existing:
            existing.nutrients = vec
            existing.source = "USDA FDC"
            existing.usda_fdc_id = fdc_id
        else:
            session.add(Ingredient(
                household_id=household_id, name=name, category=meta["category"],
                nutrients=vec, source="USDA FDC", usda_fdc_id=fdc_id))
        count += 1
        if limit and count >= limit:
            break
    session.commit()
    return count
