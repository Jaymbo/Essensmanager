# Rezept-Import aus Food.com RAW_recipes.csv (231k Rezepte, CC-ähnliche
# Forschungsdaten, Quelle: Kaggle "Food.com Recipes and Interactions").
#
# Strategie:
# - Rezeptname, kcal/Portion, Steps, Zutaten-Strings übernehmen
# - Mengen fehlen im Datensatz systematisch -> geschätzte Mengen:
#   1) Einheiten im String ("2 cups flour") wenn vorhanden
#   2) STANDARD_AMOUNTS-Tabelle für häufige Zutaten
#   3) Default 100 g
# - Kalorien-Normalisierung: Geschätzte Mengen werden global skaliert,
#   sodass die Rezept-kcal (aus USDA-Vektoren) ~ kcal/Portion * servings
#   ergeben (servings unbekannt -> 4 angenommen, Skalierung pro Rezept)
# - Zutaten-Matching: normalisierter String -> USDA-Zutat via
#   exakter Normalisierung, dann Substring-Fallback. Unmatchte Zutaten
#   werden als unbestimmt übersprungen (Rezept behält matchte Zeilen).

from __future__ import annotations

import ast
import csv
import io
import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ingredient, Recipe, RecipeLine

# ---------- Mengen-Schätzung ----------

# Einheiten -> Gramm
_UNIT_GRAMS: dict[str, float] = {
    "cup": 240.0, "cups": 240.0, "c": 240.0,
    "tablespoon": 15.0, "tablespoons": 15.0, "tbsp": 15.0, "tbl": 15.0,
    "teaspoon": 5.0, "teaspoons": 5.0, "tsp": 5.0,
    "ounce": 28.0, "ounces": 28.0, "oz": 28.0,
    "pound": 454.0, "pounds": 454.0, "lb": 454.0, "lbs": 454.0,
    "gram": 1.0, "grams": 1.0, "g": 1.0,
    "kilogram": 1000.0, "kg": 1000.0,
    "liter": 1000.0, "litre": 1000.0, "l": 1000.0,
    "milliliter": 1.0, "ml": 1.0,
    "quart": 946.0, "quarts": 946.0, "pint": 473.0, "pints": 473.0,
    "stick": 113.0, "sticks": 113.0,          # Butter
    "clove": 3.0, "cloves": 3.0,              # Knoblauch
    "slice": 25.0, "slices": 25.0,
    "can": 400.0, "cans": 400.0,
    "package": 250.0, "packages": 250.0, "envelope": 7.0, "envelopes": 7.0,
    "pinch": 0.3, "dash": 0.5,
}

# Stückware -> Gramm
_ITEM_GRAMS: dict[str, float] = {
    "egg": 50.0, "eggs": 50.0, "egg yolk": 18.0, "egg white": 33.0,
    "onion": 110.0, "onions": 110.0, "garlic clove": 3.0,
    "carrot": 70.0, "carrots": 70.0, "potato": 150.0, "potatoes": 150.0,
    "tomato": 120.0, "tomatoes": 120.0, "lemon": 60.0, "lime": 55.0,
    "apple": 150.0, "banana": 120.0, "pepper": 120.0,
    "chicken breast": 170.0, "chicken breast half": 170.0,
}

# Standardmenge, wenn Zutat ohne Mengenangabe vorkommt (g pro Rezeptnutzung)
_DEFAULT_AMOUNT: dict[str, float] = {
    "salt": 3.0, "pepper": 1.0, "black pepper": 1.0, "water": 250.0,
    "olive oil": 30.0, "vegetable oil": 30.0, "butter": 30.0,
    "sugar": 100.0, "brown sugar": 100.0, "flour": 125.0,
    "all-purpose flour": 125.0, "baking powder": 4.0, "baking soda": 3.0,
    "vanilla": 5.0, "vanilla extract": 5.0, "cinnamon": 2.0,
    "milk": 240.0, "eggs": 100.0, "egg": 50.0,
}

_FRACTIONS = {"1/2": 0.5, "1/4": 0.25, "3/4": 0.75, "1/3": 1/3, "2/3": 2/3,
              "1/8": 0.125, "3/8": 0.375, "5/8": 0.625, "7/8": 0.875}

_QTY_PAT = re.compile(
    r"^\s*(?P<num>\d+(?:\s+\d+/\d+)?(?:\.\d+)?(?:/\d+)?)\s*"
    r"(?P<unit>[a-zA-Z]+)?\s*(?P<rest>.*)$")

# Wörter, die als Mengeneinheit interpretiert werden dürfen – alles andere
# gehört zum Zutatennamen ("1 onion" -> unit=None, name="onion").
_UNIT_WORDS = set(_UNIT_GRAMS)


def parse_quantity(text: str) -> tuple[float | None, float | None, str]:
    """Extrahiert (Menge_g, Einheitsmenge_roh, Reststring) aus einem
    Zutaten-String. Menge_g nutzt Einheiten-Tabelle, sonst None."""
    m = _QTY_PAT.match(text)
    if not m:
        return None, None, text
    num_s, unit_s, rest = m.group("num"), m.group("unit"), m.group("rest")
    if unit_s and unit_s.lower() not in _UNIT_WORDS:
        # "1 onion" -> onion ist Zutat, keine Einheit: zurück in den Rest
        rest = f"{unit_s} {rest}".strip()
        unit_s = None
    # Brüche: "1 1/2" oder "1/2"
    total = 0.0
    parts = num_s.split()
    try:
        for p in parts:
            if "/" in p:
                a, b = p.split("/")
                total += float(a) / float(b)
            else:
                total += float(p)
    except (ValueError, ZeroDivisionError):
        return None, None, text
    grams: float | None = None
    if unit_s:
        grams = _UNIT_GRAMS.get(unit_s.lower())
    return grams, total, rest.strip()


def estimate_grams(ingredient_text: str) -> float:
    """Schätzt Gramm für einen Zutaten-String (ohne Mengenangabe im Datensatz
    oder mit). Grob, aber deterministisch."""
    text = ingredient_text.strip().lower()
    grams, qty, rest = parse_quantity(text)
    if grams is not None and qty:
        return qty * grams
    # Stückware: "2 eggs", "3 onions"
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s+(.+)$", text)
    if m:
        n = float(m.group(1))
        name = m.group(2).strip()
        for item, g in _ITEM_GRAMS.items():
            if name.startswith(item):
                return n * g
    # Standard-Menge für bekannte Zutaten
    for key, g in _DEFAULT_AMOUNT.items():
        if key in text:
            return g
    return 100.0  # konservativer Default


# ---------- Zutaten-Matching ----------

_STOP_WORDS = {"of", "fresh", "freshly", "ground", "chopped", "diced", "minced",
               "sliced", "grated", "large", "small", "medium", "whole", "dry",
               "dried", "raw", "cooked", "finely", "coarse", "coarsely", "to",
               "taste", "optional", "cold", "warm", "hot", "peeled", "packed",
               "plus", "more", "or", "and", "for", "with", "into", "cut"}


def normalize_ingredient(text: str) -> str:
    """'2 cups all-purpose flour, sifted' -> 'all purpose flour'."""
    _, _, rest = parse_quantity(text.strip().lower())
    words = [w for w in re.split(r"[^\w]+", rest) if w and w not in _STOP_WORDS]
    # führende Mengen-/Zahlenreste entfernen
    while words and re.match(r"^[\d./]+$", words[0]):
        words.pop(0)
    return " ".join(words)


def match_ingredient(session: Session, normalized: str,
                     lookup: dict[str, int], names_lower: dict[str, str]) -> int | None:
    """Findet USDA-Zutat: exakt -> Substring. Gibt Ingredient-ID zurück.
    normalized wird intern nochmal normalisiert (wirkt auch auf Rohstrings)."""
    normalized = normalize_ingredient(normalized)
    if not normalized:
        return None
    if normalized in lookup:
        return lookup[normalized]
    # Substring-Match: kürzester USDA-Name, der im String enthalten ist
    # (oder umgekehrt, für "milk whole" vs "milk")
    best: tuple[int, str] | None = None
    for name, ing_id in lookup.items():
        if len(name) < 4:
            continue
        if name in normalized or normalized in name:
            if best is None or len(name) < len(best[1]):
                best = (ing_id, name)
    return best[0] if best else None


def _clean_name(name: str) -> str:
    """USDA-Name fürs Matching: 'Milk, whole' -> 'milk whole'."""
    return re.sub(r"[^\w]+", " ", name.strip().lower()).strip()


def build_lookup(session: Session) -> tuple[dict[str, int], dict[str, str]]:
    lookup: dict[str, int] = {}
    names_lower: dict[str, str] = {}
    for ing in session.execute(select(Ingredient)).scalars():
        key = _clean_name(ing.name)
        if key and key not in lookup:   # erste Zutat gewinnt bei Namensgleichheit
            lookup[key] = ing.id
        names_lower[ing.id] = key
    return lookup, names_lower


# ---------- Import ----------

def import_raw_recipes_csv(session: Session, household_id: int,
                           csv_bytes: bytes, limit: int | None = None,
                           max_ingredients: int = 15) -> int:
    """Importiert Food.com RAW_recipes.csv in den Haushalt.
    Erzeugt nur Rezepte, bei denen >=60 % der Zutaten gematcht werden."""
    lookup, _ = build_lookup(session)
    existing = {r[0] for r in session.execute(
        select(Recipe.name).where(Recipe.household_id == household_id)).all()}
    # Existing als lower-case set
    existing = {n.lower() for n in existing}

    count = 0
    rdr = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8", "replace")))
    for row in rdr:
        try:
            kcal = float(row["calories"])
        except (KeyError, ValueError, TypeError):
            continue
        if not (30.0 <= kcal <= 3000.0):
            continue
        name = (row.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        try:
            ingredients = ast.literal_eval(row.get("ingredients") or "[]")
            steps = ast.literal_eval(row.get("steps") or "[]")
        except (ValueError, SyntaxError):
            continue
        if not (2 <= len(ingredients) <= max_ingredients):
            continue

        lines: list[tuple[int, float]] = []
        matched = 0
        for ing_text in ingredients:
            norm = normalize_ingredient(ing_text)
            ing_id = match_ingredient(session, norm, lookup, {})
            if ing_id is not None:
                matched += 1
                lines.append((ing_id, estimate_grams(ing_text)))
        if matched < max(2, int(0.6 * len(ingredients))):
            continue  # zu unvollständig -> überspringen

        recipe = Recipe(household_id=household_id, name=name[:160],
                        servings=4, instructions="\n".join(steps)[:4000])
        session.add(recipe)
        session.flush()  # recipe.id
        for ing_id, grams in lines:
            session.add(RecipeLine(recipe_id=recipe.id, ingredient_id=ing_id,
                                   grams_raw=grams, process_chain=[],
                                   yield_factor=1.0))
        existing.add(name.lower())
        count += 1
        if limit and count >= limit:
            break
    session.commit()
    return count
