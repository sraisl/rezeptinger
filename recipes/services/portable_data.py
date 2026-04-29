from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.dateparse import parse_datetime

from recipes.models import Recipe, RecipeSource, Tag

from .ingredients import replace_recipe_ingredients

EXPORT_VERSION = 2
SUPPORTED_IMPORT_VERSIONS = {1, 2}


def export_catalog() -> dict[str, Any]:
    return {
        "format": "rezeptinger.catalog",
        "version": EXPORT_VERSION,
        "sources": [_source_to_payload(source) for source in RecipeSource.objects.all()],
    }


@transaction.atomic
def import_catalog(payload: dict[str, Any]) -> dict[str, int]:
    payload = migrate_import_payload(payload)
    sources = validate_import_payload(payload)

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
                "queue_task_id": source_payload.get("queue_task_id", ""),
            },
        )
        _restore_timestamps(source, source_payload)
        imported_sources += 1

        recipe_payload = source_payload.get("recipe")
        if isinstance(recipe_payload, dict):
            recipe, _ = Recipe.objects.update_or_create(
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
            replace_recipe_ingredients(recipe, _list_value(recipe_payload.get("ingredients")))
            _restore_recipe_tags(recipe, _list_value(recipe_payload.get("tags")))
            _restore_timestamps(recipe, recipe_payload)
            imported_recipes += 1
        elif hasattr(source, "recipe"):
            source.recipe.delete()

    return {"sources": imported_sources, "recipes": imported_recipes}


def validate_import_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Die Datei ist kein gültiges JSON-Objekt.")

    if payload.get("format") != "rezeptinger.catalog":
        raise ValueError("Die Datei ist kein Rezeptinger-Katalogexport.")

    version = payload.get("version")
    if not isinstance(version, int):
        raise ValueError("Der Rezeptinger-Export enthält keine gültige Versionsnummer.")

    if version not in SUPPORTED_IMPORT_VERSIONS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_IMPORT_VERSIONS))
        raise ValueError(
            f"Rezeptinger-Exportversion {version} wird nicht unterstützt. "
            f"Unterstützt werden: {supported}."
        )

    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Der Rezeptinger-Export enthält keine gültige Quellenliste.")

    return sources


def migrate_import_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_import_payload(payload)
    version = payload["version"]
    if version == EXPORT_VERSION:
        return payload

    migrated = {
        **payload,
        "version": EXPORT_VERSION,
        "sources": [
            _migrate_source_payload(source_payload) for source_payload in payload["sources"]
        ],
    }
    return migrated


def _migrate_source_payload(source_payload: Any) -> Any:
    if not isinstance(source_payload, dict):
        return source_payload

    recipe_payload = source_payload.get("recipe")
    if not isinstance(recipe_payload, dict):
        return source_payload

    return {
        **source_payload,
        "recipe": {
            **recipe_payload,
            "tags": _list_value(recipe_payload.get("tags")),
        },
    }


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
        "queue_task_id": source.queue_task_id,
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
        "ingredients": recipe.ingredient_payloads(),
        "steps": recipe.steps,
        "notes": recipe.notes,
        "tags": list(recipe.tags.values_list("name", flat=True)),
        "confidence": recipe.confidence,
        "created_at": recipe.created_at.isoformat(),
        "updated_at": recipe.updated_at.isoformat(),
    }


def _source_status(value: str | None) -> str:
    allowed = {choice.value for choice in RecipeSource.Status}
    return value if value in allowed else RecipeSource.Status.PENDING


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _restore_recipe_tags(recipe: Recipe, tag_names: list[Any]) -> None:
    tags = []
    for tag_name in tag_names:
        name = str(tag_name).strip()
        if not name:
            continue
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    recipe.tags.set(tags)


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
