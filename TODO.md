# TODO

## Next

- [ ] Decide the next product-focused improvement.

## Product

## Search And Data

## Extraction

## Won't Do

- [ ] Audio transcription fallback for videos without captions, to keep the local app simple.

## Docker And Deployment


## CI And Security


## Done

- [x] Add a GitHub release flow where tags like `vX.Y.Z` publish GHCR images and release notes.
- [x] Add container image vulnerability scanning with Trivy in Makefile and CI.
- [x] Upload container security findings as SARIF in GitHub Actions.
- [x] Add Dockerfile linting with Hadolint in Makefile and CI.
- [x] Add Makefile task runner for local setup, dev server, worker, checks, and Docker tasks.
- [x] Add a production-style container variant with Gunicorn instead of Django `runserver`.
- [x] Run the container as a non-root user.
- [x] Add a Docker healthcheck endpoint and Dockerfile `HEALTHCHECK`.
- [x] Add Docker Compose for app, persistent data volume, and optional worker process.
- [x] Add quicker cleanup actions for failed and cancelled sources.
- [x] Show source types and filters in source/status views.
- [x] Improve prompt/version handling so extraction behavior is reproducible.
- [x] Improve webpage extraction with better cleanup for navigation, comments, and cookie-banner text.
- [x] Add support for regular recipe page URLs beyond YouTube.
- [x] Add direct text/transcript input as a non-YouTube extraction source.
- [x] Add optional gzip-compressed catalog exports and imports.
- [x] Add import payload migrations that normalize older export versions to the current shape.
- [x] Add schema checks for import format, supported versions, and source list shape.
- [x] Export and import recipe tags in catalog JSON version 2 while keeping version 1 imports compatible.
- [x] Let AI extraction assign existing recipe tags without creating new tags automatically.
- [x] Add a small bookmarklet to send the current YouTube URL to Rezeptinger.
- [x] Add tag filtering/search on the catalog page.
- [x] Add manual tag selection to the regular recipe edit page.
- [x] Add manual recipe tags editable in Django admin and visible on recipe detail pages.
- [x] Show LM Studio connection status and available `/v1/models` entries in admin App settings.
- [x] Add admin-only settings for LM Studio base URL, selected model/default model, transcript limit, language preference, and extraction prompt.
- [x] Add extraction history with retry timestamps, selected LM Studio model, prompt version, raw LM Studio response, and error details.
