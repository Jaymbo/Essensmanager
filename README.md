# Essensmanager

Ernährungsmanager, der Nahrung als **Vektor im Nährstoffraum** modelliert:
Grundzutaten → Kochprozesse (Retentionsfaktoren) → Bioverfügbarkeit
(Interaktionen, Sättigungskinetik) → Körperspeicher-Pools (Halbwertszeit) →
Zielbereich (Min/Max pro Nährstoff).

## Features (V1)

- Nährstoffraum mit ~25 Dimensionen inkl. DACH-Zielbereich (Min/Max)
- 12 Kochprozesse als editierbare Retentionsfaktor-Maps (USDA/Bognár-Quellen)
- Bioverfügbarkeit: 13 Interaktionsregeln (z.B. Vitamin C ↔ Eisen, Phytat ↮ Zink),
  B12-Sättigungskinetik, Speicher-Pools mit Halbwertszeit
- Rezept-Engine aus Grundzutaten (keine Fertigprodukt-Datenbank), Suche nach
  Name/Zutat/Prozess/Nährwertgrenzen, Rezepte modifizierbar
- Tagebuch + Dashboard: Tagesaufnahme vs. Zielbereich + Pool-Verlauf
- Halbautomatischer 3-Tage-Planer mit Vorrats-Priorität (ablaufende Ware zuerst)
- USDA FoodData Central CSV-Import
- Multi-Haushalt mit Login (PBKDF2), Personenprofile mit Ziel-Overrides

## Quickstart (lokal)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed_data app.db                 # Referenzdaten + Demo-Haushalt
python -m app.cli add-user Demo meinuser       # Login anlegen (Passwort-Abfrage)
EM_DB_PATH=app.db uvicorn app.main:app --port 8010
# → http://localhost:8010
```

## Deployment (Docker, Port 8010)

```bash
docker compose up -d --build
docker compose exec essensmanager python -m app.seed_data /data/app.db
docker compose exec essensmanager python -m app.cli add-user MeinHaushalt meinuser
```

SQLite liegt im Volume `essensmanager-data` (überlebt Rebuilds).
**Cloudflare Zero Trust:** Subdomain → HTTP → `http://localhost:8010`.

## Architektur

Siehe `docs/00-high-level-view.md` (Module, Datenfluss, Erweiterungspunkte)
und `docs/01-domain-model.md` (Berechnungsvorschriften). Domain-Kern ist
pure Python ohne I/O (`app/domain/`), Services orchestrieren (`app/`),
Tests in `tests/`.

```
app/
├── domain/           # Kern: Vektorraum, Prozesse, Bioverfügbarkeit (pure)
├── templates/        # Jinja2-UI
├── models.py         # SQLAlchemy-Schema
├── recipe_engine.py  # Rezeptvektoren + Suche
├── body_simulator.py # Resorption + Pools
├── planner.py        # Greedy-Mehrtagesplanung
├── importer.py       # USDA FDC CSV
├── seed_data.py      # Referenzdaten (Nährstoffe/Prozesse/Interaktionen/Zutaten)
├── main.py           # FastAPI-Routen + Auth
└── cli.py            # User-Verwaltung
```

## Tests

```bash
pytest -q
```
