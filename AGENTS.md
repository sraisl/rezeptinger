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
make setup
make server
```

Run the Huey worker in a second terminal when testing extraction end-to-end:

```bash
make worker
```

## Dev Environment Start And Restart

Start or restart the local dev environment in this order:

1. Stop any running Django `runserver` process.
2. Stop any running Huey worker process.
3. Apply migrations:

```bash
make migrate
```

4. Start the Django dev server:

```bash
make server
```

5. Start the Huey worker in a separate terminal:

```bash
make worker
```

Always restart both the web server and the Huey worker after code changes that affect models,
migrations, extraction services, tasks, settings, or dependencies. A stale Huey worker can keep
processing queued extractions with old code even while the web server is already running the new
code.

Quality checks:

```bash
make check
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
- When completing a task from `TODO.md`, update `TODO.md` in the same change: move completed
  items to `Done` and promote the next actionable item into `Next`.

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

## Admin

The Django admin is available at `http://127.0.0.1:8000/admin/`.

Create a local admin user when needed:

```bash
mise exec uv -- uv run python manage.py createsuperuser
```

Rezeptinger app settings are admin-only. Edit LM Studio base URL, selected model/default model,
transcript limit, language preference, and extraction prompt through `App settings` in Django
admin, not through a public app page.

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
