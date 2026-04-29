# Rezeptinger

Ein kleiner Django-Monolith, der YouTube-URLs annimmt, Rezeptinformationen aus Transkripten extrahiert und als Katalog speichert. Die KI-Extraktion läuft über LM Studio mit der OpenAI-kompatiblen lokalen API.

## Setup

```bash
mise install
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

LM Studio muss mit aktiviertem lokalen Server laufen, typischerweise:

```text
http://localhost:1234/v1
```

Optional kannst du das Modell oder die URL per Environment überschreiben:

```bash
export LM_STUDIO_BASE_URL=http://localhost:1234/v1
export LM_STUDIO_MODEL=local-model
```

## Docker lokal

Das Docker-Image ist derzeit bewusst ein lokales Entwicklungsimage. Es nutzt Django `runserver`, führt beim Start automatisch Migrationen aus und speichert SQLite standardmäßig unter `/data/db.sqlite3`.

Image bauen:

```bash
docker build -t rezeptinger:local .
```

Container mit benanntem Volume starten:

```bash
docker run --rm --name rezeptinger-local -p 8000:8000 \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v rezeptinger-data:/data \
  rezeptinger:local
```

Die App ist danach unter <http://127.0.0.1:8000/> erreichbar.

### LM Studio aus Docker erreichen

Im Container ist `localhost` der Container selbst. Für LM Studio auf dem Host nutzt du auf Docker Desktop:

```text
http://host.docker.internal:1234/v1
```

Ohne Docker ist die passende lokale URL weiterhin:

```text
http://localhost:1234/v1
```

### Datenbankvarianten

Empfohlen für Docker: benanntes Volume. Die Daten bleiben erhalten, auch wenn der Container mit `--rm` entfernt wird:

```bash
docker run --rm --name rezeptinger-local -p 8000:8000 \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v rezeptinger-data:/data \
  rezeptinger:local
```

Alternative: lokale Projekt-`db.sqlite3` direkt in den Container mounten:

```bash
docker run --rm --name rezeptinger-local -p 8000:8000 \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v "$PWD/db.sqlite3:/data/db.sqlite3" \
  rezeptinger:local
```

Nutze dabei nicht gleichzeitig den lokalen Django-Runserver und den Container gegen dieselbe SQLite-Datei.

### Container stoppen, Logs ansehen

Wenn der Container im Vordergrund läuft, stoppst du ihn mit `Ctrl-C`.

Wenn er im Hintergrund gestartet wurde:

```bash
docker logs -f rezeptinger-local
docker stop rezeptinger-local
```

### Wichtige Environment-Variablen

```bash
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_MODEL=
SQLITE_DATABASE_PATH=/data/db.sqlite3
```

Wenn `LM_STUDIO_MODEL` leer ist, versucht die App das erste in LM Studio geladene Modell automatisch über `/v1/models` zu finden.

## Hinweise

Die App nutzt `yt-dlp`, um Metadaten und Untertitel/Auto-Untertitel zu lesen. Videos ohne nutzbares Transkript können derzeit nicht zuverlässig ausgewertet werden.

## Headless API

Extraktion starten:

```bash
curl -X POST http://127.0.0.1:8000/api/extractions/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=..."}'
```

Die Antwort enthält `status_url`, die du pollen kannst:

```bash
curl http://127.0.0.1:8000/api/extractions/1/
```

Sobald `status` den Wert `done` hat, ist im Feld `recipe` das extrahierte Rezept enthalten.

## Daten exportieren und importieren

Im Browser findest du die Funktionen unter `Daten`.

Headless Export:

```bash
curl http://127.0.0.1:8000/data/export/ -o rezeptinger.json
```

Headless Import:

```bash
curl -X POST http://127.0.0.1:8000/data/import/ \
  -H 'Content-Type: application/json' \
  --data-binary @rezeptinger.json
```
