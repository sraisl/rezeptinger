# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV DJANGO_SETTINGS_MODULE=rezeptinger.settings \
    LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    HUEY_SQLITE_PATH=/data/huey.sqlite3 \
    SQLITE_DATABASE_PATH=/data/db.sqlite3 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN addgroup --system rezeptinger \
    && adduser --system --ingroup rezeptinger --home /app rezeptinger \
    && mkdir -p /data \
    && python manage.py collectstatic --noinput \
    && chmod +x scripts/docker-entrypoint.sh \
    && chown -R rezeptinger:rezeptinger /app /data

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=3).read()"

USER rezeptinger

ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["gunicorn", "rezeptinger.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4"]
