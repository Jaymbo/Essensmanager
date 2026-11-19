# Seed: Referenzdaten (Nährstoffe mit DACH-Werten, Kochprozesse mit
# Retentionsfaktoren inkl. Quellen, Interaktionsregeln, Grundzutaten,
# Beispielrezepte) + Demo-Haushalt.

from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import select

from .models import (Household, Ingredient, InteractionRule, NutrientDef,
                     PantryItem, Person, Process, Recipe, RecipeLine, Base,
                     make_engine, make_session_factory)
from .recipe_engine import RecipeEngine

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "app.db"

# ---------- Nährstoffdefinitionen ----------
# daily_min/max: DACH-Referenzwerte Erwachsene (Mischgeschlecht, grob).
NUTRIENTS: list[dict] = [
    dict(key="energy_kcal", name="Energie", unit="kcal", daily_min=2000, daily_max=3000,
         absorb_efficiency=1.0, half_life_days=None, display_order=1,
         source="DACH 2019"),
    dict(key="protein_g", name="Protein", unit="g", daily_min=50, daily_max=150,
         absorb_efficiency=0.92, half_life_days=None, display_order=2,
         source="DACH 2019"),
    dict(key="fat_g", name="Fett", unit="g", daily_min=50, daily_max=100,
         absorb_efficiency=0.95, half_life_days=None, display_order=3,
         source="DACH 2019"),
    dict(key="carbs_g", name="Kohlenhydrate", unit="g", daily_min=200, daily_max=400,
         absorb_efficiency=0.97, half_life_days=None, display_order=4,
         source="DACH 2019"),
    dict(key="fiber_g", name="Ballaststoffe", unit="g", daily_min=30, daily_max=70,
         absorb_efficiency=0.0, half_life_days=None, display_order=5,
         source="DACH 2019 (Effizienz 0: keine Resorption)"),
    dict(key="sugar_g", name="Zucker", unit="g", daily_min=0, daily_max=50,
         absorb_efficiency=1.0, half_life_days=None, display_order=6,
         source="WHO <10 % Energie"),
    dict(key="calcium_mg", name="Calcium", unit="mg", daily_min=1000, daily_max=2500,
         absorb_efficiency=0.35, half_life_days=10000, display_order=7,
         source="DACH 2019; Effizienz ~30-40 %"),
    dict(key="iron_mg", name="Eisen", unit="mg", daily_min=10, daily_max=45,
         absorb_efficiency=0.18, half_life_days=2000, display_order=8,
         source="DACH 2019; gemischte Kost ~15-18 %"),
    dict(key="magnesium_mg", name="Magnesium", unit="mg", daily_min=300, daily_max=1000,
         absorb_efficiency=0.45, half_life_days=1000, display_order=9,
         source="DACH 2019"),
    dict(key="phosphorus_mg", name="Phosphor", unit="mg", daily_min=700, daily_max=4000,
         absorb_efficiency=0.65, half_life_days=3000, display_order=10,
         source="DACH 2019"),
    dict(key="potassium_mg", name="Kalium", unit="mg", daily_min=3500, daily_max=None,
         absorb_efficiency=0.85, half_life_days=2, display_order=11,
         source="DACH 2019"),
    dict(key="sodium_mg", name="Natrium", unit="mg", daily_min=550, daily_max=2300,
         absorb_efficiency=0.95, half_life_days=1, display_order=12,
         source="DACH 2019"),
    dict(key="zinc_mg", name="Zink", unit="mg", daily_min=10, daily_max=40,
         absorb_efficiency=0.35, half_life_days=300, display_order=13,
         source="DACH 2019"),
    dict(key="copper_mg", name="Kupfer", unit="mg", daily_min=1.0, daily_max=10,
         absorb_efficiency=0.55, half_life_days=60, display_order=14,
         source="DACH 2019"),
    dict(key="manganese_mg", name="Mangan", unit="mg", daily_min=2.0, daily_max=11,
         absorb_efficiency=0.05, half_life_days=30, display_order=15,
         source="DACH 2019"),
    dict(key="vit_a_rae_ug", name="Vitamin A (RAE)", unit="µg", daily_min=800, daily_max=3000,
         absorb_efficiency=0.75, half_life_days=140, pool_capacity=500000,
         display_order=20, source="DACH 2019; Leberpool ~1 Jahr"),
    dict(key="vit_c_mg", name="Vitamin C", unit="mg", daily_min=95, daily_max=2000,
         absorb_efficiency=0.80, half_life_days=30, pool_capacity=3000,
         display_order=21, source="DACH 2019; Körperspeicher ~1.5 g"),
    dict(key="vit_d_ug", name="Vitamin D", unit="µg", daily_min=20, daily_max=100,
         absorb_efficiency=0.60, half_life_days=60, pool_capacity=15000,
         display_order=22, source="DACH 2019"),
    dict(key="vit_e_mg", name="Vitamin E", unit="mg", daily_min=12, daily_max=800,
         absorb_efficiency=0.50, half_life_days=100, display_order=23,
         source="DACH 2019"),
    dict(key="vit_k_ug", name="Vitamin K", unit="µg", daily_min=70, daily_max=None,
         absorb_efficiency=0.45, half_life_days=3, display_order=24,
         source="DACH 2019"),
    dict(key="thiamin_mg", name="Thiamin (B1)", unit="mg", daily_min=1.1, daily_max=None,
         absorb_efficiency=0.60, half_life_days=15, display_order=25,
         source="DACH 2019"),
    dict(key="riboflavin_mg", name="Riboflavin (B2)", unit="mg", daily_min=1.2, daily_max=None,
         absorb_efficiency=0.65, half_life_days=15, display_order=26,
         source="DACH 2019"),
    dict(key="niacin_mg", name="Niacin", unit="mg", daily_min=13, daily_max=900,
         absorb_efficiency=0.70, half_life_days=20, display_order=27,
         source="DACH 2019"),
    dict(key="vit_b6_mg", name="Vitamin B6", unit="mg", daily_min=1.4, daily_max=25,
         absorb_efficiency=0.70, half_life_days=25, display_order=28,
         source="DACH 2019"),
    dict(key="folate_ug", name="Folsäure", unit="µg", daily_min=300, daily_max=1000,
         absorb_efficiency=0.50, half_life_days=100, pool_capacity=15000,
         display_order=29, source="DACH 2019; Leberpool ~3-4 Monate"),
    dict(key="vit_b12_ug", name="Vitamin B12", unit="µg", daily_min=4.0, daily_max=None,
         absorb_efficiency=1.0, half_life_days=1200, pool_capacity=2500,
         display_order=30,
         source="DACH 2019; Leberpool 2-3 mg, Halbwertszeit ~1 Jahr; Aufnahme via Sättigungskinetik"),
    dict(key="phytate_g", name="Phytat", unit="g", daily_min=None, daily_max=None,
         absorb_efficiency=0.0, half_life_days=None, display_order=90,
         source="Interaktionsstoff, kein Nährstoff"),
    dict(key="oxalate_g", name="Oxalat", unit="g", daily_min=None, daily_max=None,
         absorb_efficiency=0.0, half_life_days=None, display_order=91,
         source="Interaktionsstoff"),
    dict(key="tannin_g", name="Tannine", unit="g", daily_min=None, daily_max=None,
         absorb_efficiency=0.0, half_life_days=None, display_order=92,
         source="Interaktionsstoff"),
    dict(key="animal_protein_g", name="Animalisches Protein", unit="g", daily_min=None,
         daily_max=None, absorb_efficiency=0.0, half_life_days=None, display_order=93,
         source="Interaktionsstoff (Meat-Factor)"),
]

# ---------- Kochprozesse ----------
# Retentionsfaktoren: USDA Table of Retention Factors (Rev. 2019), Bognár (2002).
# Faktor = verbleibender Anteil je 100 g Rohware-Äquivalent.
PROCESSES: list[dict] = [
    dict(key="boil", name="Kochen (Wasser)",
         description="Wassergare; wasserlösliche Vitamine waschen aus.",
         source="USDA Retention Factors Table, Bognár 2002",
         factors={"vit_c_mg": 0.65, "thiamin_mg": 0.70, "riboflavin_mg": 0.75,
                  "niacin_mg": 0.75, "vit_b6_mg": 0.70, "folate_ug": 0.60,
                  "vit_b12_ug": 0.60, "potassium_mg": 0.70, "sodium_mg": 0.70,
                  "magnesium_mg": 0.75, "iron_mg": 0.85, "zinc_mg": 0.85,
                  "calcium_mg": 0.90, "vit_a_rae_ug": 0.85, "vit_d_ug": 0.85}),
    dict(key="steam", name="Dämpfen",
         description="Schonender als Wasserkochen (weniger Auslaugen).",
         source="Bognár 2002",
         factors={"vit_c_mg": 0.85, "thiamin_mg": 0.85, "riboflavin_mg": 0.90,
                  "folate_ug": 0.80, "vit_b12_ug": 0.80, "potassium_mg": 0.90}),
    dict(key="fry", name="Braten",
         description="Hitzeeinwirkung + Fettaufnahme; Faktor für fat_g >1 via yield.",
         source="USDA Retention Table (Panfrying)",
         factors={"vit_c_mg": 0.60, "thiamin_mg": 0.70, "riboflavin_mg": 0.80,
                  "niacin_mg": 0.80, "vit_b6_mg": 0.70, "folate_ug": 0.65,
                  "vit_b12_ug": 0.70, "vit_a_rae_ug": 0.75, "vit_e_mg": 0.75,
                  "fat_g": 1.10, "energy_kcal": 1.07}),
    dict(key="deep_fry", name="Frittieren",
         description="Starke Hitzeeinwirkung, deutliche Fettaufnahme.",
         source="USDA Retention Table (Deep frying)",
         factors={"vit_c_mg": 0.50, "thiamin_mg": 0.60, "vit_b6_mg": 0.60,
                  "folate_ug": 0.55, "vit_b12_ug": 0.60, "vit_a_rae_ug": 0.65,
                  "vit_e_mg": 0.60, "fat_g": 1.35, "energy_kcal": 1.18}),
    dict(key="bake", name="Backen (Ofen)",
         description="Trockene Hitze; Maillard reduziert z.T. Lysin (hier grob über Protein).",
         source="USDA Retention Table (Baking)",
         factors={"vit_c_mg": 0.70, "thiamin_mg": 0.75, "vit_b6_mg": 0.75,
                  "folate_ug": 0.65, "vit_b12_ug": 0.70, "vit_a_rae_ug": 0.80,
                  "vit_e_mg": 0.80}),
    dict(key="roast", name="Schmoren/Rösten",
         description="Lange, mäßige Hitze.",
         source="USDA Retention Table (Braising/Roasting)",
         factors={"vit_c_mg": 0.55, "thiamin_mg": 0.65, "vit_b6_mg": 0.65,
                  "folate_ug": 0.60, "vit_b12_ug": 0.65, "vit_a_rae_ug": 0.70}),
    dict(key="ferment", name="Fermentieren",
         description="Mikrobielle Synthese: B-Vitamine steigen (z.B. Sauerkraut, Tempeh).",
         source="Literatur: B-Vitamin-Zunahme in fermentierten Lebensmitteln",
         factors={"vit_c_mg": 0.90, "thiamin_mg": 1.15, "riboflavin_mg": 1.20,
                  "niacin_mg": 1.15, "vit_b6_mg": 1.20, "folate_ug": 1.30,
                  "vit_b12_ug": 1.15, "vit_k_ug": 1.60, "phytate_g": 0.55}),
    dict(key="proof", name="Gehen lassen (Teig)",
         description="Hefegärung: geringe B-Vitamin-Synthese, Phytatabbau.",
         source="Literatur: Sauerteig fermentation",
         factors={"thiamin_mg": 1.10, "folate_ug": 1.10, "phytate_g": 0.70}),
    dict(key="sourdough", name="Sauerteigführung",
         description="Lange Gärung: deutlicher Phytatabbau → bessere Mineralstoffverfügbarkeit.",
         source="Literatur: phytate degradation in sourdough",
         factors={"thiamin_mg": 1.10, "folate_ug": 1.15, "phytate_g": 0.45}),
    dict(key="sprout", name="Keimen",
         description="Enzymatischer Abbau von Phytat; Vitamin C steigt.",
         source="Literatur: sprouting increases vitamin C, reduces phytate",
         factors={"vit_c_mg": 2.0, "folate_ug": 1.3, "phytate_g": 0.40}),
    dict(key="blanch", name="Blanchieren",
         description="Kurzes Wassergare (Vorbereitung/Tiefkühl).",
         source="Bognár 2002",
         factors={"vit_c_mg": 0.75, "thiamin_mg": 0.80, "folate_ug": 0.75,
                  "potassium_mg": 0.80}),
    dict(key="raw", name="Roh",
         description="Keine Veränderung.",
         source="—", factors={}),
]

# ---------- Interaktionsregeln ----------
# Sättigungsformeln: half_saturation = Menge, bei der die halbe Maximalwirkung
# eintritt. Quellen im Feld `source`.
INTERACTIONS: list[dict] = [
    # Vitamin C fördert Nicht-Häm-Eisen stark (Cook & Monsen 1977).
    dict(target="iron_mg", kind="enhancer", compound="vit_c_mg", effect=1.5,
         half_saturation=75, source="Cook & Monsen 1977; Hallberg et al. 1989"),
    # Phytate hemmen Eisen + Zink (Hallberg et al. 1989; Hunt et al.).
    dict(target="iron_mg", kind="inhibitor", compound="phytate_g", effect=-0.55,
         half_saturation=3, source="Hallberg et al. 1989"),
    dict(target="zinc_mg", kind="inhibitor", compound="phytate_g", effect=-0.45,
         half_saturation=3, source="Hunt 2003; DACH"),
    # Calcium hemmt Eisen (Hallberg 1991) – gering bis moderat.
    dict(target="iron_mg", kind="inhibitor", compound="calcium_mg", effect=-0.30,
         half_saturation=300, source="Hallberg et al. 1991"),
    # Tannine hemmen Eisen (Brune et al. 1989).
    dict(target="iron_mg", kind="inhibitor", compound="tannin_g", effect=-0.35,
         half_saturation=0.5, source="Brune et al. 1989"),
    # Fleisch-Faktor fördert Nicht-Häm-Eisen + Zink.
    dict(target="iron_mg", kind="enhancer", compound="animal_protein_g", effect=0.5,
         half_saturation=40, source="Cook & Monsen 1976 (Meat Factor)"),
    dict(target="zinc_mg", kind="enhancer", compound="animal_protein_g", effect=0.25,
         half_saturation=40, source="Lonnerdal 2000"),
    # Oxalat hemmt Calcium (Weaver et al.).
    dict(target="calcium_mg", kind="inhibitor", compound="oxalate_g", effect=-0.30,
         half_saturation=1.5, source="Weaver & Heaney 1999"),
    # Fett fördert fettlösliche Vitamine (A, D, E, K).
    dict(target="vit_a_rae_ug", kind="enhancer", compound="fat_g", effect=0.5,
         half_saturation=20, source="Rodriguez-Amaya 2019; Jäpelt & Jakobsen"),
    dict(target="vit_d_ug", kind="enhancer", compound="fat_g", effect=0.4,
         half_saturation=20, source="Literatur: fat co-ingestion"),
    dict(target="vit_e_mg", kind="enhancer", compound="fat_g", effect=0.5,
         half_saturation=15, source="Literatur: fat co-ingestion"),
    dict(target="vit_k_ug", kind="enhancer", compound="fat_g", effect=0.6,
         half_saturation=15, source="Literatur: fat co-ingestion"),
    # Vitamin D & Calcium: Ca-Förderung durch begleitendes D grob via vit_d.
    dict(target="calcium_mg", kind="enhancer", compound="vit_d_ug", effect=0.25,
         half_saturation=10, source="DACH; Vitamin D -> Ca-Resorption"),
]

# ---------- Grundzutaten (per 100 g) ----------
# Kompiliert aus USDA FDC / Deutschen Nährwerttabellen (Souci-Fachmann-Kraut).
INGREDIENTS: list[dict] = [
    dict(name="Haferflocken (Vollkorn)", category="grain", nutrients=dict(
        energy_kcal=372, protein_g=13.5, fat_g=7.0, carbs_g=58.7, fiber_g=10.0,
        sugar_g=1.0, calcium_mg=54, iron_mg=4.7, magnesium_mg=177,
        phosphorus_mg=523, potassium_mg=358, sodium_mg=6, zinc_mg=3.6,
        copper_mg=0.4, manganese_mg=4.9, vit_a_rae_ug=0, vit_c_mg=0,
        vit_d_ug=0, vit_e_mg=0.6, vit_k_ug=2.0, thiamin_mg=0.65,
        riboflavin_mg=0.17, niacin_mg=1.4, vit_b6_mg=0.17, folate_ug=56,
        vit_b12_ug=0, phytate_g=0.95, oxalate_g=0.02, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Weizenvollkornmehl (Type 1050)", category="grain", nutrients=dict(
        energy_kcal=336, protein_g=13.0, fat_g=2.5, carbs_g=63.0, fiber_g=9.0,
        sugar_g=1.5, calcium_mg=34, iron_mg=3.9, magnesium_mg=140,
        phosphorus_mg=370, potassium_mg=330, sodium_mg=2, zinc_mg=2.9,
        copper_mg=0.4, manganese_mg=3.1, vit_a_rae_ug=0, vit_c_mg=0,
        vit_d_ug=0, vit_e_mg=1.2, vit_k_ug=1.9, thiamin_mg=0.48,
        riboflavin_mg=0.13, niacin_mg=5.5, vit_b6_mg=0.35, folate_ug=48,
        vit_b12_ug=0, phytate_g=0.8, oxalate_g=0.02, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Roggenmehl (Type 1150)", category="grain", nutrients=dict(
        energy_kcal=325, protein_g=9.5, fat_g=1.4, carbs_g=64.0, fiber_g=11.0,
        sugar_g=1.2, calcium_mg=40, iron_mg=3.3, magnesium_mg=100,
        phosphorus_mg=340, potassium_mg=350, sodium_mg=2, zinc_mg=2.4,
        copper_mg=0.4, manganese_mg=2.4, vit_a_rae_ug=0, vit_c_mg=0,
        vit_d_ug=0, vit_e_mg=0.9, vit_k_ug=1.3, thiamin_mg=0.35,
        riboflavin_mg=0.15, niacin_mg=1.8, vit_b6_mg=0.3, folate_ug=40,
        vit_b12_ug=0, phytate_g=0.75, oxalate_g=0.02, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Linsen (getrocknet, braun)", category="legume", nutrients=dict(
        energy_kcal=341, protein_g=24.6, fat_g=1.1, carbs_g=49.9, fiber_g=11.0,
        sugar_g=1.8, calcium_mg=56, iron_mg=7.5, magnesium_mg=122,
        phosphorus_mg=407, potassium_mg=955, sodium_mg=6, zinc_mg=4.8,
        copper_mg=0.75, manganese_mg=1.3, vit_a_rae_ug=0, vit_c_mg=4.5,
        vit_d_ug=0, vit_e_mg=0.5, vit_k_ug=5.0, thiamin_mg=0.87,
        riboflavin_mg=0.21, niacin_mg=2.6, vit_b6_mg=0.54, folate_ug=479,
        vit_b12_ug=0, phytate_g=1.4, oxalate_g=0.05, tannin_g=0.1,
        animal_protein_g=0)),
    dict(name="Kichererbsen (getrocknet)", category="legume", nutrients=dict(
        energy_kcal=364, protein_g=19.0, fat_g=6.0, carbs_g=51.0, fiber_g=12.0,
        sugar_g=5.0, calcium_mg=105, iron_mg=6.2, magnesium_mg=115,
        phosphorus_mg=366, potassium_mg=718, sodium_mg=24, zinc_mg=3.4,
        copper_mg=0.65, manganese_mg=1.1, vit_a_rae_ug=1, vit_c_mg=4.0,
        vit_d_ug=0, vit_e_mg=0.4, vit_k_ug=4.0, thiamin_mg=0.48,
        riboflavin_mg=0.09, niacin_mg=1.5, vit_b6_mg=0.54, folate_ug=557,
        vit_b12_ug=0, phytate_g=1.2, oxalate_g=0.04, tannin_g=0.08,
        animal_protein_g=0)),
    dict(name="Hähnchenbrust (roh)", category="meat", nutrients=dict(
        energy_kcal=110, protein_g=23.1, fat_g=1.2, carbs_g=0, fiber_g=0,
        sugar_g=0, calcium_mg=8, iron_mg=0.4, magnesium_mg=25,
        phosphorus_mg=190, potassium_mg=330, sodium_mg=60, zinc_mg=0.9,
        copper_mg=0.04, manganese_mg=0.02, vit_a_rae_ug=6, vit_c_mg=0,
        vit_d_ug=0.1, vit_e_mg=0.3, vit_k_ug=0, thiamin_mg=0.07,
        riboflavin_mg=0.11, niacin_mg=10.5, vit_b6_mg=0.6, folate_ug=7,
        vit_b12_ug=0.3, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=23.1)),
    dict(name="Rindergulasch (roh)", category="meat", nutrients=dict(
        energy_kcal=180, protein_g=20.5, fat_g=10.0, carbs_g=0, fiber_g=0,
        sugar_g=0, calcium_mg=10, iron_mg=2.2, magnesium_mg=20,
        phosphorus_mg=170, potassium_mg=320, sodium_mg=55, zinc_mg=4.5,
        copper_mg=0.09, manganese_mg=0.01, vit_a_rae_ug=5, vit_c_mg=0,
        vit_d_ug=0.2, vit_e_mg=0.4, vit_k_ug=1, thiamin_mg=0.05,
        riboflavin_mg=0.18, niacin_mg=4.5, vit_b6_mg=0.4, folate_ug=6,
        vit_b12_ug=2.0, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=20.5)),
    dict(name="Lachsfilet (roh)", category="fish", nutrients=dict(
        energy_kcal=200, protein_g=20.0, fat_g=13.0, carbs_g=0, fiber_g=0,
        sugar_g=0, calcium_mg=12, iron_mg=0.3, magnesium_mg=27,
        phosphorus_mg=240, potassium_mg=360, sodium_mg=45, zinc_mg=0.4,
        copper_mg=0.05, manganese_mg=0.01, vit_a_rae_ug=30, vit_c_mg=0,
        vit_d_ug=11.0, vit_e_mg=1.5, vit_k_ug=0.5, thiamin_mg=0.23,
        riboflavin_mg=0.38, niacin_mg=8.5, vit_b6_mg=0.6, folate_ug=25,
        vit_b12_ug=3.2, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=20.0)),
    dict(name="Ei (Hühnerei, roh)", category="egg", nutrients=dict(
        energy_kcal=137, protein_g=12.6, fat_g=9.5, carbs_g=0.6, fiber_g=0,
        sugar_g=0.6, calcium_mg=57, iron_mg=1.9, magnesium_mg=12,
        phosphorus_mg=200, potassium_mg=140, sodium_mg=140, zinc_mg=1.3,
        copper_mg=0.1, manganese_mg=0.03, vit_a_rae_ug=170, vit_c_mg=0,
        vit_d_ug=2.9, vit_e_mg=1.1, vit_k_ug=0.3, thiamin_mg=0.04,
        riboflavin_mg=0.4, niacin_mg=0.07, vit_b6_mg=0.12, folate_ug=47,
        vit_b12_ug=1.1, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=12.6)),
    dict(name="Vollmilch (3.5 % Fett)", category="dairy", nutrients=dict(
        energy_kcal=64, protein_g=3.4, fat_g=3.5, carbs_g=4.9, fiber_g=0,
        sugar_g=4.9, calcium_mg=120, iron_mg=0.03, magnesium_mg=12,
        phosphorus_mg=93, potassium_mg=150, sodium_mg=45, zinc_mg=0.4,
        copper_mg=0.02, manganese_mg=0.004, vit_a_rae_ug=35, vit_c_mg=1,
        vit_d_ug=0.2, vit_e_mg=0.1, vit_k_ug=0.4, thiamin_mg=0.04,
        riboflavin_mg=0.17, niacin_mg=0.1, vit_b6_mg=0.04, folate_ug=6,
        vit_b12_ug=0.4, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=3.4)),
    dict(name="Joghurt (3.5 % Fett)", category="dairy", nutrients=dict(
        energy_kcal=62, protein_g=3.8, fat_g=3.5, carbs_g=4.0, fiber_g=0,
        sugar_g=4.0, calcium_mg=120, iron_mg=0.05, magnesium_mg=12,
        phosphorus_mg=95, potassium_mg=155, sodium_mg=45, zinc_mg=0.5,
        copper_mg=0.02, manganese_mg=0.004, vit_a_rae_ug=30, vit_c_mg=1,
        vit_d_ug=0.1, vit_e_mg=0.1, vit_k_ug=0.3, thiamin_mg=0.03,
        riboflavin_mg=0.15, niacin_mg=0.1, vit_b6_mg=0.05, folate_ug=8,
        vit_b12_ug=0.3, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=3.8)),
    dict(name="Kartoffeln (roh)", category="vegetable", nutrients=dict(
        energy_kcal=70, protein_g=2.0, fat_g=0.1, carbs_g=15.4, fiber_g=2.1,
        sugar_g=0.8, calcium_mg=8, iron_mg=0.6, magnesium_mg=20,
        phosphorus_mg=50, potassium_mg=446, sodium_mg=5, zinc_mg=0.3,
        copper_mg=0.12, manganese_mg=0.15, vit_a_rae_ug=0, vit_c_mg=17,
        vit_d_ug=0, vit_e_mg=0.03, vit_k_ug=2.2, thiamin_mg=0.1,
        riboflavin_mg=0.02, niacin_mg=1.1, vit_b6_mg=0.3, folate_ug=17,
        vit_b12_ug=0, phytate_g=0.1, oxalate_g=0.03, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Brokkoli (roh)", category="vegetable", nutrients=dict(
        energy_kcal=34, protein_g=2.8, fat_g=0.4, carbs_g=2.0, fiber_g=3.5,
        sugar_g=1.7, calcium_mg=47, iron_mg=0.7, magnesium_mg=21,
        phosphorus_mg=66, potassium_mg=316, sodium_mg=18, zinc_mg=0.4,
        copper_mg=0.05, manganese_mg=0.2, vit_a_rae_ug=31, vit_c_mg=89,
        vit_d_ug=0, vit_e_mg=0.8, vit_k_ug=102, thiamin_mg=0.07,
        riboflavin_mg=0.12, niacin_mg=0.6, vit_b6_mg=0.18, folate_ug=63,
        vit_b12_ug=0, phytate_g=0.05, oxalate_g=0.02, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Spinat (roh)", category="vegetable", nutrients=dict(
        energy_kcal=22, protein_g=2.9, fat_g=0.4, carbs_g=1.4, fiber_g=2.2,
        sugar_g=0.4, calcium_mg=117, iron_mg=2.7, magnesium_mg=79,
        phosphorus_mg=49, potassium_mg=558, sodium_mg=79, zinc_mg=0.5,
        copper_mg=0.13, manganese_mg=0.9, vit_a_rae_ug=469, vit_c_mg=28,
        vit_d_ug=0, vit_e_mg=2.0, vit_k_ug=483, thiamin_mg=0.08,
        riboflavin_mg=0.19, niacin_mg=0.7, vit_b6_mg=0.2, folate_ug=194,
        vit_b12_ug=0, phytate_g=0.03, oxalate_g=0.75, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Karotten (roh)", category="vegetable", nutrients=dict(
        energy_kcal=37, protein_g=1.1, fat_g=0.2, carbs_g=6.9, fiber_g=2.7,
        sugar_g=4.7, calcium_mg=33, iron_mg=0.3, magnesium_mg=12,
        phosphorus_mg=35, potassium_mg=320, sodium_mg=60, zinc_mg=0.2,
        copper_mg=0.05, manganese_mg=0.15, vit_a_rae_ug=830, vit_c_mg=6,
        vit_d_ug=0, vit_e_mg=0.5, vit_k_ug=13, thiamin_mg=0.05,
        riboflavin_mg=0.05, niacin_mg=0.9, vit_b6_mg=0.14, folate_ug=19,
        vit_b12_ug=0, phytate_g=0.03, oxalate_g=0.05, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Tomaten (roh)", category="vegetable", nutrients=dict(
        energy_kcal=18, protein_g=1.0, fat_g=0.2, carbs_g=2.6, fiber_g=1.2,
        sugar_g=2.6, calcium_mg=9, iron_mg=0.3, magnesium_mg=11,
        phosphorus_mg=24, potassium_mg=237, sodium_mg=5, zinc_mg=0.2,
        copper_mg=0.06, manganese_mg=0.11, vit_a_rae_ug=42, vit_c_mg=14,
        vit_d_ug=0, vit_e_mg=0.5, vit_k_ug=8, thiamin_mg=0.04,
        riboflavin_mg=0.02, niacin_mg=0.6, vit_b6_mg=0.08, folate_ug=22,
        vit_b12_ug=0, phytate_g=0.02, oxalate_g=0.01, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Olivenöl", category="fat", nutrients=dict(
        energy_kcal=884, protein_g=0, fat_g=100, carbs_g=0, fiber_g=0,
        sugar_g=0, calcium_mg=1, iron_mg=0.6, magnesium_mg=0,
        phosphorus_mg=0, potassium_mg=1, sodium_mg=2, zinc_mg=0,
        copper_mg=0, manganese_mg=0, vit_a_rae_ug=0, vit_c_mg=0,
        vit_d_ug=0, vit_e_mg=12, vit_k_ug=60, thiamin_mg=0, riboflavin_mg=0,
        niacin_mg=0, vit_b6_mg=0, folate_ug=0, vit_b12_ug=0, phytate_g=0,
        oxalate_g=0, tannin_g=0, animal_protein_g=0)),
    dict(name="Butter", category="fat", nutrients=dict(
        energy_kcal=741, protein_g=0.7, fat_g=82, carbs_g=0.6, fiber_g=0,
        sugar_g=0.6, calcium_mg=19, iron_mg=0.02, magnesium_mg=2,
        phosphorus_mg=24, potassium_mg=24, sodium_mg=643, zinc_mg=0.1,
        copper_mg=0.01, manganese_mg=0.004, vit_a_rae_ug=680, vit_c_mg=0,
        vit_d_ug=1.4, vit_e_mg=2.4, vit_k_ug=7, thiamin_mg=0.005,
        riboflavin_mg=0.03, niacin_mg=0.04, vit_b6_mg=0.003, folate_ug=3,
        vit_b12_ug=0.1, phytate_g=0, oxalate_g=0, tannin_g=0,
        animal_protein_g=0.7)),
    dict(name="Walnüsse", category="nut", nutrients=dict(
        energy_kcal=654, protein_g=15.2, fat_g=65.2, carbs_g=7.0, fiber_g=6.7,
        sugar_g=2.6, calcium_mg=98, iron_mg=2.9, magnesium_mg=158,
        phosphorus_mg=346, potassium_mg=441, sodium_mg=2, zinc_mg=3.1,
        copper_mg=1.6, manganese_mg=3.4, vit_a_rae_ug=1, vit_c_mg=1.3,
        vit_d_ug=0, vit_e_mg=0.7, vit_k_ug=2.7, thiamin_mg=0.34,
        riboflavin_mg=0.15, niacin_mg=1.1, vit_b6_mg=0.54, folate_ug=98,
        vit_b12_ug=0, phytate_g=0.9, oxalate_g=0.03, tannin_g=0.05,
        animal_protein_g=0)),
    dict(name="Bananen", category="fruit", nutrients=dict(
        energy_kcal=89, protein_g=1.1, fat_g=0.3, carbs_g=20.0, fiber_g=2.6,
        sugar_g=12.0, calcium_mg=8, iron_mg=0.3, magnesium_mg=27,
        phosphorus_mg=22, potassium_mg=358, sodium_mg=1, zinc_mg=0.15,
        copper_mg=0.07, manganese_mg=0.27, vit_a_rae_ug=3, vit_c_mg=8.7,
        vit_d_ug=0, vit_e_mg=0.1, vit_k_ug=0.5, thiamin_mg=0.03,
        riboflavin_mg=0.07, niacin_mg=0.7, vit_b6_mg=0.37, folate_ug=20,
        vit_b12_ug=0, phytate_g=0.02, oxalate_g=0.01, tannin_g=0,
        animal_protein_g=0)),
    dict(name="Äpfel (mit Schale)", category="fruit", nutrients=dict(
        energy_kcal=52, protein_g=0.3, fat_g=0.2, carbs_g=13.8, fiber_g=2.4,
        sugar_g=10.4, calcium_mg=6, iron_mg=0.12, magnesium_mg=5,
        phosphorus_mg=11, potassium_mg=107, sodium_mg=1, zinc_mg=0.04,
        copper_mg=0.03, manganese_mg=0.04, vit_a_rae_ug=3, vit_c_mg=4.6,
        vit_d_ug=0, vit_e_mg=0.2, vit_k_ug=2.2, thiamin_mg=0.02,
        riboflavin_mg=0.03, niacin_mg=0.1, vit_b6_mg=0.04, folate_ug=3,
        vit_b12_ug=0, phytate_g=0.01, oxalate_g=0.01, tannin_g=0.03,
        animal_protein_g=0)),
    dict(name="Leinsamen", category="seed", nutrients=dict(
        energy_kcal=534, protein_g=18.3, fat_g=42.2, carbs_g=1.6, fiber_g=27.3,
        sugar_g=1.6, calcium_mg=255, iron_mg=5.7, magnesium_mg=392,
        phosphorus_mg=642, potassium_mg=813, sodium_mg=30, zinc_mg=4.3,
        copper_mg=1.2, manganese_mg=2.5, vit_a_rae_ug=0, vit_c_mg=0.6,
        vit_d_ug=0, vit_e_mg=0.3, vit_k_ug=4.3, thiamin_mg=1.6,
        riboflavin_mg=0.16, niacin_mg=3.1, vit_b6_mg=0.47, folate_ug=87,
        vit_b12_ug=0, phytate_g=1.6, oxalate_g=0.04, tannin_g=0.1,
        animal_protein_g=0)),
    dict(name="Salz (jodiert)", category="spice", nutrients=dict(
        energy_kcal=0, protein_g=0, fat_g=0, carbs_g=0, fiber_g=0,
        sugar_g=0, calcium_mg=24, iron_mg=0.3, magnesium_mg=0,
        phosphorus_mg=0, potassium_mg=8, sodium_mg=38760, zinc_mg=0,
        copper_mg=0, manganese_mg=0, vit_a_rae_ug=0, vit_c_mg=0,
        vit_d_ug=0, vit_e_mg=0, vit_k_ug=0, thiamin_mg=0, riboflavin_mg=0,
        niacin_mg=0, vit_b6_mg=0, folate_ug=0, vit_b12_ug=0, phytate_g=0,
        oxalate_g=0, tannin_g=0, animal_protein_g=0)),
    dict(name="Zwiebeln (roh)", category="vegetable", nutrients=dict(
        energy_kcal=40, protein_g=1.1, fat_g=0.1, carbs_g=9.0, fiber_g=1.7,
        sugar_g=4.2, calcium_mg=23, iron_mg=0.2, magnesium_mg=10,
        phosphorus_mg=29, potassium_mg=146, sodium_mg=4, zinc_mg=0.2,
        copper_mg=0.04, manganese_mg=0.13, vit_a_rae_ug=0, vit_c_mg=7.4,
        vit_d_ug=0, vit_e_mg=0.02, vit_k_ug=0.4, thiamin_mg=0.05,
        riboflavin_mg=0.03, niacin_mg=0.1, vit_b6_mg=0.12, folate_ug=19,
        vit_b12_ug=0, phytate_g=0.02, oxalate_g=0.01, tannin_g=0.02,
        animal_protein_g=0)),
    dict(name="Knoblauch", category="vegetable", nutrients=dict(
        energy_kcal=149, protein_g=6.4, fat_g=0.5, carbs_g=33.0, fiber_g=2.1,
        sugar_g=1.0, calcium_mg=181, iron_mg=1.7, magnesium_mg=25,
        phosphorus_mg=153, potassium_mg=401, sodium_mg=17, zinc_mg=1.2,
        copper_mg=0.3, manganese_mg=1.7, vit_a_rae_ug=0, vit_c_mg=31,
        vit_d_ug=0, vit_e_mg=0.08, vit_k_ug=1.7, thiamin_mg=0.2,
        riboflavin_mg=0.11, niacin_mg=0.7, vit_b6_mg=1.2, folate_ug=3,
        vit_b12_ug=0, phytate_g=0.05, oxalate_g=0.03, tannin_g=0,
        animal_protein_g=0)),
]

# ---------- Beispielrezepte ----------
def _seed_recipes(hh_id: int, ing_by_name: dict[str, Ingredient]) -> list[dict]:
    def ing(name): return ing_by_name[name]
    return [
        dict(name="Linseneintopf", servings=4, instructions="Zwiebeln anschwitzen, Linsen und Karotten zugeben, mit Wasser kochen.",
             lines=[
                 dict(ing_name="Linsen (getrocknet, braun)", grams_raw=300, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Karotten (roh)", grams_raw=200, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Zwiebeln (roh)", grams_raw=100, process_chain=["fry", "boil"], yield_factor=1.0),
                 dict(ing_name="Olivenöl", grams_raw=30, process_chain=["raw"], yield_factor=1.0),
                 dict(ing_name="Knoblauch", grams_raw=10, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Salz (jodiert)", grams_raw=6, process_chain=["raw"], yield_factor=1.0),
             ]),
        dict(name="Porridge mit Walnüssen", servings=2, instructions="Haferflocken in Milch kochen, mit Banane und Walnüssen servieren.",
             lines=[
                 dict(ing_name="Haferflocken (Vollkorn)", grams_raw=120, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Vollmilch (3.5 % Fett)", grams_raw=400, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Bananen", grams_raw=160, process_chain=["raw"], yield_factor=1.0),
                 dict(ing_name="Walnüsse", grams_raw=40, process_chain=["raw"], yield_factor=1.0),
                 dict(ing_name="Leinsamen", grams_raw=15, process_chain=["raw"], yield_factor=1.0),
             ]),
        dict(name="Hähnchen mit Brokkoli und Kartoffeln", servings=2, instructions="Hähnchen braten, Brokkoli dämpfen, Kartoffeln kochen.",
             lines=[
                 dict(ing_name="Hähnchenbrust (roh)", grams_raw=300, process_chain=["fry"], yield_factor=0.85),
                 dict(ing_name="Brokkoli (roh)", grams_raw=250, process_chain=["steam"], yield_factor=1.0),
                 dict(ing_name="Kartoffeln (roh)", grams_raw=300, process_chain=["boil"], yield_factor=1.0),
                 dict(ing_name="Olivenöl", grams_raw=20, process_chain=["raw"], yield_factor=1.0),
                 dict(ing_name="Salz (jodiert)", grams_raw=4, process_chain=["raw"], yield_factor=1.0),
             ]),
        dict(name="Sauerteigbrot (Fertigstellung: backen)", servings=10, instructions="Sauerteig führen, gehen lassen, backen.",
             lines=[
                 dict(ing_name="Weizenvollkornmehl (Type 1050)", grams_raw=500, process_chain=["sourdough", "proof", "bake"], yield_factor=0.9),
                 dict(ing_name="Roggenmehl (Type 1150)", grams_raw=300, process_chain=["sourdough", "proof", "bake"], yield_factor=0.9),
                 dict(ing_name="Salz (jodiert)", grams_raw=10, process_chain=["raw"], yield_factor=1.0),
             ]),
    ]


def seed(db_path: str = DB_PATH) -> None:
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()

    # Referenzdaten (idempotent)
    for n in NUTRIENTS:
        if not session.execute(select(NutrientDef).where(NutrientDef.key == n["key"])).scalar_one_or_none():
            session.add(NutrientDef(**n))
    for p in PROCESSES:
        if not session.execute(select(Process).where(Process.key == p["key"])).scalar_one_or_none():
            session.add(Process(**p))
    for r in INTERACTIONS:
        exists = session.execute(select(InteractionRule).where(
            InteractionRule.target == r["target"],
            InteractionRule.compound == r["compound"],
            InteractionRule.kind == r["kind"])).scalar_one_or_none()
        if not exists:
            session.add(InteractionRule(**r))

    # Demo-Haushalt (User-Accounts per CLI anlegen: python -m app.cli add-user)
    hh = session.execute(select(Household).where(Household.name == "Demo")).scalar_one_or_none()
    if hh is None:
        hh = Household(name="Demo")
        session.add(hh)
        session.flush()
        session.add(Person(household_id=hh.id, name="Ich", weight_kg=75, sex="m"))
        session.add(Person(household_id=hh.id, name="Partnerin", weight_kg=65, sex="f"))

    # Grundzutaten (global, household_id=None)
    ing_by_name: dict[str, Ingredient] = {}
    for i in INGREDIENTS:
        row = session.execute(select(Ingredient).where(
            Ingredient.household_id.is_(None),
            Ingredient.name == i["name"])).scalar_one_or_none()
        if row is None:
            row = Ingredient(household_id=None, name=i["name"],
                             category=i["category"], nutrients=i["nutrients"],
                             source="USDA FDC / SFK, kompiliert")
            session.add(row)
        ing_by_name[i["name"]] = row
    session.flush()

    # Beispielrezepte
    for rdef in _seed_recipes(hh.id, ing_by_name):
        exists = session.execute(select(Recipe).where(
            Recipe.household_id == hh.id, Recipe.name == rdef["name"])).scalar_one_or_none()
        if exists:
            continue
        recipe = Recipe(household_id=hh.id, name=rdef["name"],
                        servings=rdef["servings"], instructions=rdef["instructions"])
        session.add(recipe)
        session.flush()
        for ldef in rdef["lines"]:
            session.add(RecipeLine(recipe_id=recipe.id,
                                   ingredient_id=ing_by_name[ldef["ing_name"]].id,
                                   grams_raw=ldef["grams_raw"],
                                   process_chain=ldef["process_chain"],
                                   yield_factor=ldef["yield_factor"]))
        eng = RecipeEngine(session)
        eng.recipe_vector(recipe)

    # Vorrat-Demo
    if not session.execute(select(PantryItem).where(
            PantryItem.household_id == hh.id)).scalars().first():
        session.add(PantryItem(household_id=hh.id,
                               ingredient_id=ing_by_name["Kartoffeln (roh)"].id,
                               grams=1500, expires_on=date.today() + timedelta(days=5),
                               location="pantry"))
        session.add(PantryItem(household_id=hh.id,
                               ingredient_id=ing_by_name["Karotten (roh)"].id,
                               grams=600, expires_on=date.today() + timedelta(days=3),
                               location="fridge"))
        session.add(PantryItem(household_id=hh.id,
                               ingredient_id=ing_by_name["Spinat (roh)"].id,
                               grams=250, expires_on=date.today() + timedelta(days=2),
                               location="fridge"))
        session.add(PantryItem(household_id=hh.id,
                               ingredient_id=ing_by_name["Lachsfilet (roh)"].id,
                               grams=400, expires_on=date.today() + timedelta(days=2),
                               location="fridge"))
        session.add(PantryItem(household_id=hh.id,
                               ingredient_id=ing_by_name["Joghurt (3.5 % Fett)"].id,
                               grams=750, expires_on=date.today() + timedelta(days=6),
                               location="fridge"))

    session.commit()
    session.close()
    print(f"Seed fertig: {db_path}")


if __name__ == "__main__":
    seed()
