from __future__ import annotations

import os

from django.conf import settings

from recipes.models import AppSettings


def load_app_settings() -> AppSettings:
    return AppSettings.load()


def lm_studio_base_url() -> str:
    app_settings = load_app_settings()
    return (
        app_settings.lm_studio_base_url.strip()
        or os.environ.get("LM_STUDIO_BASE_URL", "").strip()
        or settings.LM_STUDIO_BASE_URL
    ).rstrip("/")


def lm_studio_model() -> str:
    app_settings = load_app_settings()
    return (
        app_settings.lm_studio_model.strip()
        or os.environ.get("LM_STUDIO_MODEL", "").strip()
        or settings.LM_STUDIO_MODEL
    )


def lm_studio_max_tokens() -> int:
    raw_value = os.environ.get("LM_STUDIO_MAX_TOKENS", "").strip()
    if not raw_value:
        raw_value = str(getattr(settings, "LM_STUDIO_MAX_TOKENS", 8192))
    try:
        value = int(raw_value)
    except ValueError:
        value = 8192
    return max(512, min(32768, value))


def transcript_limit() -> int:
    app_settings = load_app_settings()
    return max(1000, min(200000, app_settings.transcript_limit or 30000))


def language_preferences() -> list[str]:
    raw_value = load_app_settings().language_preference
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def extraction_prompt() -> str:
    return load_app_settings().extraction_prompt.strip()
