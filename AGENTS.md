# Agent Instructions

This repository is a small Django monolith for extracting recipes from YouTube transcripts and storing them in a local catalog.

## Stack

- Python is managed through `mise`.
- Python packages and commands should run through `uv`.
- Web framework: Django.
- Database: SQLite.
- Extraction input: YouTube metadata/transcripts via `yt-dlp`.
- AI extraction: LM Studio through its OpenAI-compatible local API.
- Frontend: Django templates, one CSS file, minimal vanilla JavaScript.

## Common Commands

```bash
mise install
mise exec uv -- uv sync --python 3.12
mise exec uv -- uv run python manage.py migrate
mise exec uv -- uv run python manage.py runserver 127.0.0.1:8000
```

Run the Huey worker in a second terminal when testing extraction end-to-end:

```bash
mise exec uv -- uv run python manage.py run_huey
```

Quality checks:

```bash
mise exec uv -- uv run ruff check .
mise exec uv -- uv run python manage.py test
```

## Project Layout

- `rezeptinger/`: Django project settings and root URL config.
- `recipes/`: Main app with models, views, templates, static CSS, services, and tests.
- `recipes/services/youtube.py`: Fetches YouTube metadata and captions.
- `recipes/services/lmstudio.py`: Talks to LM Studio.
- `recipes/services/extractor.py`: Coordinates extraction and background processing.
- `recipes/tasks.py`: Huey tasks for queued extraction.
- `recipes/services/portable_data.py`: JSON import/export.

## Development Notes

- Keep the app simple and monolithic unless there is a clear need to split it.
- Prefer server-rendered Django templates over adding a frontend framework.
- Use SQLite-friendly logic.
- Extraction is queued through Huey. Keep web and worker behavior compatible with local SQLite.
- If adding external dependencies, put them in `pyproject.toml` and sync with `uv`.
- Keep import/export backwards-friendly by bumping the export `version` if the JSON format changes.

## LM Studio

The app defaults to:

```text
http://localhost:1234/v1
```

If `LM_STUDIO_MODEL` is empty, the app tries to discover the first loaded model from `/v1/models`.

Useful environment variables:

```bash
export LM_STUDIO_BASE_URL=http://localhost:1234/v1
export LM_STUDIO_MODEL=
```

## API Surface

Start extraction:

```bash
curl -X POST http://127.0.0.1:8000/api/extractions/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=..."}'
```

Poll extraction:

```bash
curl http://127.0.0.1:8000/api/extractions/1/
```

Export catalog:

```bash
curl http://127.0.0.1:8000/data/export/ -o rezeptinger.json
```

Import catalog:

```bash
curl -X POST http://127.0.0.1:8000/data/import/ \
  -H 'Content-Type: application/json' \
  --data-binary @rezeptinger.json
```

## Verification Before Handoff

Run these before considering a code change done:

```bash
mise exec uv -- uv run ruff check .
mise exec uv -- uv run python manage.py test
```
