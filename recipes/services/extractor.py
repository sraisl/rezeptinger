from __future__ import annotations

from django.db import transaction

from recipes.models import Recipe, RecipeSource

from .duplicates import find_duplicate_video_recipe
from .ingredients import replace_recipe_ingredients
from .lmstudio import RecipeExtractionError, extract_recipe
from .youtube import TranscriptUnavailable, YouTubeRateLimited, fetch_video


def enqueue_source_processing(source: RecipeSource) -> None:
    source.status = RecipeSource.Status.PROCESSING
    source.error_message = ""
    source.queue_task_id = ""
    source.save(update_fields=["status", "error_message", "queue_task_id", "updated_at"])
    from recipes.tasks import process_source_task

    task = process_source_task(source.pk)
    source.queue_task_id = task.id
    source.save(update_fields=["queue_task_id", "updated_at"])


def process_source(source: RecipeSource) -> RecipeSource:
    source.refresh_from_db()
    if source.status == RecipeSource.Status.CANCELLED:
        return source

    source.status = RecipeSource.Status.PROCESSING
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    try:
        video = fetch_video(source.url)
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            return source

        duplicate_recipe = find_duplicate_video_recipe(video.video_id, source.pk)
        if duplicate_recipe:
            source.title = video.title
            source.channel = video.channel
            source.video_id = video.video_id
            source.thumbnail_url = video.thumbnail_url
            source.transcript = video.transcript
            source.status = RecipeSource.Status.FAILED
            source.error_message = (
                "Dieses Video ist bereits als Rezept "
                f'"{duplicate_recipe.title}" im Katalog gespeichert.'
            )
            source.queue_task_id = ""
            source.save()
            return source

        payload = extract_recipe(video.title, video.channel, video.transcript)
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            return source

        with transaction.atomic():
            source.title = video.title
            source.channel = video.channel
            source.video_id = video.video_id
            source.thumbnail_url = video.thumbnail_url
            source.transcript = video.transcript

            if not payload["is_recipe"]:
                source.status = RecipeSource.Status.FAILED
                source.error_message = payload.get("reason", "Kein Rezept erkannt.")
                source.queue_task_id = ""
                source.save()
                return source

            recipe, _ = Recipe.objects.update_or_create(
                source=source,
                defaults={
                    "title": payload["title"],
                    "summary": payload["summary"],
                    "servings": payload["servings"],
                    "prep_time": payload["prep_time"],
                    "cook_time": payload["cook_time"],
                    "total_time": payload["total_time"],
                    "ingredients": payload["ingredients"],
                    "steps": payload["steps"],
                    "notes": payload["notes"],
                    "confidence": payload["confidence"],
                },
            )
            replace_recipe_ingredients(recipe, payload["ingredients"])
            source.status = RecipeSource.Status.DONE
            source.error_message = ""
            source.queue_task_id = ""
            source.save()

    except (TranscriptUnavailable, YouTubeRateLimited, RecipeExtractionError, Exception) as exc:
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            return source
        source.status = RecipeSource.Status.FAILED
        source.error_message = str(exc)
        source.queue_task_id = ""
        source.save(update_fields=["status", "error_message", "queue_task_id", "updated_at"])

    return source
