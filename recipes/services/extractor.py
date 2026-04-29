from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from recipes.models import ExtractionAttempt, Recipe, RecipeSource, Tag

from .duplicates import find_duplicate_video_recipe
from .ingredients import replace_recipe_ingredients
from .lmstudio import RecipeExtractionError, extract_recipe_result
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

    attempt = ExtractionAttempt.objects.create(source=source)
    source.status = RecipeSource.Status.PROCESSING
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    try:
        video = fetch_video(source.url)
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            _finish_attempt(
                attempt,
                ExtractionAttempt.Status.CANCELLED,
                "Extraktion wurde abgebrochen.",
            )
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
            _finish_attempt(attempt, ExtractionAttempt.Status.FAILED, source.error_message)
            return source

        result = extract_recipe_result(video.title, video.channel, video.transcript)
        payload = result.payload
        attempt.lm_studio_model = result.lm_studio_model
        attempt.prompt_version = result.prompt_version
        attempt.raw_lm_studio_response = result.raw_response
        attempt.save(
            update_fields=[
                "lm_studio_model",
                "prompt_version",
                "raw_lm_studio_response",
            ]
        )
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            _finish_attempt(
                attempt,
                ExtractionAttempt.Status.CANCELLED,
                "Extraktion wurde abgebrochen.",
            )
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
                _finish_attempt(attempt, ExtractionAttempt.Status.FAILED, source.error_message)
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
            _replace_recipe_tags(recipe, payload.get("tags", []))
            source.status = RecipeSource.Status.DONE
            source.error_message = ""
            source.queue_task_id = ""
            source.save()
            _finish_attempt(attempt, ExtractionAttempt.Status.DONE)

    except (TranscriptUnavailable, YouTubeRateLimited, RecipeExtractionError, Exception) as exc:
        source.refresh_from_db()
        if source.status == RecipeSource.Status.CANCELLED:
            _finish_attempt(
                attempt,
                ExtractionAttempt.Status.CANCELLED,
                "Extraktion wurde abgebrochen.",
            )
            return source
        if isinstance(exc, RecipeExtractionError):
            attempt.lm_studio_model = exc.lm_studio_model
            attempt.prompt_version = exc.prompt_version
            attempt.raw_lm_studio_response = exc.raw_response
        source.status = RecipeSource.Status.FAILED
        source.error_message = str(exc)
        source.queue_task_id = ""
        source.save(update_fields=["status", "error_message", "queue_task_id", "updated_at"])
        _finish_attempt(attempt, ExtractionAttempt.Status.FAILED, str(exc))

    return source


def _replace_recipe_tags(recipe: Recipe, tag_names: list[str]) -> None:
    normalized_names = {str(name).strip().lower() for name in tag_names if str(name).strip()}
    if not normalized_names:
        recipe.tags.clear()
        return

    tags = [
        tag
        for tag in Tag.objects.all()
        if tag.name.lower() in normalized_names or tag.slug.lower() in normalized_names
    ]
    recipe.tags.set(tags)


def _finish_attempt(
    attempt: ExtractionAttempt,
    status: ExtractionAttempt.Status,
    error_details: str = "",
) -> None:
    attempt.status = status
    attempt.error_details = error_details
    attempt.finished_at = timezone.now()
    attempt.save(
        update_fields=[
            "status",
            "error_details",
            "finished_at",
            "lm_studio_model",
            "prompt_version",
            "raw_lm_studio_response",
        ]
    )
