# Rezeptinger

Ein kleiner Django-Monolith, der YouTube-URLs annimmt, Rezeptinformationen aus Transkripten extrahiert und als Katalog speichert. Die KI-Extraktion läuft über LM Studio mit der OpenAI-kompatiblen lokalen API.

## Setup

```bash
mise install
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Extraktionen laufen über Huey. Starte in einem zweiten Terminal den Worker:

```bash
uv run python manage.py run_huey
```

LM Studio muss mit aktiviertem lokalen Server laufen, typischerweise:

```text
http://localhost:1234/v1
```

Optional kannst du das Modell oder die URL per Environment überschreiben:

```bash
export LM_STUDIO_BASE_URL=http://localhost:1234/v1
export LM_STUDIO_MODEL=google/gemma-4-e2b
```

### Modellwahl

Standardmäßig verwendet die App dieses LM-Studio-Modell:

```text
google/gemma-4-e2b
```

Du kannst es jederzeit per `LM_STUDIO_MODEL` überschreiben. Das ist relevant, weil Rezeptinger von LM Studio eine strukturierte JSON-Antwort erwartet. Chat- oder Instruct-Modelle befolgen solche Ausgabevorgaben meist zuverlässiger als Base-Modelle; Embedding-Modelle sind für die Extraktion nicht geeignet.

Wenn `LM_STUDIO_MODEL` leer ist, versucht die App ein geeignetes geladenes Modell über `/v1/models` zu finden. Dabei werden Chat/Instruct-nahe Modelle bevorzugt und Embedding-Modelle ignoriert.

## Admin

Der Django-Admin ist lokal unter <http://127.0.0.1:8000/admin/> erreichbar. Falls noch kein
Admin-User existiert, lege ihn so an:

```bash
uv run python manage.py createsuperuser
```

Die Rezeptinger-Einstellungen wie LM-Studio-URL, Modell, Transkript-Limit, Sprachpräferenz und
Extraktionsprompt werden nur im Admin unter `App settings` bearbeitet.

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

### Docker Compose

Empfohlen für den lokalen Docker-Betrieb ist Compose. Es baut das lokale Image, bindet Port `8000`
und speichert SQLite/Huey dauerhaft im benannten Volume `rezeptinger-data`:

```bash
docker compose up --build
```

Die App ist danach unter <http://127.0.0.1:8000/> erreichbar.

Wenn Extraktionen verarbeitet werden sollen, starte den optionalen Worker mit:

```bash
docker compose --profile worker up --build
```

Logs und Stop:

```bash
docker compose logs -f
docker compose down
```

Der Container hat einen Docker-Healthcheck gegen `/health/`. Den Status siehst du mit:

```bash
docker compose ps
```

Der Prozess läuft im Container als non-root User `rezeptinger`. Das Volume `/data` ist für diesen
User beschreibbar, damit SQLite und Huey dort Dateien anlegen können.

Das Datenvolume bleibt bei `docker compose down` erhalten. Entferne es nur bewusst:

```bash
docker compose down -v
```

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
LM_STUDIO_MODEL=google/gemma-4-e2b
SQLITE_DATABASE_PATH=/data/db.sqlite3
YT_DLP_COOKIES_FILE=
```

Wenn du im Container ein anderes Modell nutzen willst, setze `LM_STUDIO_MODEL` beim Start explizit mit `-e LM_STUDIO_MODEL=...`.

### Huey Worker

Der Webserver legt Extraktionen nur in die Queue. Für die eigentliche Verarbeitung muss zusätzlich ein Worker laufen.

Lokal:

```bash
uv run python manage.py run_huey
```

Mit Docker im zweiten Terminal:

```bash
docker run --rm --name rezeptinger-worker \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v rezeptinger-data:/data \
  rezeptinger:local \
  python manage.py run_huey
```

Wenn du die lokale `db.sqlite3` mountest, nutze für Web und Worker denselben Mount:

```bash
docker run --rm --name rezeptinger-worker \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v "$PWD/db.sqlite3:/data/db.sqlite3" \
  -v "$PWD/huey.sqlite3:/data/huey.sqlite3" \
  rezeptinger:local \
  python manage.py run_huey
```

Für Tests oder Spezialfälle kann Huey synchron laufen:

```bash
HUEY_IMMEDIATE=1 uv run python manage.py test
```

## Hinweise

Die App nutzt `yt-dlp`, um Metadaten und Untertitel/Auto-Untertitel zu lesen. Videos ohne nutzbares Transkript können derzeit nicht zuverlässig ausgewertet werden.

Wenn YouTube `HTTP 429: Too Many Requests` meldet, blockt YouTube die aktuelle Abrufrate oder IP temporär. Warte dann etwas und versuche es erneut. Falls das häufiger passiert, kannst du yt-dlp mit einer Cookie-Datei aus deinem Browser starten:

```bash
export YT_DLP_COOKIES_FILE=/pfad/zu/cookies.txt
```

Im Docker-Setup muss die Datei zusätzlich in den Container gemountet und der Container mit `-e YT_DLP_COOKIES_FILE=/data/cookies.txt` gestartet werden.

## Bookmarklet

Im Browser findest du unter `Tools` ein Bookmarklet. Damit kannst du eine geöffnete YouTube-Seite
direkt an Rezeptinger senden.

So richtest du es ein:

1. Starte Rezeptinger lokal und öffne <http://127.0.0.1:8000/bookmarklet/>.
2. Ziehe den Button `An Rezeptinger senden` in die Lesezeichenleiste deines Browsers.
3. Öffne ein YouTube-Video.
4. Klicke in der Lesezeichenleiste auf `An Rezeptinger senden`.

Rezeptinger übernimmt die aktuelle YouTube-URL, startet die Extraktion und öffnet die
Quell-Detailseite. Das Bookmarklet akzeptiert nur YouTube-URLs.

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
