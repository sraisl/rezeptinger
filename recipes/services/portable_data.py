from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.dateparse import parse_datetime

from recipes.models import Recipe, RecipeSource

EXPORT_VERSION = 1


def export_catalog() -> dict[str, Any]:
    return {
        "format": "rezeptinger.catalog",
        "version": EXPORT_VERSION,
        "sources": [_source_to_payload(source) for source in RecipeSource.objects.all()],
    }


@transaction.atomic
def import_catalog(payload: dict[str, Any]) -> dict[str, int]:
    sources = payload.get("sources")
    if payload.get("format") != "rezeptinger.catalog" or not isinstance(sources, list):
        raise ValueError("Die Datei ist kein gültiger Rezeptinger-Export.")

    imported_sources = 0
    imported_recipes = 0

    for source_payload in sources:
        if not isinstance(source_payload, dict) or not source_payload.get("url"):
            continue

        source, _ = RecipeSource.objects.update_or_create(
            url=source_payload["url"],
            defaults={
                "title": source_payload.get("title", ""),
                "channel": source_payload.get("channel", ""),
                "video_id": source_payload.get("video_id", ""),
                "thumbnail_url": source_payload.get("thumbnail_url", ""),
                "transcript": source_payload.get("transcript", ""),
                "status": _source_status(source_payload.get("status")),
                "error_message": source_payload.get("error_message", ""),
            },
        )
        _restore_timestamps(source, source_payload)
        imported_sources += 1

        recipe_payload = source_payload.get("recipe")
        if isinstance(recipe_payload, dict):
            Recipe.objects.update_or_create(
                source=source,
                defaults={
                    "title": recipe_payload.get("title", "Unbenanntes Rezept"),
                    "summary": recipe_payload.get("summary", ""),
                    "servings": recipe_payload.get("servings", ""),
                    "prep_time": recipe_payload.get("prep_time", ""),
                    "cook_time": recipe_payload.get("cook_time", ""),
                    "total_time": recipe_payload.get("total_time", ""),
                    "ingredients": _list_value(recipe_payload.get("ingredients")),
                    "steps": _list_value(recipe_payload.get("steps")),
                    "notes": _list_value(recipe_payload.get("notes")),
                    "confidence": float(recipe_payload.get("confidence") or 0.0),
                },
            )
            _restore_timestamps(source.recipe, recipe_payload)
            imported_recipes += 1
        elif hasattr(source, "recipe"):
            source.recipe.delete()

    return {"sources": imported_sources, "recipes": imported_recipes}


def _source_to_payload(source: RecipeSource) -> dict[str, Any]:
    payload = {
        "url": source.url,
        "title": source.title,
        "channel": source.channel,
        "video_id": source.video_id,
        "thumbnail_url": source.thumbnail_url,
        "transcript": source.transcript,
        "status": source.status,
        "error_message": source.error_message,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
        "recipe": None,
    }
    if hasattr(source, "recipe"):
        payload["recipe"] = _recipe_to_payload(source.recipe)
    return payload


def _recipe_to_payload(recipe: Recipe) -> dict[str, Any]:
    return {
        "title": recipe.title,
        "summary": recipe.summary,
        "servings": recipe.servings,
        "prep_time": recipe.prep_time,
        "cook_time": recipe.cook_time,
        "total_time": recipe.total_time,
        "ingredients": recipe.ingredients,
        "steps": recipe.steps,
        "notes": recipe.notes,
        "confidence": recipe.confidence,
        "created_at": recipe.created_at.isoformat(),
        "updated_at": recipe.updated_at.isoformat(),
    }


def _source_status(value: str | None) -> str:
    allowed = {choice.value for choice in RecipeSource.Status}
    return value if value in allowed else RecipeSource.Status.PENDING


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _restore_timestamps(instance, payload: dict[str, Any]) -> None:
    updates = {}
    for field in ("created_at", "updated_at"):
        parsed = parse_datetime(payload.get(field, ""))
        if parsed:
            updates[field] = parsed

    if updates:
        type(instance).objects.filter(pk=instance.pk).update(**updates)
        for field, value in updates.items():
            setattr(instance, field, value)
