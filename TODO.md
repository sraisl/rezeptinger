# TODO

## Next

- [ ] Add a fallback for videos without captions by extracting audio and running local speech-to-text, for example Whisper.cpp or faster-whisper.

## Product

## Search And Data

## Extraction


## Docker And Deployment

- [ ] Add a production-style container variant with Gunicorn instead of Django `runserver`.
- [ ] Run the container as a non-root user.
- [ ] Add a Docker healthcheck endpoint and Dockerfile `HEALTHCHECK`.
- [ ] Add Docker Compose for app, persistent data volume, and optional worker process.

## CI And Security

- [ ] Add Dockerfile linting, for example Hadolint.
- [ ] Add container image vulnerability scanning, for example Trivy.
- [ ] Upload security findings as SARIF where useful.
- [ ] Add a GitHub release flow where tags like `vX.Y.Z` publish GHCR images and release notes.

## Done

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
