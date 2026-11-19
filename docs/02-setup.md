# Setup & Deployment

## Lokal entwickeln
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed        # erstellt DB + Seed-Daten
uvicorn app.main:app --reload
# → http://localhost:8010
```

## Server (Docker)
```bash
ssh server
git clone git@github.com:Jaymbo/Essensmanager.git && cd Essensmanager
docker compose up -d --build
```
- SQLite-Datei liegt im Volume `essensmanager-data:/data/app.db` (bleibt bei Rebuilds erhalten).
- Port auf dem Host: **8010**.

## Cloudflare Zero Trust
Subdomain (z.B. `essen.<deine-domain>`) → **HTTP** → `localhost:8010`
(sorgt dafür, dass der Tunnel-Connector auf demselben Host läuft, `cloudflared`).

## Updates
```bash
cd Essensmanager && git pull && docker compose up -d --build
```
