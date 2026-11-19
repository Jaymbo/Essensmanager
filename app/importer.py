# USDA FoodData Central Import: Full-Export CSV (Food_Nutrient / Food Tabelle)
# oder vereinfachte SR-Legacy-CSV. Mappt USDA-Nutrient-IDs auf unsere Keys.

from __future__ import annotations

import csv
import io
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ingredient

# USDA FDC Nutrient-IDs (FoodData Central, SR Legacy nutrient.csv) -> unsere Keys.
# Wert: (key, divisor). Divisor 1000 = USDA liefert mg/g-mischung, wir brauchen g.
# Verifiziert gegen SR Legacy 2018-04 nutrient.csv (474 Nährstoffe gesamt).
# Bugfix-Historie: 1096 ist CHROMIUM (nicht Cu, das ist 1098);
#                  1170 ist PANTOTHENIC ACID (nicht B6, das ist 1175).
USDA_MAP: dict[int, tuple[str, float]] = {
    # Makros
    1008: ("energy_kcal", 1.0),
    1003: ("protein_g", 1.0),
    1004: ("fat_g", 1.0),
    1005: ("carbs_g", 1.0),
    1079: ("fiber_g", 1.0),
    2000: ("sugar_g", 1.0),
    1009: ("starch_g", 1.0),
    1010: ("sucrose_g", 1.0),
    1011: ("glucose_g", 1.0),
    1012: ("fructose_g", 1.0),
    1013: ("lactose_g", 1.0),
    1014: ("maltose_g", 1.0),
    1018: ("alcohol_g", 1.0),
    1051: ("water_g", 1.0),
    1007: ("ash_g", 1.0),
    1082: ("fiber_soluble_g", 1.0),
    1084: ("fiber_insoluble_g", 1.0),
    # Mineralstoffe
    1087: ("calcium_mg", 1.0),
    1089: ("iron_mg", 1.0),
    1141: ("heme_iron_mg", 1.0),
    1142: ("nonheme_iron_mg", 1.0),
    1090: ("magnesium_mg", 1.0),
    1091: ("phosphorus_mg", 1.0),
    1092: ("potassium_mg", 1.0),
    1093: ("sodium_mg", 1.0),
    1095: ("zinc_mg", 1.0),
    1098: ("copper_mg", 1.0),
    1101: ("manganese_mg", 1.0),
    1103: ("selenium_ug", 1.0),
    1100: ("iodine_ug", 1.0),
    1099: ("fluoride_ug", 1.0),
    1096: ("chromium_ug", 1.0),
    1102: ("molybdenum_ug", 1.0),
    # Vitamine
    1106: ("vit_a_rae_ug", 1.0),
    1162: ("vit_c_mg", 1.0),
    1114: ("vit_d_ug", 1.0),
    1109: ("vit_e_mg", 1.0),
    1126: ("tocopherol_gamma_mg", 1.0),
    1185: ("vit_k_ug", 1.0),
    1183: ("vit_k2_mk4_ug", 1.0),
    1165: ("thiamin_mg", 1.0),
    1166: ("riboflavin_mg", 1.0),
    1167: ("niacin_mg", 1.0),
    1175: ("vit_b6_mg", 1.0),
    1170: ("pantothenic_mg", 1.0),
    1176: ("biotin_ug", 1.0),
    1177: ("folate_ug", 1.0),
    1190: ("folate_dfe_ug", 1.0),
    1178: ("vit_b12_ug", 1.0),
    1180: ("choline_mg", 1.0),
    1198: ("betaine_mg", 1.0),
    # Aminosäuren (SR Legacy 1210-1227, in g)
    1210: ("tryptophan_g", 1.0),
    1211: ("threonine_g", 1.0),
    1212: ("isoleucine_g", 1.0),
    1213: ("leucine_g", 1.0),
    1214: ("lysine_g", 1.0),
    1215: ("methionine_g", 1.0),
    1216: ("cystine_g", 1.0),
    1217: ("phenylalanine_g", 1.0),
    1218: ("tyrosine_g", 1.0),
    1219: ("valine_g", 1.0),
    1220: ("arginine_g", 1.0),
    1221: ("histidine_g", 1.0),
    1222: ("alanine_g", 1.0),
    1223: ("aspartic_acid_g", 1.0),
    1224: ("glutamic_acid_g", 1.0),
    1225: ("glycine_g", 1.0),
    1226: ("proline_g", 1.0),
    1227: ("serine_g", 1.0),
    # Fettsäuren
    1258: ("sfa_g", 1.0),
    1292: ("mufa_g", 1.0),
    1293: ("pufa_g", 1.0),
    1269: ("omega6_g", 1.0),
    1404: ("omega3_ala_g", 1.0),
    1278: ("epa_g", 1.0),
    1272: ("dha_g", 1.0),
    1257: ("trans_fat_g", 1.0),
    1253: ("cholesterol_mg", 1.0),
    1283: ("phytosterols_mg", 1.0),
    # Carotinoide
    1107: ("beta_carotene_ug", 1.0),
    1123: ("lutein_zeaxanthin_ug", 1.0),
    1122: ("lycopene_ug", 1.0),
    # Sonstiges
    1057: ("caffeine_mg", 1.0),
    1058: ("theobromine_mg", 1.0),
    # Antinutrients: USDA liefert echte Messwerte (mg -> g)!
    1041: ("oxalate_g", 1000.0),
    1042: ("phytate_g", 1000.0),
}

# Antinutrient-Schätzwerte nach Kategorie (nur als Fallback, wenn USDA
# keinen Messwert für Oxalat (1041) / Phytat (1042) liefert).
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
        mapped = USDA_MAP.get(int(float(nid)))
        if mapped:
            key, divisor = mapped
            nutrients[fdc_id][key] = float(amount) / divisor

    count = 0
    for fdc_id, meta in foods.items():
        vec = nutrients.get(fdc_id)
        if not vec or not meta["name"]:
            continue
        vec = dict(vec)
        # Fallback-Schätzwerte nur ergänzen, wenn USDA keinen Messwert liefert
        # (Oxalat 1041 / Phytat 1042 sind in SR Legacy als echte Messwerte drin).
        for ck, cv in _compound_guess(meta["name"], meta["category"]).items():
            if ck not in vec:
                vec[ck] = cv
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
