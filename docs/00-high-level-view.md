# Essensmanager – High-Level View (V1)

> **Prinzip:** Diese Datei beschreibt WAS das System tut und WIE die Module
> zusammenwirken – bevor Code gelesen wird. Bei jeder Erweiterung: zuerst
> hier ändern, dann implementieren.

## 1. Vision

Ein selbst gehosteter Ernährungsmanager, der Nahrung **nicht als „Produkt mit
Nährwerttabelle"** behandelt, sondern als **Vektor im n-dimensionalen
Nährstoffraum**, der sich durch Grundzutaten, Mengen und Kochprozesse
deterministisch ergibt. Ziel: jederzeit sichtbar machen, was im Körper
**fehlt, zu viel ist oder passt** – über Zeitverläufe und Speicher-Pools.

## 2. Kernkonzepte (Domain)

### 2.1 Nährstoffraum
- Jede Lebensmittelmenge / jedes Rezept / jeder Tagesplan ist ein Vektor
  `v ∈ ℝⁿ` (n ≈ 30–40 Nährstoffe, definiert in `NutrientDef`).
- Jede Dimension hat: Einheit, Tages-Minimum (z.B. DACH-Referenz),
  Tages-Maximum (UL), Aufnahme-Effizienz, Halbwertszeit + Kapazität des
  Körper-Speichers (Pools).
- **Zielbereich** = Min-Vektor ≤ Essensvektor ≤ Max-Vektor (pro Person/Tag).

### 2.2 Kochprozesse als Transformationen
- Ein Prozess (braten, backen, frittieren, fermentieren, gehen lassen, …)
  ist eine **Retentionsfaktor-Map**: `v' = M_p · v` mit
  `M_p[i] = Retentionsfaktor` des Prozesses p für Nährstoff i.
- Rezepte wenden Prozessketten auf Zutatenzeilen an (`roh → anbraten →
  backen`). Alle Faktoren sind **editierbar und quellenreferenziert**
  (USDA Retention Factors, Bognár-Tabellen, Studien).

### 2.3 Bioverfügbarkeit (Feinmodell V1)
Drei Mechanismen, in dieser Reihenfolge angewendet:
1. **Interaktions-Matrix:** Co-präsente Verbindungen modifizieren Aufnahme
   (z.B. Vitamin C ↑ Nicht-Häm-Eisen ×2–3, Phytate ↓ Zn/Fe, Oxalat ↓ Ca,
   Fett ↑ fettlösliche Vitamine, Ca ↓ Fe). Implementiert als
   Faktor-Funktionen mit Sättigung, nicht als simple Multiplikation.
2. **Sättigungskinetik:** z.B. B12: aktiver IF-Transport gesättigt bei
   ~1,5 µg/Mahlzeit, Rest nur ~1 % passiv. → `absorbed = f(intake)`.
3. **Speicher-Pools:** Pro Nährstoff ein Pool mit Halbwertszeit
   (z.B. B12-Leber ~1 Jahr, Vit-A ~140 d, Vit-C ~30 d, wasserlösliche B-Vitamine
   Stunden–Tage) und ggf. Kapazität. Ergibt den **Vektorverlauf über die Zeit**.

### 2.4 Körpersimulation
- Eingabe: Log aller Mahlzeiten (Rezepte/Einzelzutaten) pro Person.
- Ausgabe: Zeitreihe pro Nährstoff: `aufgenommen → resorbiert → Pool →
  Defizit/Überschuss` vs. Zielbereich (als Bereichsband, nicht als Linie).

## 3. Module & Interaktion

```
┌───────────────────────────── Web-UI (Jinja2/HTMX, responsive) ─────────────────────────────┐
│  Dashboard   Rezepte   Zutaten   Planer   Vorrat   Tagebuch   Verwaltung                   │
└──────┬──────────────────────────────────────────────────────────────────────┬──────────────┘
       │ (server-seitig gerendert, Formulare/HTMX)                            │
┌──────▼─────────────────────── API/Schicht (FastAPI) ────────────────────────▼──────────────┐
│  auth   │  routes_*  │  services: planner, body_simulator, recipe_engine, importer         │
└──────┬─────────────────────────────────────────────────────────────────────┬───────────────┘
       │                                                                     │
┌──────▼───────────────────── Domain-Kern (pure Python) ─────────────────────▼───────────────┐
│  nutrient_space   (Vektoren, Min/Max-Ziele, Aggregation)                                   │
│  processes        (Retentions-Transformationen, Prozessketten)                             │
│  bioavailability  (Interaktions-Matrix, Sättigung, Pools, Zeitverlauf)                     │
└──────┬─────────────────────────────────────────────────────────────────────────────────────┘
       │
┌──────▼─────────── Persistenz (SQLAlchemy + SQLite, Datei im Volume) ───────────────────────┐
│  Household/User/Person · NutrientDef · Ingredient · Process/ProcessEffect · Interaction    │
│  Recipe/RecipeLine · PantryItem · MealPlan/PlanEntry · LogEntry                            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Regeln:**
- Domain-Kern ist **pure Python ohne I/O** → testbar, in späteren UIs/APIs wiederverwendbar.
- Services orchestrieren Domain + DB. Routes kennen Domain nur über Services.
- Alle Daten sind **haushaltsbezogen** (Multi-Tenant lite); Nährstoffdefinitionen,
  Prozesse und Interaktionen sind **global** (Referenzdaten), Zutaten/Rezepte je
  Haushalt (+ globale Seeds, kopierbar/modifizierbar).

## 4. Datenfluss (zentrale Szenarien)

### S1 Rezept-Nährwerte berechnen
`Zutatenzeilen (g) → v_i · g/100 → Prozesskette p1..pk → Σ = Rezeptvektor`
→ gecached in `Recipe.nutrient_json`, bei jeder Änderung neu berechnet.

### S2 Tages-/Zeitverlauf („was fehlt, was zu viel")
`LogEntry-Tage → Mahlzeiten-Vektoren → Bioverfügbarkeit (S2.1–S2.3) →
Pool-Dynamik (Tagesauflösung) → Vergleich mit Zielbereich`
Dashboard zeigt: rote Dimensionen (unter Min), orange (über Max),grün (in Bereich)
– sowohl für Tagesaufnahme als auch Pool-Füllstand.

### S3 Mehrtages-Planung (halbautomatisch)
1. Nutzer gibt: Tage (z.B. 3), Personen, gewünschte Rezept-/Zutaten-Pools, „Vorrat bevorzugen".
2. Planer (Greedy-Optimierung) wählt aus Kandidaten Zuordnungen Tag/Mahlzeit,
   minimiert Abweichung vom Zielbereich, priorisiert ablaufende Vorräte.
3. Nutzer bestätigt/passt an → Plan wird zu LogEntries beim Verzehr.

### S4 Zutaten-Import
`importer` liest USDA FoodData Central (CSV/JSON-Export) → mappt Nährstoff-IDs
auf unsere Dimensionen → legt/aktualisiert `Ingredient`-Vektoren (Quelle vermerkt).
Keine Fertigprodukte: Produkte werden als **Rezepte aus Grundzutaten** modelliert.

## 5. Erweiterbarkeit (bewusste Schnitte)

| Erweiterung später | Schnittstelle, an der es andockt |
|---|---|
| Neue Kochprozesse | `Process` + `ProcessEffect` (Daten, kein Code) |
| Neue Interaktionen | `Interaction`-Zeilen (Daten) |
| Neue Nährstoffe | `NutrientDef`-Zeile; Vektorcode generisch |
| Optimierer statt Greedy | `services/planner.py` implementiert `PlanStrategy` |
| Rezept-Suche semantisch | `services/recipe_engine.py` → Search-Adapter |
| Mobile App | Domain/Services über JSON-API (FastAPI) nutzbar |
| LLM-Kochassistent |nutzt Rezept-Engine + Planer als Werkzeuge |

## 6. Deployment

- Ein Docker-Container (App + SQLite-Datei im Volume), Port 8010.
- Läuft auf `server` (SSH-Alias), Reverse-Proxy via **Cloudflare Zero Trust**:
  Subdomain → `http://localhost:8010` (cloudflared läuft auf demselben Host).
- Repo: `git@github.com:Jaymbo/Essensmanager.git`
