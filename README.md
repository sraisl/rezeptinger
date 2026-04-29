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
