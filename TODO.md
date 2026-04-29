# TODO

## Next

- [ ] Add extraction history with retry timestamps, selected LM Studio model, prompt version, raw LM Studio response, and error details.

## Product

- [ ] Add an in-app settings page for LM Studio base URL, selected model/default model, transcript limit, language preference, and extraction prompt.
- [ ] Show LM Studio connection status and available `/v1/models` entries in the app.
- [ ] Add tags and categories such as pasta, dessert, vegetarian, quick, and meal prep.
- [ ] Add duplicate detection for repeated videos, similar recipe titles, or near-identical ingredient lists.
- [ ] Add a small bookmarklet or browser extension to send the current YouTube URL to Rezeptinger.

## Search And Data

- [ ] Make import/export more explicitly versioned with schema checks, export migrations, and optional compressed exports.

## Extraction

- [ ] Add support for sources beyond YouTube, such as regular recipe pages and direct text/transcript input.
- [ ] Add a fallback for videos without captions by extracting audio and running local speech-to-text, for example Whisper.cpp or faster-whisper.
- [ ] Improve prompt/version handling so extraction behavior is reproducible.

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
