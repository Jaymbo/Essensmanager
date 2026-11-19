# Domain-Modell & Berechnungsvorschriften

## Vektoren
- `NutrientVector = dict[str, float]` (Key = `NutrientDef.key`, z.B. `vit_c`).
- Aggregation: `add(a, b)` – einfache Summe (Mengen-Linearkombination).

## Kochprozesse
- `ProcessEffect(process_key, nutrient_key, factor)` – Faktor ∈ [0,1+]
  (Fermentieren kann z.B. B-Vitamine **erhöhen**, Faktor > 1 erlaubt).
- `apply_process(v, process_key)` = komponentenweise Multiplikation mit Faktor
  (Fehlender Faktor ⇒ 1.0, unverändert).
- Prozesskette: linke Anwendung in Reihenfolge: `raw → fry → bake`.
- Energie (kcal) wird bei Prozessen mit Fettverlust/-aufnahme über
  `fat`-Faktor mitgeführt; `energy` skaliert mit (da kcal ≈ 4/4/9 g).

## Bioverfügbarkeit
`absorbed = absorb_efficiency(nutrient) · interaction_factor(compounds) · saturation(intake) · intake`

- `compounds` = hemmende/fördernde Stoffe der **gesamten Mahlzeit** (Summe über
  Zutaten: `phytate_g, oxalate_g, tannin_g, animal_protein_g, vit_c_mg, fat_g, calcium_mg`).
- Interaktionsformeln (Sättigungsfunktionen, Quelle in `Interaction.source`):
  - Fe: `f = (1 + 0.9·min(vitC/75,1.5)) · (1 − 0.55·min(phytate/3,1)) · (1 − 0.4·min(ca/300,1)) · (1 − 0.3·min(tannin/0.5,1))`, Häm-Fe (über animal_protein-Anteil) separat ~25 %.
  - Zn: `f = 1 − 0.45·min(phytate/3,1) + 0.2·min(animal_protein/40,1)`
  - Ca: `f = 1 − 0.3·min(oxalate/1.5,1)`
  - A/D/E/K: `f = 1 + 0.5·min(fat/20,1)`
- B12-Sättigung: `min(intake,1.5)·0.5 + max(intake−1.5,0)·0.01`

## Pools (Körperspeicher)
- `pool[t+1] = pool[t] · 0.5^(1/half_life_days) + absorbed[t]`, ggf. cap `pool_capacity`.
- Nährstoffe ohne Pool (z.B. Energie): `half_life_days = None` → nur Tagesbilanz.

## Zielbereich
- Pro Person: `daily_min/daily_max` aus `NutrientDef` (DACH-Referenz, Erwachsene),
  überschreibbar per `Person.target_override_json` (Gewicht/Sex/Alter skaliert).
- Bewertung pro Tag: Status `under / in_range / over` je Dimension.
