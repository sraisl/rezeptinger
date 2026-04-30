from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import httpx

from recipes.models import Tag

from .app_settings import extraction_prompt, lm_studio_base_url, lm_studio_model, transcript_limit


class RecipeExtractionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        lm_studio_model: str = "",
        prompt_version: str = "",
        raw_response: str = "",
    ) -> None:
        super().__init__(message)
        self.lm_studio_model = lm_studio_model
        self.prompt_version = prompt_version
        self.raw_response = raw_response


@dataclass(frozen=True)
class RecipeExtractionResult:
    payload: dict[str, Any]
    lm_studio_model: str
    prompt_version: str
    raw_response: str


@dataclass(frozen=True)
class LmStudioConnectionStatus:
    base_url: str
    is_available: bool
    model_ids: list[str]
    error_message: str = ""


DEFAULT_PROMPT_VERSION = "default-v1"

SYSTEM_PROMPT = """
Du extrahierst Kochrezepte aus YouTube-Transkripten.
Antworte ausschließlich als valides JSON-Objekt. Keine Markdown-Blöcke.
Wenn das Video kein Rezept enthält, setze "is_recipe" auf false.
Nutze nur Informationen, die im Transkript oder in den Metadaten erkennbar sind.
Schätze keine exakten Mengen, wenn sie nicht genannt werden.
""".strip()


def extract_recipe(video_title: str, channel: str, transcript: str) -> dict[str, Any]:
    return extract_recipe_result(video_title, channel, transcript).payload


def connection_status(base_url: str | None = None) -> LmStudioConnectionStatus:
    resolved_base_url = (base_url or lm_studio_base_url()).rstrip("/")

    try:
        response = httpx.get(f"{resolved_base_url}/models", timeout=5)
        response.raise_for_status()
        models = response.json().get("data", [])
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        return LmStudioConnectionStatus(
            base_url=resolved_base_url,
            is_available=False,
            model_ids=[],
            error_message=str(exc),
        )

    model_ids = [model.get("id") for model in models if isinstance(model, dict) and model.get("id")]
    return LmStudioConnectionStatus(
        base_url=resolved_base_url,
        is_available=True,
        model_ids=model_ids,
    )


def extract_recipe_result(
    video_title: str,
    channel: str,
    transcript: str,
) -> RecipeExtractionResult:
    base_url = lm_studio_base_url()
    model = _resolve_model(base_url)
    prompt = _build_prompt(video_title, channel, transcript)
    system_prompt, prompt_version = _system_prompt_with_version()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    try:
        json_payload = {**payload, "response_format": {"type": "json_object"}}
        response = _post_chat_completion(base_url, json_payload)
        if response.status_code == 400:
            response = _post_chat_completion(base_url, payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        message = _format_http_error(exc)
        raw_response = ""
        if isinstance(exc, httpx.HTTPStatusError):
            raw_response = exc.response.text
        raise RecipeExtractionError(
            message,
            lm_studio_model=model,
            prompt_version=prompt_version,
            raw_response=raw_response,
        ) from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
        data = _parse_json_content(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        excerpt = _response_content_excerpt(response)
        message = f"LM Studio hat keine valide JSON-Antwort geliefert. Antwortauszug: {excerpt}"
        raise RecipeExtractionError(
            message,
            lm_studio_model=model,
            prompt_version=prompt_version,
            raw_response=_raw_response_content(response),
        ) from exc

    return RecipeExtractionResult(
        payload=_normalize_recipe_payload(data),
        lm_studio_model=model,
        prompt_version=prompt_version,
        raw_response=content,
    )


def _system_prompt_with_version() -> tuple[str, str]:
    custom_prompt = extraction_prompt()
    if custom_prompt:
        return custom_prompt, f"custom-{_prompt_hash(custom_prompt)}"
    return SYSTEM_PROMPT, DEFAULT_PROMPT_VERSION


def _prompt_hash(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()[:12]


def _resolve_model(base_url: str) -> str:
    configured = lm_studio_model().strip()
    if configured:
        return configured

    try:
        response = httpx.get(f"{base_url}/models", timeout=10)
        response.raise_for_status()
        models = response.json().get("data", [])
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        message = (
            "LM Studio ist erreichbar? Kein Modell konnte automatisch geladen werden. "
            "Starte LM Studio mit geladenem Modell oder setze LM_STUDIO_MODEL."
        )
        raise RecipeExtractionError(message) from exc

    model_ids = [model.get("id") for model in models if isinstance(model, dict) and model.get("id")]
    preferred = [
        model_id
        for model_id in model_ids
        if any(marker in model_id.lower() for marker in ("instruct", "chat", "qwen", "mistral"))
        and "embedding" not in model_id.lower()
    ]
    if preferred:
        return preferred[0]
    if model_ids:
        return model_ids[0]

    raise RecipeExtractionError(
        "LM Studio meldet keine geladenen Modelle. "
        "Lade ein Modell in LM Studio und versuche es erneut."
    )


def _post_chat_completion(base_url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.post(f"{base_url}/chat/completions", json=payload, timeout=120)


def _format_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = _response_error_detail(exc.response)
        return f"LM Studio meldet Fehler {exc.response.status_code}: {detail}"
    return f"LM Studio ist nicht erreichbar oder meldet Fehler: {exc}"


def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500] or response.reason_phrase

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if error:
        return str(error)
    return str(payload)[:500]


def _parse_json_content(content: str) -> dict[str, Any]:
    content = content.strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, str):
            return _parse_json_content(parsed)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return _parse_json_content(fenced.group(1))

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise json.JSONDecodeError("No JSON object found", content, 0)


def _response_content_excerpt(response: httpx.Response) -> str:
    content = _raw_response_content(response)
    content = re.sub(r"\s+", " ", str(content)).strip()
    return content[:500] or "leer"


def _raw_response_content(response: httpx.Response) -> str:
    try:
        return str(response.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        return response.text


def _build_prompt(video_title: str, channel: str, transcript: str) -> str:
    transcript = transcript[: transcript_limit()]
    allowed_tags = ", ".join(_allowed_tag_names()) or "keine Tags verfügbar"
    return f"""
Video-Titel: {video_title}
Kanal: {channel}

Extrahiere ein Rezept in diesem JSON-Schema:
{{
  "is_recipe": true,
  "title": "Name des Rezepts",
  "summary": "kurze Beschreibung",
  "servings": "z.B. 4 Portionen oder leer",
  "prep_time": "Vorbereitungszeit oder leer",
  "cook_time": "Koch-/Backzeit oder leer",
  "total_time": "Gesamtzeit oder leer",
  "ingredients": [
    {{"quantity": "200", "unit": "g", "name": "Mehl", "note": "optional"}}
  ],
  "steps": ["Schritt 1", "Schritt 2"],
  "notes": ["wichtige Hinweise"],
  "tags": ["bestehender-tag"],
  "confidence": 0.0
}}

Nutze für "tags" nur Tags aus dieser Liste. Wenn keiner passt, nutze eine leere Liste:
{allowed_tags}

Wenn kein Rezept erkennbar ist:
{{"is_recipe": false, "reason": "kurze Begründung", "confidence": 0.0}}

Transkript:
{transcript}
""".strip()


def _normalize_recipe_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("is_recipe"):
        return {
            "is_recipe": False,
            "reason": str(data.get("reason", "Kein Rezept erkannt.")),
            "confidence": float(data.get("confidence") or 0.0),
        }

    return {
        "is_recipe": True,
        "title": str(data.get("title") or "Unbenanntes Rezept"),
        "summary": str(data.get("summary") or ""),
        "servings": str(data.get("servings") or ""),
        "prep_time": str(data.get("prep_time") or ""),
        "cook_time": str(data.get("cook_time") or ""),
        "total_time": str(data.get("total_time") or ""),
        "ingredients": _as_list(data.get("ingredients")),
        "steps": _as_list(data.get("steps")),
        "notes": _as_list(data.get("notes")),
        "tags": _string_list(data.get("tags")),
        "confidence": max(0.0, min(1.0, float(data.get("confidence") or 0.0))),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _allowed_tag_names() -> list[str]:
    return list(Tag.objects.values_list("name", flat=True))
