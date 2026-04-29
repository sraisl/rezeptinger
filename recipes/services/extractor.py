from __future__ import annotations

from threading import Thread

from django.db import close_old_connections, transaction

from recipes.models import Recipe, RecipeSource

from .lmstudio import RecipeExtractionError, extract_recipe
from .youtube import TranscriptUnavailable, fetch_video


def enqueue_source_processing(source: RecipeSource) -> None:
    source.status = RecipeSource.Status.PROCESSING
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    thread = Thread(target=_process_source_by_id, args=(source.pk,), daemon=True)
    thread.start()


def _process_source_by_id(source_id: int) -> None:
    close_old_connections()
    try:
        source = RecipeSource.objects.get(pk=source_id)
        process_source(source)
    finally:
        close_old_connections()


def process_source(source: RecipeSource) -> RecipeSource:
    source.status = RecipeSource.Status.PROCESSING
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    try:
        video = fetch_video(source.url)
        payload = extract_recipe(video.title, video.channel, video.transcript)

        with transaction.atomic():
            source.title = video.title
            source.channel = video.channel
            source.video_id = video.video_id
            source.thumbnail_url = video.thumbnail_url
            source.transcript = video.transcript

            if not payload["is_recipe"]:
                source.status = RecipeSource.Status.FAILED
                source.error_message = payload.get("reason", "Kein Rezept erkannt.")
                source.save()
                return source

            Recipe.objects.update_or_create(
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
            source.status = RecipeSource.Status.DONE
            source.error_message = ""
            source.save()

    except (TranscriptUnavailable, RecipeExtractionError, Exception) as exc:
        source.status = RecipeSource.Status.FAILED
        source.error_message = str(exc)
        source.save(update_fields=["status", "error_message", "updated_at"])

    return source
