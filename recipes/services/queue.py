from __future__ import annotations

from huey.contrib.djhuey import HUEY

from recipes.models import RecipeSource


def queue_status() -> dict[str, int]:
    return {
        "pending": HUEY.pending_count(),
        "scheduled": HUEY.scheduled_count(),
        "results": HUEY.result_count(),
        "processing_sources": RecipeSource.objects.filter(
            status=RecipeSource.Status.PROCESSING
        ).count(),
        "failed_sources": RecipeSource.objects.filter(status=RecipeSource.Status.FAILED).count(),
        "cancelled_sources": RecipeSource.objects.filter(
            status=RecipeSource.Status.CANCELLED
        ).count(),
    }


def revoke_source_task(source: RecipeSource) -> None:
    if source.queue_task_id:
        HUEY.revoke_by_id(source.queue_task_id)
