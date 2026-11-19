# Roadmap (V1-Umfang & spätere Erweiterungen)

## V1 – aktueller Scope
- [x] Multi-Tenant lite: Haushalte mit Login, Personenprofile mit Ziel-Overrides
- [x] Nährstoffraum (~38 Dimensionen) mit Min/Max-Zielbereich
- [x] Grundzutaten-DB + Import-Skript (USDA FoodData Central CSV)
- [x] Kochprozesse als editierbare Retentionsfaktor-Maps (Seed mit Quellen)
- [x] Rezept-Engine: Prozessketten, gecachte Vektoren, Suche, Modifikation
- [x] Bioverfügbarkeit: Interaktions-Matrix, Sättigungskinetik (B12), Pools mit Halbwertszeit
- [x] Dashboard: Tagesbilanz + Pool-Zeitverlauf vs. Zielbereich
- [x] Tagebuch (Log-Einträge) als Basis der Simulation
- [x] Halbautomatischer 3-Tage-Planer (Greedy, Vorratspriorität)
- [x] Vorratsverwaltung (Menge, Ablaufdatum, Status)
- [x] Docker-Deployment (Port 8010) + Cloudflare-Hinweis

## V2+ (Schnittstellen sind vorbereitet, siehe High-Level-View §5)
- Feed/Detail-Modell: USDA-Quellenangaben pro Zutat anzeigen
- Import UEB / andere Quellen als weiterer Adapter
- Optimierer (ILP statt Greedy) hinter `PlanStrategy`
- Rezept-Export/Import (JSON) zum Teilen zwischen Haushalten
- Mobile PWA-Layout
