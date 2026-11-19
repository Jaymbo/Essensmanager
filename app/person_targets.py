# Personenbezogene Tagesziele: Auto-Berechnung aus Gewicht/Geschlecht/Alter
# (DACH 2019 skaliert) + manuelle Overrides pro Person.
#
# Berechnungslogik:
# - Energie: Henry/RA-BMR nach Mifflin-St Jeor (Gewicht, Größe, Alter, Sex),
#   mit Aktivitätsfaktor; Zielbereich = BMR*AF ± 10 %
# - Protein: 0.8 g/kg Referenz (DACH), Bereich 0.8–1.5 g/kg
# - Fett: 25–35 % der Energie (9 kcal/g)
# - Kohlenhydrate: Rest, mind. 45 % Energie (4 kcal/g)
# - Ballaststoffe: 30 g (DACH); 14 g pro 1000 kcal als Bereich
# - Natrium: 550–2300 mg (DACH); Kalium 3500 mg fix
# - Mikronährstoffe (Vitamine, Mineralien): DACH-Werte sind für Erwachsene
#   19–65 Jahre weitgehend gewichtsunabhängig -> unverändert übernommen;
#   Ausnahme: Calcium 1000 mg, Eisen (f: 15 mg statt 10), Zink (f: 7 statt 10),
#   B12 (f: 4.0), Folsäure (f: 300) -> Geschlechts-Adjustierung.
# - Aminosäuren: WHO/FAO 2007 in mg/kg -> auf Gewicht skalieren
from __future__ import annotations

# WHO/FAO 2007: mg/kg Körpergewicht (Erwachsene)
_AA_MG_PER_KG: dict[str, float] = {
    "leucine_g": 39.0, "isoleucine_g": 20.0, "valine_g": 26.0,
    "lysine_g": 30.0, "methionine_g": 15.0,  # inkl. Cystin (SAA)
    "threonine_g": 15.0, "tryptophan_g": 4.0,
    "phenylalanine_g": 25.0,  # inkl. Tyrosin
    "histidine_g": 10.0,
}

# WHO/FAO 2007: g/kg je 1000 kcal (nicht essentiell) -> grobe Obergrenzen
_ACID_2019_UNSAFE_LIMITS = {"vit_b6_mg": 25, "niacin_mg": 900, "folate_ug": 1000}

_FEMALE_ADJUSTMENTS: dict[str, float] = {
    "iron_mg": 15.0, "zinc_mg": 7.0, "vit_b12_ug": 4.0, "iodine_ug": 140.0,
}


def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Mifflin-St Jeor (1990), Standard-Referenz für RMR."""
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + (5.0 if sex == "m" else -161.0)


def auto_targets(weight_kg: float | None, height_cm: float | None, age: int | None,
                 sex: str | None, activity: float = 1.4) -> dict[str, tuple[float | None, float | None]]:
    """Liefert (min, max) pro Nährstoff-Key. activity = PAL-Faktor (1.2–2.0)."""
    weight = weight_kg or 75.0
    height = height_cm or (175.0 if sex != "f" else 165.0)
    age_y = age or 35
    is_f = sex == "f"

    # Energie: BMR * PAL ± 10 %
    bmr = bmr_mifflin(weight, height, age_y, sex or "m")
    kcal_mid = bmr * max(1.1, min(activity, 2.4))
    kcal_min, kcal_max = kcal_mid * 0.9, kcal_mid * 1.1

    protein_min = 0.8 * weight
    protein_max = 1.5 * weight
    fat_min = kcal_min * 0.25 / 9.0
    fat_max = kcal_max * 0.35 / 9.0
    carbs_min = kcal_min * 0.45 / 4.0
    carbs_max = kcal_max * 0.55 / 4.0

    t: dict[str, tuple[float | None, float | None]] = {
        "energy_kcal": (kcal_min, kcal_max),
        "protein_g": (protein_min, protein_max),
        "fat_g": (fat_min, fat_max),
        "carbs_g": (carbs_min, carbs_max),
        "fiber_g": (kcal_mid / 1000.0 * 14.0, kcal_mid / 1000.0 * 25.0),
        "sugar_g": (0.0, kcal_mid * 0.10 / 4.0),
        "water_g": (weight * 35.0, weight * 45.0),
        # Mikronährstoffe: DACH-Basis, geschlechtsadjustiert
        "calcium_mg": (1000.0, 2500.0),
        "iron_mg": (15.0 if is_f else 10.0, 45.0),
        "magnesium_mg": (310.0 if is_f else 400.0, 1000.0),
        "phosphorus_mg": (700.0, 4000.0),
        "potassium_mg": (3500.0, None),
        "sodium_mg": (550.0, 2300.0),
        "zinc_mg": (7.0 if is_f else 10.0, 40.0),
        "copper_mg": (1.0, 10.0),
        "manganese_mg": (2.0, 11.0),
        "selenium_ug": (60.0, 300.0),
        "iodine_ug": (140.0, 500.0),
        "molybdenum_ug": (50.0, 600.0),
        "vit_a_rae_ug": (800.0 if is_f else 950.0, 3000.0),
        "vit_c_mg": (95.0, 2000.0),
        "vit_d_ug": (20.0, 100.0),
        "vit_e_mg": (12.0, 800.0),
        "vit_k_ug": (70.0, None),
        "thiamin_mg": (1.1, None),
        "riboflavin_mg": (1.2, None),
        "niacin_mg": (13.0, 900.0),
        "vit_b6_mg": (1.4, 25.0),
        "pantothenic_mg": (4.0, None),
        "biotin_ug": (30.0, None),
        "folate_ug": (300.0, 1000.0),
        "vit_b12_ug": (4.0, None),
        "choline_mg": (400.0 if is_f else 550.0, 3000.0),
        # Fettsäuren
        "sfa_g": (None, kcal_mid * 0.10 / 9.0),
        "omega6_g": (8.0, 30.0),
        "omega3_ala_g": (1.1, None),
        "dha_g": (0.25, None),
        "trans_fat_g": (None, kcal_mid * 0.01 / 9.0),
        "cholesterol_mg": (None, 300.0),
    }
    # Aminosäuren nach Gewicht
    for key, mg_kg in _AA_MG_PER_KG.items():
        t[key] = (round(mg_kg * weight / 1000.0, 2), None)
    return t


def effective_targets(base: dict[str, tuple[float | None, float | None]],
                      overrides: dict) -> dict[str, tuple[float | None, float | None]]:
    """Overrides anwenden: {"min": x, "max": y} pro Key; None löscht Ziel."""
    out = dict(base)
    for key, ov in (overrides or {}).items():
        if not isinstance(ov, dict):
            continue
        bmin, bmax = out.get(key, (None, None))
        if "min" in ov:
            bmin = ov["min"]
        if "max" in ov:
            bmax = ov["max"]
        out[key] = (bmin, bmax)
    return out
